"""Timeline: the backend. Start it with `python3 server.py`, then open http://localhost:8009

This file has three parts:
  CONTROLLER  reads each request and decides what to do
  MODEL       the rules, and the database (four tables: users, posts, likes and follows)
              A reply is a post that points at the post it answers.
              A like is a pair: this user likes this post.
              A follow is a pair too: this user follows that user.
  VIEW        turns database rows into the JSON answer
It uses only the Python standard library, so there is nothing to install.

Timeline의 백엔드. `python3 server.py`로 켠 뒤 http://localhost:8009 를 여세요.

이 파일은 세 부분으로 되어 있습니다:
  CONTROLLER  요청을 하나씩 읽고 무엇을 할지 정합니다
  MODEL       규칙과 데이터베이스 (표 네 개: users, posts, likes, follows)
              답글은 자신이 답하는 글을 가리키는 글입니다.
              좋아요는 짝입니다: 이 사용자가 이 글을 좋아합니다.
              팔로우도 짝입니다: 이 사용자가 저 사용자를 팔로우합니다.
  VIEW        데이터베이스의 줄을 JSON 답으로 바꿉니다
파이썬 표준 라이브러리만 쓰므로 설치할 것이 없습니다.
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
# 이 서버가 브라우저에 주는 화면 파일과, 각 파일의 종류.
PAGE_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


# ============================================================================
#  CONTROLLER
#  Reads the request. Picks what to do. Asks the model. Sends the answer.
#  컨트롤러
#  요청을 읽습니다. 할 일을 고릅니다. 모델에 묻습니다. 답을 보냅니다.
# ============================================================================

class TimelineHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        url = urlparse(self.path)
        query = parse_qs(url.query)
        if url.path == "/posts":
            try:
                after = int(query.get("after", ["0"])[0])
            except ValueError:
                self.send_json(400, {"error": "'after' must be a whole number."})
                return
            # ?following=Aiko asks for the timeline of the people Aiko follows, not everyone's.
            # ?following=Aiko는 모두의 글이 아니라, Aiko가 팔로우하는 사람들의 타임라인을 달라는 뜻입니다.
            following = query.get("following", [None])[0]
            rows = posts_after(self.server.db_path, after, following)
            self.send_json(200, posts_to_json(rows))
        elif url.path == "/likes":
            rows = like_counts(self.server.db_path)
            self.send_json(200, like_counts_to_json(rows))
        elif url.path == "/follows":
            by = query.get("by", [""])[0]
            rows = following_names(self.server.db_path, by)
            self.send_json(200, names_to_json(rows))
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
        path = urlparse(self.path).path
        if path not in ("/posts", "/likes", "/follows"):
            self.send_json(404, {"error": "You can only send a post to /posts, a like to /likes, "
                                          "or a follow to /follows"})
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
            if path == "/posts":
                row = save_post(self.server.db_path, data.get("author"), data.get("text"),
                                data.get("reply_to"))
                answer = post_to_json(row)
                print(post_to_log_line(row), flush=True)   # one line in the terminal for each new post / 새 글마다 터미널에 한 줄
            elif path == "/likes":
                # The answer is the liked post, with its new number of likes.
                # 답은 좋아요를 받은 글과 그 새 좋아요 수입니다.
                row = save_like(self.server.db_path, data.get("author"), data.get("post_id"))
                answer = post_to_json(row)
            else:
                # The answer is every name this user follows now.
                # 답은 이 사용자가 지금 팔로우하는 모든 이름입니다.
                rows = save_follow(self.server.db_path, data.get("author"), data.get("follow"))
                answer = names_to_json(rows)
        except RuleBroken as problem:
            self.send_json(400, {"error": str(problem)})
            return
        self.send_json(201, answer)

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
        # 각 창은 1초마다 새 글이 있는지 묻습니다. 그 질문을 전부 찍으면
        # 화면이 가득 차므로 찍지 않습니다.
        if self.command == "GET" and self.path.startswith(("/posts", "/likes", "/follows")):
            return
        BaseHTTPRequestHandler.log_message(self, format, *args)


# ============================================================================
#  MODEL
#  The rules a post, a like and a follow must follow, and the database that
#  keeps them. Four tables: users (each person once), posts (each post points
#  at its author by the author's id), likes (each like points at a post and
#  at the user who likes it) and follows (each follow points at the user who
#  follows and at the user being followed). A reply is a post too: its
#  reply_to is the id of the post it answers. That post can itself be a
#  reply, but a reply to a reply cannot be answered. A like has no id of its
#  own: the pair (post, user) is the like, so one user can like one post only
#  once. A follow is a pair in the same way. A new rule goes here, never in
#  the controller or the view.
#  모델
#  글, 좋아요, 팔로우가 따라야 하는 규칙과, 그것들을 보관하는 데이터베이스.
#  표 네 개: users(사람마다 한 번), posts(글마다 작성자를 그 사람의 id로
#  가리킴), likes(좋아요마다 글 하나와 그 글을 좋아하는 사용자를 가리킴),
#  follows(팔로우마다 팔로우하는 사용자와 팔로우받는 사용자를 가리킴).
#  답글도 글입니다: reply_to는 답하는 글의 id입니다. 그 글이 답글일 수도
#  있지만, 답글의 답글에는 답할 수 없습니다. 좋아요에는 자기 id가 없습니다:
#  (글, 사용자) 짝이 곧 좋아요이므로, 한 사용자는 한 글을 한 번만 좋아할 수
#  있습니다. 팔로우도 같은 방식의 짝입니다. 새 규칙은 여기에 씁니다.
#  컨트롤러나 뷰에는 절대 쓰지 않습니다.
# ============================================================================

MAX_TEXT = 280
MAX_AUTHOR = 40
MAX_REPLY_DEPTH = 2  # a reply is 1 deep, a reply to a reply is 2 deep, and nothing goes deeper / 답글은 깊이 1, 답글의 답글은 깊이 2, 그보다 깊어지지 않음


class RuleBroken(Exception):
    """A post broke one of the rules. The message says which rule.

    글이 규칙 하나를 어겼습니다. 메시지가 어느 규칙인지 말해 줍니다.
    """


def connect(db_path):
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row  # so a row can be read as row["author"]
    connection.execute("PRAGMA foreign_keys = ON")  # a post must point at a real user / 글은 실제로 있는 사용자를 가리켜야 함
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
        # 답글 기능 전에 만든 데이터베이스. 새 칸을 더하고 글은 그대로 둡니다.
        connection.execute("ALTER TABLE posts ADD COLUMN reply_to INTEGER REFERENCES posts(id)")
    # The pair (post_id, user_id) is the key, so the database itself refuses a second like.
    # (post_id, user_id) 짝이 키이므로, 데이터베이스 스스로 두 번째 좋아요를 거절합니다.
    connection.execute("CREATE TABLE IF NOT EXISTS likes ("
                       "post_id INTEGER NOT NULL REFERENCES posts(id), "
                       "user_id INTEGER NOT NULL REFERENCES users(id), "
                       "PRIMARY KEY (post_id, user_id))")
    # Who follows whom. The pair is the key, so one user can follow another only once.
    # 누가 누구를 팔로우하는지. 짝이 키이므로, 한 사용자는 다른 사용자를 한 번만 팔로우할 수 있습니다.
    connection.execute("CREATE TABLE IF NOT EXISTS follows ("
                       "follower_id INTEGER NOT NULL REFERENCES users(id), "
                       "followed_id INTEGER NOT NULL REFERENCES users(id), "
                       "PRIMARY KEY (follower_id, followed_id))")
    connection.commit()
    connection.close()


# Each post, with its author's name looked up in users, and its likes counted.
# The view reads row["author"] and row["likes"]. The number of likes is not stored
# anywhere: it is counted from the likes table each time, so it is always right.
# 각 글에, users에서 찾은 작성자 이름과 좋아요 수를 붙여서. 뷰는 row["author"]와
# row["likes"]를 읽습니다. 좋아요 수는 어디에도 저장하지 않습니다: 매번 likes 표에서
# 세므로 언제나 정확합니다.
POSTS_WITH_AUTHORS = ("SELECT posts.id, users.name AS author, posts.text, posts.posted_at, "
                      "posts.reply_to, "
                      "(SELECT COUNT(*) FROM likes WHERE likes.post_id = posts.id) AS likes "
                      "FROM posts JOIN users ON users.id = posts.author_id")

# The same posts, joined to the post that started their conversation: the post itself,
# or the post it answers, or the post that one answers. A reply is at most 2 deep, so two
# steps always reach the start. "parent" and "grandparent" are empty for a post that is not a reply.
# 같은 글들에, 그 대화를 시작한 글을 붙인 것: 글 자신이거나, 답하는 글이거나, 그 글이 답하는 글.
# 답글은 최대 깊이 2이므로, 두 단계면 항상 시작 글에 닿습니다. 답글이 아닌 글에서는
# "parent"와 "grandparent"가 비어 있습니다.
POSTS_WITH_STARTER = (POSTS_WITH_AUTHORS +
                      " LEFT JOIN posts AS parent ON parent.id = posts.reply_to"
                      " LEFT JOIN posts AS grandparent ON grandparent.id = parent.reply_to")

# The following timeline: a conversation is shown if the user who started it is someone
# this name follows, or this name itself. Every reply in that conversation comes along.
# 팔로우 타임라인: 대화를 시작한 사용자가 이 이름이 팔로우하는 사람이거나 이 이름 자신이면
# 그 대화를 보여 줍니다. 그 대화의 모든 답글이 함께 옵니다.
STARTED_BY_SOMEONE_FOLLOWED = (
    "COALESCE(grandparent.author_id, parent.author_id, posts.author_id) IN ("
    "SELECT follows.followed_id FROM follows JOIN users AS follower ON follower.id = follows.follower_id "
    "WHERE follower.name = ? UNION SELECT id FROM users WHERE name = ?)")


def check_name(author):
    """Return the name without extra spaces, or raise RuleBroken. A post and a like both need one.

    앞뒤 공백을 뺀 이름을 돌려주거나, RuleBroken을 일으킵니다. 글과 좋아요 모두 이름이 필요합니다.
    """
    author = author.strip() if isinstance(author, str) else ""
    if author == "":
        raise RuleBroken("The name must not be empty.")
    if len(author) > MAX_AUTHOR:
        raise RuleBroken(f"The name must be {MAX_AUTHOR} characters or fewer.")
    return author


def check_rules(author, text):
    """Return the author and text without extra spaces, or raise RuleBroken.

    앞뒤 공백을 뺀 이름과 글을 돌려주거나, RuleBroken을 일으킵니다.
    """
    author = check_name(author)
    text = text.strip() if isinstance(text, str) else ""
    if text == "":
        raise RuleBroken("The post must not be empty.")
    if len(text) > MAX_TEXT:
        raise RuleBroken(f"The post must be {MAX_TEXT} characters or fewer.")
    return author, text


def user_id_for(connection, name):
    """Return the id of the user with this name, adding the user the first time.

    이 이름을 가진 사용자의 id를 돌려줍니다. 처음 보는 이름이면 사용자를 추가합니다.
    """
    row = connection.execute("SELECT id FROM users WHERE name = ?", (name,)).fetchone()
    if row is not None:
        return row["id"]
    return connection.execute("INSERT INTO users (name) VALUES (?)", (name,)).lastrowid


def check_post_id(connection, post_id, doing):
    """Return post_id if it is the id of a post that exists, or raise RuleBroken.

    `doing` says what the post is wanted for, in the message: "replying to" or "liking".

    post_id가 실제로 있는 글의 id이면 그대로 돌려주고, 아니면 RuleBroken을 일으킵니다.
    `doing`은 메시지에서 그 글을 무엇에 쓰려는지 말합니다: "replying to"(답글) 또는 "liking"(좋아요).
    """
    # In Python, True and False count as whole numbers, so they are refused by name.
    # 파이썬에서 True와 False는 정수로 치므로, 따로 이름을 대서 거절합니다.
    if isinstance(post_id, bool) or not isinstance(post_id, int):
        raise RuleBroken(f"The post you are {doing} must be named by its id, a whole number.")
    try:
        row = connection.execute("SELECT id FROM posts WHERE id = ?", (post_id,)).fetchone()
    except OverflowError:  # a number too large for the database is not a post either / 데이터베이스에 담기엔 너무 큰 수도 글이 아님
        row = None
    if row is None:
        raise RuleBroken(f"The post you are {doing} does not exist.")
    return post_id


def depth_of(connection, post_id):
    """Return how deep a post is: 0 for a post, 1 for a reply, 2 for a reply to a reply.

    Return None if there is no post with this id.

    글의 깊이를 돌려줍니다: 글은 0, 답글은 1, 답글의 답글은 2.
    이 id를 가진 글이 없으면 None을 돌려줍니다.
    """
    find = "SELECT reply_to FROM posts WHERE id = ?"
    try:
        row = connection.execute(find, (post_id,)).fetchone()
    except OverflowError:  # a number too large for the database is not a post either / 데이터베이스에 담기엔 너무 큰 수도 글이 아님
        row = None
    if row is None:
        return None
    depth = 0
    while row["reply_to"] is not None:  # walk up, one answered post at a time / 답한 글을 따라 한 단계씩 위로
        depth += 1
        row = connection.execute(find, (row["reply_to"],)).fetchone()
    return depth


def check_reply_to(connection, reply_to):
    """Return the id of the post being answered (None for a new post), or raise RuleBroken.

    The post being answered may be a reply itself: that is a reply to a reply.
    A reply to a reply cannot be answered, so replies stop at MAX_REPLY_DEPTH.

    답하려는 글의 id를 돌려주거나(새 글이면 None), RuleBroken을 일으킵니다.
    답하려는 글이 답글일 수도 있습니다: 그것이 답글의 답글입니다.
    답글의 답글에는 답할 수 없으므로, 답글은 MAX_REPLY_DEPTH에서 멈춥니다.
    """
    if reply_to is None:
        return None
    check_post_id(connection, reply_to, "replying to")
    if depth_of(connection, reply_to) >= MAX_REPLY_DEPTH:
        raise RuleBroken(f"Replies go only {MAX_REPLY_DEPTH} levels deep, "
                         "so this reply cannot be answered.")
    return reply_to


def save_post(db_path, author, text, reply_to=None):
    """Check the rules, save the post, and return the saved row.

    `reply_to` is the id of the post this one answers, or None for a new post.

    규칙을 검사하고, 글을 저장하고, 저장된 줄을 돌려줍니다.
    `reply_to`는 이 글이 답하는 글의 id이고, 새 글이면 None입니다.
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
        connection.close()  # also when a rule was broken / 규칙을 어겼을 때도


