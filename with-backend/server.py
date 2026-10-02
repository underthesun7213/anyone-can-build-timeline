"""Timeline: the backend. Start it with `python3 server.py`, then open http://localhost:8009

This file has three parts:
  CONTROLLER  reads each request and decides what to do
  MODEL       the rules, and the database (two tables: users and posts)
              A reply is a post that points at the post it answers.
  VIEW        turns database rows into the JSON answer
It uses only the Python standard library, so there is nothing to install.
"""

import argparse
import json
import os
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "timeline.db")

# The page files this server gives to the browser, and the type of each one.
PAGE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


# ============================================================================
#  CONTROLLER
#  Reads the request. Picks what to do. Asks the model. Sends the answer.
# ============================================================================

class TimelineHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        url = urlparse(self.path)
        if url.path == "/posts":
            try:
                after = int(parse_qs(url.query).get("after", ["0"])[0])
            except ValueError:
                self.send_json(400, {"error": "'after' must be a whole number."})
                return
            rows = posts_after(self.server.db_path, after)
            self.send_json(200, posts_to_json(rows))
        elif url.path in PAGE_FILES:
            file_name, content_type = PAGE_FILES[url.path]
            try:
                with open(os.path.join(HERE, file_name), "rb") as page_file:
                    self.send_answer(200, content_type, page_file.read())
            except OSError:
                self.send_json(404, {"error": "The file " + file_name + " is missing."})
        else:
            self.send_json(404, {"error": "There is nothing at " + url.path})

    def do_POST(self):
        if urlparse(self.path).path != "/posts":
            self.send_json(404, {"error": "You can only send a post to /posts"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length))
        except ValueError:
            self.send_json(400, {"error": "The request must be JSON."})
            return
        if not isinstance(data, dict):
            self.send_json(400, {"error": "The request must be a JSON object."})
            return
        try:
            row = save_post(self.server.db_path, data.get("author"), data.get("text"),
                            data.get("reply_to"))
        except RuleBroken as problem:
            self.send_json(400, {"error": str(problem)})
            return
        self.send_json(201, post_to_json(row))
        print(post_to_log_line(row), flush=True)   # one line in the terminal for each new post

    def send_json(self, status, data):
        body = json.dumps(data).encode("utf-8")
        self.send_answer(status, "application/json; charset=utf-8", body)

    def send_answer(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Each window asks for new posts every second. Printing all of those
        # questions would fill the screen, so they are not printed.
        if self.command == "GET" and self.path.startswith("/posts"):
            return
        BaseHTTPRequestHandler.log_message(self, format, *args)


# ============================================================================
#  MODEL
#  The rules a post must follow, and the database that keeps the posts.
#  Two tables: users (each person once) and posts (each post points at its
#  author by the author's id). A reply is a post too: its reply_to is the id
#  of the post it answers. That post can itself be a reply, but a reply to a
#  reply cannot be answered. A new rule goes here, never in the controller or
#  the view.
# ============================================================================

MAX_TEXT = 280
MAX_AUTHOR = 40
MAX_REPLY_DEPTH = 2  # a reply is 1 deep, a reply to a reply is 2 deep, and nothing goes deeper


class RuleBroken(Exception):
    """A post broke one of the rules. The message says which rule."""


def connect(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row  # so a row can be read as row["author"]
    connection.execute("PRAGMA foreign_keys = ON")  # a post must point at a real user
    return connection


def create_tables(db_path):
    connection = connect(db_path)
    old = [c["name"] for c in connection.execute("PRAGMA table_info(posts)")]
    if old and "author_id" not in old:
        connection.close()
        raise SystemExit("timeline.db was made by an older version of Timeline. "
                         "Run `make reset`, then start the server again.")
    connection.execute("CREATE TABLE IF NOT EXISTS users ("
                       "id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
    connection.execute("CREATE TABLE IF NOT EXISTS posts ("
                       "id INTEGER PRIMARY KEY, "
                       "author_id INTEGER NOT NULL REFERENCES users(id), "
                       "text TEXT NOT NULL, posted_at TEXT NOT NULL, "
                       "reply_to INTEGER REFERENCES posts(id))")
    if old and "reply_to" not in old:
        # A database from before replies. Add the new column, and keep its posts.
        connection.execute("ALTER TABLE posts ADD COLUMN reply_to INTEGER REFERENCES posts(id)")
    connection.commit()
    connection.close()


# Each post, with its author's name looked up in users. The view reads row["author"].
POSTS_WITH_AUTHORS = ("SELECT posts.id, users.name AS author, posts.text, posts.posted_at, "
                      "posts.reply_to FROM posts JOIN users ON users.id = posts.author_id")


def check_rules(author, text):
    """Return the author and text without extra spaces, or raise RuleBroken."""
    author = author.strip() if isinstance(author, str) else ""
    text = text.strip() if isinstance(text, str) else ""
    if author == "":
        raise RuleBroken("The name must not be empty.")
    if len(author) > MAX_AUTHOR:
        raise RuleBroken(f"The name must be {MAX_AUTHOR} characters or fewer.")
    if text == "":
        raise RuleBroken("The post must not be empty.")
    if len(text) > MAX_TEXT:
        raise RuleBroken(f"The post must be {MAX_TEXT} characters or fewer.")
    return author, text


def user_id_for(connection, name):
    """Return the id of the user with this name, adding the user the first time."""
    row = connection.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["id"]
    return connection.execute("INSERT INTO users (name) VALUES (?)", (name,)).lastrowid


def depth_of(connection, post_id):
    """Return how deep a post is: 0 for a post, 1 for a reply, 2 for a reply to a reply.

    Return None if there is no post with this id.
    """
    find = "SELECT reply_to FROM posts WHERE id = ?"
    try:
        row = connection.execute(find, (post_id,)).fetchone()
    except OverflowError:  # a number too large for the database is not a post either
        row = None
    if row is None:
        return None
    depth = 0
    while row["reply_to"] is not None:  # walk up, one answered post at a time
        depth += 1
        row = connection.execute(find, (row["reply_to"],)).fetchone()
    return depth


def check_reply_to(connection, reply_to):
    """Return the id of the post being answered (None for a new post), or raise RuleBroken.

    The post being answered may be a reply itself: that is a reply to a reply.
    A reply to a reply cannot be answered, so replies stop at MAX_REPLY_DEPTH.
    """
    if reply_to is None:
        return None
    # In Python, True and False count as whole numbers, so they are refused by name.
    if isinstance(reply_to, bool) or not isinstance(reply_to, int):
        raise RuleBroken("A reply must name the post it answers by its id, a whole number.")
    depth = depth_of(connection, reply_to)
    if depth is None:
        raise RuleBroken("The post you are replying to does not exist.")
    if depth >= MAX_REPLY_DEPTH:
        raise RuleBroken(f"Replies go only {MAX_REPLY_DEPTH} levels deep, "
                         "so this reply cannot be answered.")
    return reply_to


def save_post(db_path, author, text, reply_to=None):
    """Check the rules, save the post, and return the saved row.

    `reply_to` is the id of the post this one answers, or None for a new post.
    """
    author, text = check_rules(author, text)
    connection = connect(db_path)
    try:
        reply_to = check_reply_to(connection, reply_to)
        author_id = user_id_for(connection, author)
        cursor = connection.execute(
            "INSERT INTO posts (author_id, text, posted_at, reply_to) VALUES (?, ?, ?, ?)",
            (author_id, text, time.strftime("%H:%M"), reply_to))
        connection.commit()
        return connection.execute(POSTS_WITH_AUTHORS + " WHERE posts.id = ?",
                                  (cursor.lastrowid,)).fetchone()
    finally:
        connection.close()  # also when a rule was broken


def posts_after(db_path, after):
    """Return every post with an id larger than `after`, replies too, oldest first."""
    connection = connect(db_path)
    rows = connection.execute(POSTS_WITH_AUTHORS + " WHERE posts.id > ? ORDER BY posts.id",
                              (after,)).fetchall()
    connection.close()
    return rows


# ============================================================================
#  VIEW
#  Turns database rows into the JSON the page reads.
# ============================================================================

def post_to_json(row):
    # reply_to is the id of the post this one answers. It is None for a post that is not a reply.
    return {"id": row["id"], "author": row["author"], "text": row["text"],
            "posted_at": row["posted_at"], "reply_to": row["reply_to"]}


def posts_to_json(rows):
    return [post_to_json(row) for row in rows]


def post_to_log_line(row):
    """One line for the terminal: when the post was written, who wrote it, and what it says."""
    return f"{row['posted_at']}  {row['author']}: {row['text']}"


# ============================================================================
#  Starting the server
# ============================================================================

def make_server(port, db_path):
    create_tables(db_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), TimelineHandler)
    server.db_path = db_path
    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the Timeline server.")
    parser.add_argument("--port", type=int, default=8009)
    port = parser.parse_args().port
    server = make_server(port, DB_PATH)
    print("Timeline is running at http://localhost:" + str(port))
    print("The posts are kept in " + DB_PATH)
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    server.server_close()
