"""Tests for server.py. Run them with:  python3 -m unittest

Most tests call the MODEL directly, with a database made only for the test.
The last test starts the real server and talks to it, as the page does.

server.py의 테스트. 실행: python3 -m unittest

대부분의 테스트는 테스트용으로만 만든 데이터베이스로 모델을 직접 부릅니다.
마지막 테스트들은 진짜 서버를 켜고, 화면이 하듯이 서버와 대화합니다.
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
        # 테스트마다 임시 폴더에 새 빈 데이터베이스를 만듭니다.
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
        self.assertNotIn("author", post.keys())  # the name is kept once, in users / 이름은 users에 한 번만 보관

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
        self.assertEqual(len(server.posts_after(self.db_path, 0)), 3)  # nothing was saved / 아무것도 저장되지 않음
        # The post and the reply can still be answered.
        # 글과 답글에는 여전히 답할 수 있습니다.
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
        self.assertEqual(len(server.posts_after(self.db_path, 0)), 1)  # nothing was saved / 아무것도 저장되지 않음

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
        # posts 표를 답글 기능 전의 모양으로 만들고, 글 하나를 넣습니다.
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

    def test_a_new_post_has_no_likes(self):
        row = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        self.assertEqual(row["likes"], 0)

    def test_a_like_adds_one_to_the_likes_of_that_post(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        server.save_post(self.db_path, "Ben", "a second post")
        row = server.save_like(self.db_path, "Ben", 1)
        self.assertEqual(row["id"], 1)
        self.assertEqual(row["likes"], 1)
        rows = server.posts_after(self.db_path, 0)
        self.assertEqual([r["likes"] for r in rows], [1, 0])  # the other post is not touched / 다른 글은 건드리지 않음

    def test_the_same_user_cannot_like_the_same_post_twice(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        server.save_like(self.db_path, "Ben", 1)
        with self.assertRaises(server.RuleBroken):
            server.save_like(self.db_path, " Ben ", 1)  # the same name, with extra spaces / 같은 이름에 공백만 더한 것
        self.assertEqual(server.posts_after(self.db_path, 0)[0]["likes"], 1)

    def test_two_users_can_like_the_same_post(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        server.save_like(self.db_path, "Ben", 1)
        row = server.save_like(self.db_path, "Chloe", 1)
        self.assertEqual(row["likes"], 2)

    def test_a_user_can_like_their_own_post(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        self.assertEqual(server.save_like(self.db_path, "Aiko", 1)["likes"], 1)

    def test_a_like_needs_a_name(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        for bad_name in ("", "   ", None, "a" * 41):
            with self.assertRaises(server.RuleBroken):
                server.save_like(self.db_path, bad_name, 1)

    def test_a_like_on_a_post_that_does_not_exist_is_refused(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        for missing in (99, 0, -1, 10 ** 30, "1", 1.0, True, None):
            with self.assertRaises(server.RuleBroken):
                server.save_like(self.db_path, "Ben", missing)

    def test_a_refused_like_does_not_add_its_user(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        with self.assertRaises(server.RuleBroken):
            server.save_like(self.db_path, "Ben", 99)
        connection = server.connect(self.db_path)
        users = connection.execute("SELECT name FROM users ORDER BY id").fetchall()
        connection.close()
        self.assertEqual([u["name"] for u in users], ["Aiko"])

    def test_a_like_is_the_pair_post_and_user_with_no_id_of_its_own(self):
        server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        server.save_like(self.db_path, "Ben", 1)
        connection = server.connect(self.db_path)
        like = connection.execute("SELECT * FROM likes").fetchone()
        ben = connection.execute("SELECT id FROM users WHERE name = 'Ben'").fetchone()
        connection.close()
        self.assertEqual(sorted(like.keys()), ["post_id", "user_id"])
        self.assertEqual((like["post_id"], like["user_id"]), (1, ben["id"]))

    def test_like_counts_lists_only_liked_posts(self):
        server.save_post(self.db_path, "Aiko", "first")
        server.save_post(self.db_path, "Aiko", "second")
        server.save_post(self.db_path, "Aiko", "third")
        server.save_like(self.db_path, "Ben", 3)
        server.save_like(self.db_path, "Chloe", 3)
        server.save_like(self.db_path, "Ben", 1)
        counts = server.like_counts_to_json(server.like_counts(self.db_path))
        self.assertEqual(counts, [{"post_id": 1, "likes": 1}, {"post_id": 3, "likes": 2}])

    def test_a_database_from_before_likes_gets_the_likes_table(self):
        old_path = os.path.join(self.folder.name, "old.db")
        connection = server.connect(old_path)
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        connection.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, "
                           "author_id INTEGER NOT NULL REFERENCES users(id), "
                           "text TEXT NOT NULL, posted_at TEXT NOT NULL, "
                           "reply_to INTEGER REFERENCES posts(id))")
        connection.execute("INSERT INTO users (name) VALUES ('Aiko')")
        connection.execute("INSERT INTO posts (author_id, text, posted_at) VALUES (1, 'old', '09:00')")
        connection.commit()
        connection.close()

        server.create_tables(old_path)

        self.assertEqual(server.save_like(old_path, "Ben", 1)["likes"], 1)

    def test_a_follow_is_saved_and_the_names_followed_come_back_in_order(self):
        server.save_post(self.db_path, "Ben", "hello")
        server.save_post(self.db_path, "Chloe", "hi")
        server.save_follow(self.db_path, "Aiko", "Chloe")
        rows = server.save_follow(self.db_path, "Aiko", "Ben")
        self.assertEqual(server.names_to_json(rows), ["Ben", "Chloe"])
        self.assertEqual(server.names_to_json(server.following_names(self.db_path, "Aiko")),
                         ["Ben", "Chloe"])
        self.assertEqual(server.names_to_json(server.following_names(self.db_path, "Ben")), [])

    def test_a_follow_is_the_pair_follower_and_followed_with_no_id_of_its_own(self):
        server.save_post(self.db_path, "Ben", "hello")
        server.save_follow(self.db_path, "Aiko", "Ben")
        connection = server.connect(self.db_path)
        follow = connection.execute("SELECT * FROM follows").fetchone()
        aiko = connection.execute("SELECT id FROM users WHERE name = 'Aiko'").fetchone()
        ben = connection.execute("SELECT id FROM users WHERE name = 'Ben'").fetchone()
        connection.close()
        self.assertEqual(sorted(follow.keys()), ["followed_id", "follower_id"])
        self.assertEqual((follow["follower_id"], follow["followed_id"]), (aiko["id"], ben["id"]))

    def test_nobody_can_follow_themselves(self):
        server.save_post(self.db_path, "Aiko", "hello")
        with self.assertRaises(server.RuleBroken):
            server.save_follow(self.db_path, "Aiko", " Aiko ")

    def test_nobody_can_follow_the_same_person_twice(self):
        server.save_post(self.db_path, "Ben", "hello")
        server.save_follow(self.db_path, "Aiko", "Ben")
        with self.assertRaises(server.RuleBroken):
            server.save_follow(self.db_path, "Aiko", "Ben")
        self.assertEqual(server.names_to_json(server.following_names(self.db_path, "Aiko")), ["Ben"])

    def test_only_someone_the_timeline_knows_can_be_followed(self):
        with self.assertRaises(server.RuleBroken):
            server.save_follow(self.db_path, "Aiko", "Nobody")

    def test_a_follow_needs_two_names(self):
        server.save_post(self.db_path, "Ben", "hello")
        for bad_name in ("", "   ", None, "a" * 41):
            with self.assertRaises(server.RuleBroken):
                server.save_follow(self.db_path, bad_name, "Ben")
            with self.assertRaises(server.RuleBroken):
                server.save_follow(self.db_path, "Aiko", bad_name)

    def test_a_refused_follow_does_not_add_its_follower(self):
        with self.assertRaises(server.RuleBroken):
            server.save_follow(self.db_path, "Aiko", "Nobody")
        connection = server.connect(self.db_path)
        users = connection.execute("SELECT name FROM users").fetchall()
        connection.close()
        self.assertEqual(users, [])

    def test_the_following_timeline_shows_the_conversations_of_people_you_follow_and_your_own(self):
        server.save_post(self.db_path, "Ben", "Ben's post")               # 1
        server.save_post(self.db_path, "Chloe", "Chloe's post")           # 2
        server.save_post(self.db_path, "Aiko", "Aiko's own post")         # 3
        server.save_post(self.db_path, "Chloe", "Chloe answers Ben", 1)   # 4: in Ben's conversation
        server.save_post(self.db_path, "Ben", "Ben answers Chloe", 2)     # 5: in Chloe's conversation
        server.save_post(self.db_path, "Dev", "Dev answers Chloe", 4)     # 6: in Ben's conversation, 2 deep
        server.save_follow(self.db_path, "Aiko", "Ben")

        rows = server.posts_after(self.db_path, 0, "Aiko")
        self.assertEqual([row["id"] for row in rows], [1, 3, 4, 6])

        # `after` still works, and so does "nobody followed yet".
        self.assertEqual([row["id"] for row in server.posts_after(self.db_path, 3, "Aiko")], [4, 6])
        self.assertEqual([row["id"] for row in server.posts_after(self.db_path, 0, "Chloe")], [2, 5])
        self.assertEqual([row["id"] for row in server.posts_after(self.db_path, 0, "Nobody")], [])
        # Without a name, everyone's posts, as before.
        self.assertEqual(len(server.posts_after(self.db_path, 0)), 6)

    def test_a_database_from_before_follows_gets_the_follows_table(self):
        old_path = os.path.join(self.folder.name, "old.db")
        connection = server.connect(old_path)
        connection.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE)")
        connection.execute("CREATE TABLE posts (id INTEGER PRIMARY KEY, "
                           "author_id INTEGER NOT NULL REFERENCES users(id), "
                           "text TEXT NOT NULL, posted_at TEXT NOT NULL, "
                           "reply_to INTEGER REFERENCES posts(id))")
        connection.execute("INSERT INTO users (name) VALUES ('Ben')")
        connection.commit()
        connection.close()

        server.create_tables(old_path)

        self.assertEqual(server.names_to_json(server.save_follow(old_path, "Aiko", "Ben")), ["Ben"])

    def test_log_line_has_the_time_the_author_and_the_text(self):
        row = server.save_post(self.db_path, "Aiko", "the library is open late tonight")
        self.assertEqual(server.post_to_log_line(row),
                         row["posted_at"] + "  Aiko: the library is open late tonight")


class RealServerTest(unittest.TestCase):

    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        db_path = os.path.join(self.folder.name, "test.db")
        # Port 0 asks the computer for any free port.
        # 포트 0은 컴퓨터에 비어 있는 아무 포트나 달라는 뜻입니다.
        self.server = server.make_server(0, db_path)
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.folder.cleanup()

    def send(self, path, data):
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request)

    def post(self, data):
        return self.send("/posts", data)

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

    def test_like_then_get_shows_the_count(self):
        self.post({"author": "Aiko", "text": "hello"}).close()
        with self.send("/likes", {"author": "Ben", "post_id": 1}) as answer:
            self.assertEqual(answer.status, 201)
            self.assertEqual(json.loads(answer.read())["likes"], 1)
        with urllib.request.urlopen(self.base + "/posts?after=0") as answer:
            self.assertEqual(json.loads(answer.read())[0]["likes"], 1)
        with urllib.request.urlopen(self.base + "/likes") as answer:
            self.assertEqual(json.loads(answer.read()), [{"post_id": 1, "likes": 1}])

    def test_a_second_like_gets_400_and_a_reason(self):
        self.post({"author": "Aiko", "text": "hello"}).close()
        self.send("/likes", {"author": "Ben", "post_id": 1}).close()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.send("/likes", {"author": "Ben", "post_id": 1})
        self.assertEqual(caught.exception.code, 400)
        reason = json.loads(caught.exception.read())["error"]
        self.assertIn("already", reason)
        caught.exception.close()

    def test_follow_then_get_the_following_timeline(self):
        self.post({"author": "Ben", "text": "from Ben"}).close()
        self.post({"author": "Chloe", "text": "from Chloe"}).close()
        with self.send("/follows", {"author": "Aiko", "follow": "Ben"}) as answer:
            self.assertEqual(answer.status, 201)
            self.assertEqual(json.loads(answer.read()), ["Ben"])
        with urllib.request.urlopen(self.base + "/posts?after=0&following=Aiko") as answer:
            self.assertEqual([p["author"] for p in json.loads(answer.read())], ["Ben"])
        with urllib.request.urlopen(self.base + "/posts?after=0") as answer:
            self.assertEqual(len(json.loads(answer.read())), 2)
        with urllib.request.urlopen(self.base + "/follows?by=Aiko") as answer:
            self.assertEqual(json.loads(answer.read()), ["Ben"])

    def test_following_yourself_gets_400_and_a_reason(self):
        self.post({"author": "Aiko", "text": "hello"}).close()
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.send("/follows", {"author": "Aiko", "follow": "Aiko"})
        self.assertEqual(caught.exception.code, 400)
        reason = json.loads(caught.exception.read())["error"]
        self.assertIn("yourself", reason)
        caught.exception.close()

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
