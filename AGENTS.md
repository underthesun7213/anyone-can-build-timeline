# AGENTS.md — for the AI agent working in this repository

The person asking you may be new to programming, and may read English as a second language. Explain in short, plain sentences, and define a technical word the first time you
use it. When you change code, say which file changed and why.

## What this is

Timeline is a small app where people post short messages, and everyone's posts appear on one
timeline, newest first. A post can be answered with a reply, and a reply can be answered too, but a
reply to a reply cannot. The replies sit under the post they answer. It comes in two versions with
the same screen:

- `page-only/` runs only in the browser. It has no server, so nothing is shared between windows.
- `with-backend/` has a small Python server and a database, so every window sees every post.

## What each file does

| File | Its one job |
|---|---|
| `page-only/index.html` | The parts of the screen: name, post box, Post button, timeline, and the reply form (name, reply box, Send, Cancel) that opens under a post. |
| `page-only/style.css` | How the screen looks. |
| `page-only/app.js` | Checks the rules and keeps the posts in this window's `sessionStorage`. |
| `with-backend/index.html` | The same screen as `page-only/index.html`. |
| `with-backend/style.css` | The same look as `page-only/style.css`. |
| `with-backend/app.js` | Sends each post to the server, and asks the server for new posts every second. |
| `with-backend/server.py` | The backend, in three labelled parts: **controller**, **model**, **view**. |
| `with-backend/test_server.py` | The checks for `server.py`. |
| `with-backend/timeline.db` | The database. The server creates it when it starts. It is not in git. |
| `Makefile` | Short commands: `make run`, `make test`, `make reset`. |

The three parts of `server.py`:

- **Controller** (`TimelineHandler`): reads each request and picks what to do.
- **Model** (`check_rules`, `depth_of`, `check_reply_to`, `user_id_for`, `save_post`, `posts_after`):
  the rules a post must follow, and the database, in two tables: `users` (each person once) and `posts`
  (each post points at its author by `author_id`). A name is kept once, in `users`; never copy it into
  another table. A reply is a row in `posts` too: its `reply_to` is the `id` of the post it answers.
  For a post that is not a reply, `reply_to` is empty. Replies stop at `MAX_REPLY_DEPTH`: a reply is
  1 deep, a reply to a reply is 2 deep, and a reply to a reply cannot be answered.
- **View** (`post_to_json`, `posts_to_json`): turns database rows into the JSON the page reads.

## How to run it

- Page-only: open `page-only/index.html` in a browser. Nothing to start.
- With a backend: `make run`, then open <http://localhost:8009>. Press Ctrl+C to stop.
- Start again with an empty timeline: `make reset`.
- See what is saved: `sqlite3 with-backend/timeline.db 'select * from users; select * from posts'`

It needs only `python3` (3.9 or newer). Do not add libraries, packages or a build step.
Write code that runs on Python 3.9: no `match` statements, and no `X | Y` in type hints.

## How to test it

`make test`. Every test must pass before and after a change. A new feature gets a new test in
`with-backend/test_server.py`.

## The one rule

**Keep the three parts of `server.py` separate. A new rule goes in the model.** The controller does
not check rules and does not touch the database. The view does not decide anything. If a feature
needs a new rule, write it in the model, and check it in the page too, because the page and the
server must agree. The server always checks, even when the page already did, because a user can change anything that
runs on their own device.