def save_like(db_path, author, post_id):
    """Check the rules, save that this user likes this post, and return the post row.

    The row carries the new number of likes. A user is known by name, as for a post.

    규칙을 검사하고, 이 사용자가 이 글을 좋아한다고 저장하고, 그 글의 줄을 돌려줍니다.
    돌려주는 줄에는 새 좋아요 수가 들어 있습니다. 사용자는 글과 마찬가지로 이름으로 알아봅니다.
    """
    author = check_name(author)
    connection = connect(db_path)
    try:
        check_post_id(connection, post_id, "liking")
        user_id = user_id_for(connection, author)
        already = connection.execute("SELECT 1 FROM likes WHERE post_id = ? AND user_id = ?",
                                     (post_id, user_id)).fetchone()
        if already is not None:
            raise RuleBroken("You already like this post.")
        connection.execute("INSERT INTO likes (post_id, user_id) VALUES (?, ?)", (post_id, user_id))
        connection.commit()
        return connection.execute(POSTS_WITH_AUTHORS + " WHERE posts.id = ?", (post_id,)).fetchone()
    finally:
        connection.close()  # a broken rule throws away the unsaved user too / 규칙을 어기면 저장 전인 사용자도 버려짐


def save_follow(db_path, author, followed):
    """Check the rules, save that this user follows that user, and return the names this user follows.

    Both are names. The one being followed must be someone the timeline knows already.

    규칙을 검사하고, 이 사용자가 저 사용자를 팔로우한다고 저장하고, 이 사용자가 팔로우하는 이름들을 돌려줍니다.
    둘 다 이름입니다. 팔로우받는 쪽은 타임라인이 이미 아는 사람이어야 합니다.
    """
    author = check_name(author)
    followed = check_name(followed)
    if author == followed:
        raise RuleBroken("You cannot follow yourself.")
    connection = connect(db_path)
    try:
        row = connection.execute("SELECT id FROM users WHERE name = ?", (followed,)).fetchone()
        if row is None:
            raise RuleBroken(f"There is no one called {followed} here.")
        followed_id = row["id"]
        follower_id = user_id_for(connection, author)
        already = connection.execute("SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?",
                                     (follower_id, followed_id)).fetchone()
        if already is not None:
            raise RuleBroken(f"You already follow {followed}.")
        connection.execute("INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)",
                           (follower_id, followed_id))
        connection.commit()
        return names_followed_by(connection, author)
    finally:
        connection.close()  # a broken rule throws away the unsaved user too / 규칙을 어기면 저장 전인 사용자도 버려짐


