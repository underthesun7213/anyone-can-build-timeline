"""Tests for server.py. Run them with:  python3 -m unittest

Most tests call the MODEL directly, with a database made only for the test.
The last test starts the real server and talks to it, as the page does.
"""

import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import server


class ModelTests(unittest.TestCase):

    def setUp(self):
        # A new, empty database for every test, in a temporary folder.
        self.folder = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.folder.name, "test.db")
        server.create_tables(self.db_path)

    def tearDown(self):
        self.folder.cleanup()

    def test_empty_text_is_refused(self):
        with self.assertRaises(server.RuleBroken):
            server.save_post(self.db_path, "Aiko", "   ")

    def test_too_long_text_is_refused(self):
        with self.assertRaises(server.RuleBroken):
            server.save_post(self.db_path, "Aiko", "a" * 281)

    def test_text_of_exactly_280_is_allowed(self):
        row = server.save_post(self.db_path, "Aiko", "a" * 280)
        self.assertEqual(len(row["text"]), 280)

    def test_empty_author_is_refused(self):
        with self.assertRaises(server.RuleBroken):
            server.save_post(self.db_path, "", "hello")

    def test_too_long_author_is_refused(self):
        with self.assertRaises(server.RuleBroken):
            server.save_post(self.db_path, "a" * 41, "hello")

    def test_saved_post_comes_back_with_id_and_time(self):
        row = server.save_post(self.db_path, " Aiko ", " the library is open late ")
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["author"], "Aiko")
        self.assertEqual(row["text"], "the library is open late")
        self.assertRegex(row["posted_at"], r"^\d\d:\d\d$")

    def test_the_same_name_is_one_user(self):
        server.save_post(self.db_path, "Aiko", "first")
        server.save_post(self.db_path, "Aiko", "second")
        server.save_post(self.db_path, "Ben", "third")
        connection = server.connect(self.db_path)
        users = connection.execute("SELECT name FROM users ORDER BY id").fetchall()
        connection.close()
        self.assertEqual([u["name"] for u in users], ["Aiko", "Ben"])

    def test_a_post_points_at_its_author_by_id(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        connection = server.connect(self.db_path)
        post = connection.execute("SELECT * FROM posts").fetchone()
        user = connection.execute("SELECT * FROM users").fetchone()
        connection.close()
        self.assertEqual(post["author_id"], user["id"])
        self.assertNotIn("author", post.keys())  # the name is kept once, in users

    def test_after_returns_only_newer_posts_oldest_first(self):
        server.save_post(self.db_path, "Aiko", "first")
        server.save_post(self.db_path, "Ben", "second")
        server.save_post(self.db_path, "Aiko", "third")
        rows = server.posts_after(self.db_path, 1)
        self.assertEqual([row["text"] for row in rows], ["second", "third"])

    def test_a_post_that_is_not_a_reply_points_at_nothing(self):
        row = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        self.assertIsNone(row["reply_to"])

    def test_a_reply_points_at_the_post_it_answers(self):
        post = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        reply = server.save_post(self.db_path, "Ben", "until when?", post["id"])
        self.assertEqual(reply["reply_to"], post["id"])

    def test_a_reply_to_a_reply_is_allowed(self):
        post = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        reply = server.save_post(self.db_path, "Ben", "until when?", post["id"])
        reply_to_reply = server.save_post(self.db_path, "Aiko", "until ten", reply["id"])
        self.assertEqual(reply_to_reply["reply_to"], reply["id"])

    def test_a_reply_to_a_reply_cannot_be_answered(self):
        post = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        reply = server.save_post(self.db_path, "Ben", "until when?", post["id"])
        reply_to_reply = server.save_post(self.db_path, "Aiko", "until ten", reply["id"])
        with self.assertRaises(server.RuleBroken):
            server.save_post(self.db_path, "Ben", "thanks", reply_to_reply["id"])
        self.assertEqual(len(server.posts_after(self.db_path, 0)), 3)  # nothing was saved
        # The post and the reply can still be answered.
        server.save_post(self.db_path, "Chloe", "good to know", post["id"])
        server.save_post(self.db_path, "Chloe", "I asked that too", reply["id"])

    def test_depth_is_0_for_a_post_1_for_a_reply_2_for_a_reply_to_a_reply(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        server.save_post(self.db_path, "Ben", "until when?", 1)
        server.save_post(self.db_path, "Aiko", "until ten", 2)
        connection = server.connect(self.db_path)
        depths = [server.depth_of(connection, post_id) for post_id in (1, 2, 3, 99)]
        connection.close()
        self.assertEqual(depths, [0, 1, 2, None])

    def test_a_reply_to_a_post_that_does_not_exist_is_refused(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        for missing in (99, 0, -1, 10 ** 30):
            with self.assertRaises(server.RuleBroken):
                server.save_post(self.db_path, "Ben", "until when?", missing)
        self.assertEqual(len(server.posts_after(self.db_path, 0)), 1)  # nothing was saved

    def test_a_reply_must_name_its_post_by_a_whole_number(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        for not_an_id in ("1", 1.0, True, [1]):
            with self.assertRaises(server.RuleBroken):
                server.save_post(self.db_path, "Ben", "until when?", not_an_id)

    def test_a_refused_reply_does_not_add_its_author(self):
        with self.assertRaises(server.RuleBroken):
            server.save_post(self.db_path, "Ben", "until when?", 99)
        connection = server.connect(self.db_path)
        users = connection.execute("SELECT name FROM users").fetchall()
        connection.close()
        self.assertEqual(users, [])

    def test_after_returns_replies_with_what_they_answer(self):
        server.save_post(self.db_path, "Aiko", "first")
        server.save_post(self.db_path, "Ben", "second", 1)
        server.save_post(self.db_path, "Aiko", "third", 2)
        posts = server.posts_to_json(server.posts_after(self.db_path, 0))
        self.assertEqual([post["reply_to"] for post in posts], [None, 1, 2])

    def test_a_database_from_before_replies_keeps_its_posts(self):
        # Make the posts table the way it was before replies, with one post in it.
        old_path = os.path.join(self.folder.name, "old.db")
        connection = server.connect(old_path)
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        connection.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, "
                           "author_id INTEGER NOT NULL REFERENCES users(id), "
                           "text TEXT NOT NULL, posted_at TEXT NOT NULL)")
        connection.execute("INSERT INTO users (name) VALUES ('Aiko')")
        connection.execute("INSERT INTO posts (author_id, text, posted_at) VALUES (1, 'old', '09:00')")
        connection.commit()
        connection.close()

        server.create_tables(old_path)

        reply = server.save_post(old_path, "Ben", "new", 1)
        self.assertEqual(reply["reply_to"], 1)
        rows = server.posts_after(old_path, 0)
        self.assertEqual([(row["text"], row["reply_to"]) for row in rows], [("old", None), ("new", 1)])

    def test_log_line_has_the_time_the_author_and_the_text(self):
        row = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        self.assertEqual(server.post_to_log_line(row),
                         row["posted_at"] + "  Aiko: the library is open late tonight")


class RealServerTest(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.folder.name, "test.db")
        # Port 0 asks the computer for any free port.
        self.server = server.make_server(0, db_path)
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.folder.cleanup()

    def post(self, data):
        request = urllib.request.Request(
            self.base + "/posts",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request)

    def test_post_then_get(self):
        answer = self.post({"author": "Aiko", "text": "hello"})
        self.assertEqual(answer.status, 201)
        with urllib.request.urlopen(self.base + "/posts?after=0") as answer:
            posts = json.loads(answer.read())
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["author"], "Aiko")
        self.assertEqual(posts[0]["text"], "hello")

    def test_empty_post_gets_400_and_a_reason(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post({"author": "Aiko", "text": ""})
        self.assertEqual(caught.exception.code, 400)
        reason = json.loads(caught.exception.read())["error"]
        self.assertIn("empty", reason)
        caught.exception.close()

    def test_reply_then_reply_to_the_reply_then_get(self):
        self.post({"author": "Aiko", "text": "hello"}).close()
        self.post({"author": "Ben", "text": "hi Aiko", "reply_to": 1}).close()
        self.post({"author": "Aiko", "text": "hi Ben", "reply_to": 2}).close()
        with urllib.request.urlopen(self.base + "/posts?after=0") as answer:
            posts = json.loads(answer.read())
        self.assertEqual([post["text"] for post in posts], ["hello", "hi Aiko", "hi Ben"])
        self.assertEqual([post["reply_to"] for post in posts], [None, 1, 2])

    def test_reply_to_a_missing_post_gets_400_and_a_reason(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post({"author": "Ben", "text": "hi", "reply_to": 99})
        self.assertEqual(caught.exception.code, 400)
        reason = json.loads(caught.exception.read())["error"]
        self.assertIn("does not exist", reason)
        caught.exception.close()

    def test_reply_to_a_reply_to_a_reply_gets_400_and_a_reason(self):
        self.post({"author": "Aiko", "text": "hello"}).close()
        self.post({"author": "Ben", "text": "hi Aiko", "reply_to": 1}).close()
        self.post({"author": "Aiko", "text": "hi Ben", "reply_to": 2}).close()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.post({"author": "Ben", "text": "one more", "reply_to": 3})
        self.assertEqual(caught.exception.code, 400)
        reason = json.loads(caught.exception.read())["error"]
        self.assertIn("cannot be answered", reason)
        caught.exception.close()


if __name__ == "__main__":
    unittest.main()