def names_followed_by(connection, name):
    """Return the names this name follows, in alphabetical order. Each row has a "name".

    이 이름이 팔로우하는 이름들을 가나다순으로 돌려줍니다. 각 줄에 "name"이 있습니다.
    """
    return connection.execute(
        "SELECT followed.name FROM follows "
        "JOIN users AS follower ON follower.id = follows.follower_id "
        "JOIN users AS followed ON followed.id = follows.followed_id "
        "WHERE follower.name = ? ORDER BY followed.name", (name,)).fetchall()


def following_names(db_path, name):
    """The same, opening the database first. A name the timeline does not know follows no one.

    같은 일을 하되, 데이터베이스를 먼저 엽니다. 타임라인이 모르는 이름은 아무도 팔로우하지 않습니다.
    """
    name = name.strip() if isinstance(name, str) else ""
    connection = connect(db_path)
    rows = names_followed_by(connection, name)
    connection.close()
    return rows


def like_counts(db_path):
    """Return (post_id, likes) for every post that has at least one like, by post id.

    좋아요가 하나 이상 있는 글마다 (post_id, likes)를 글 id 순서로 돌려줍니다.
    """
    connection = connect(db_path)
    rows = connection.execute("SELECT post_id, COUNT(*) AS likes FROM likes "
                              "GROUP BY post_id ORDER BY post_id").fetchall()
    connection.close()
    return rows


def posts_after(db_path, after, following=None):
    """Return every post with an id larger than `after`, replies too, oldest first.

    With `following`, a name, return only the conversations started by someone that name
    follows, or by that name itself. That is the following timeline.

    id가 `after`보다 큰 글을 모두, 답글까지 포함해서, 오래된 것부터 돌려줍니다.
    `following`에 이름을 주면, 그 이름이 팔로우하는 사람이나 그 이름 자신이 시작한 대화만
    돌려줍니다. 그것이 팔로우 타임라인입니다.
    """
    connection = connect(db_path)
    if following is None:
        rows = connection.execute(POSTS_WITH_AUTHORS + " WHERE posts.id > ? ORDER BY posts.id",
                                  (after,)).fetchall()
    else:
        following = following.strip()
        rows = connection.execute(POSTS_WITH_STARTER + " WHERE posts.id > ? AND " +
                                  STARTED_BY_SOMEONE_FOLLOWED + " ORDER BY posts.id",
                                  (after, following, following)).fetchall()
    connection.close()
    return rows


# ============================================================================
#  VIEW
#  Turns database rows into the JSON the page reads.
#  뷰
#  데이터베이스의 줄을 화면이 읽는 JSON으로 바꿉니다.
# ============================================================================

def post_to_json(row):
    # reply_to is the id of the post this one answers. It is None for a post that is not a reply.
    # likes is how many users like the post.
    # reply_to는 이 글이 답하는 글의 id입니다. 답글이 아니면 None입니다.
    # likes는 이 글을 좋아하는 사용자의 수입니다.
    return {"id": row["id"], "author": row["author"], "text": row["text"],
            "posted_at": row["posted_at"], "reply_to": row["reply_to"], "likes": row["likes"]}


def posts_to_json(rows):
    return [post_to_json(row) for row in rows]


def like_counts_to_json(rows):
    """The number of likes of each liked post, so a window can keep its counts fresh.

    좋아요가 있는 글마다 그 수. 각 창이 자기 숫자를 최신으로 유지하는 데 씁니다.
    """
    return [{"post_id": row["post_id"], "likes": row["likes"]} for row in rows]


def names_to_json(rows):
    """A list of names, for who someone follows.

    누구를 팔로우하는지 보여 주는 이름 목록.
    """
    return [row["name"] for row in rows]


def post_to_log_line(row):
    """One line for the terminal: when the post was written, who wrote it, and what it says.

    터미널에 찍을 한 줄: 언제 썼는지, 누가 썼는지, 무슨 내용인지.
    """
    return f"{row['posted_at']}  {row['author']}: {row['text']}"


# ============================================================================
#  Starting the server
#  서버 켜기
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
