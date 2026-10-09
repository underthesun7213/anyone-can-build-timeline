# Design doc — Timeline

*Every name and example row here is made up.*

---

*The product spec*

## 1. The problem

When two people use the same app, each needs to see what the other posted. A page that keeps
everything in the browser cannot do that: each person's device keeps its own copy. Timeline is a
small Twitter-like app built to show the difference. One version keeps everything in the page, and
the other has a backend that every window shares.

## 2. Not in this version

- No accounts, passwords or sign-in. Each window types a display name.
- No deleting or editing. They are left for whoever extends the app.
- No taking a like or a follow back. Once given, they stay.
- No replies deeper than a reply to a reply.
- No pictures. A picture needs a second kind of storage for its files, which is a design of its own.
- No realtime connection (no WebSockets). The page asks for new posts once a second.
- Nothing reachable from another machine. The server listens on `127.0.0.1` only.
- No libraries, no install, no build step.

## 3. Screens

One screen, the same in both versions:

- **The timeline.** A name field at the top, a *What is happening?* box with a live count
  (*x / 280*) and a **Post** button, and the timeline below it, newest first (author, text, time).
  Its one job: show everyone's posts, and take a new one.
- **Replies.** Each post has a **Reply** button. Pressing it opens a small reply form under that
  post: a name field, a box with its own live count, a **Send** button and a **Cancel** button. The
  name field holds the same name as the one at the top: typing in either changes both. Pressing
  **Reply** again, or **Cancel**, closes the form. There is one reply form, so opening it under
  another post closes it under the first. The top box only takes new posts. A reply has a **Reply**
  button too, so a reply can be answered. A reply to a reply has no button: it cannot be answered.
  Replies sit under the post they answer, oldest first, each level moved in one step.
- **Likes.** Each post has a **Like** button and, next to it, how many people like it. Pressing it
  likes the post under the name at the top of the page. A second press by the same name is refused,
  and the reason shows next to the button.
- **Follows.** Next to the name on each post is a **Follow** button. Pressing it makes the name at
  the top follow that person; the button then says **Following** on every post by them. Above the
  timeline, a switch, **Only the people I follow**, shows just the conversations started by the
  people the name at the top follows, and by that name itself, with all their replies.

Large type and high contrast, so that it can be read from across a room.

---

*The engineering design*

## 4. The three parts

```
the browser                          the server                   the store
index.html · style.css · app.js  ──  server.py  ──────────────────  timeline.db
         a new post, "anything new?" ▶          save this, give me the newest ▶
         ◀ saved, the newest posts               ◀ the rows
```

| Part | `page-only/` | `with-backend/` |
|---|---|---|
| **Frontend** (runs on the user's device) | `index.html` · `style.css` · `app.js` | the same three files; `app.js` talks to the server instead of the browser |
| **Backend** (runs on the server) | none: the rules run in `app.js` | `server.py`, Python 3 standard library (`http.server`), written in three labelled parts: **controller · model · view** |
| **Data** (runs on the server) | the browser's `sessionStorage` | `timeline.db`, one SQLite file with four tables, `users`, `posts`, `likes` and `follows`, created by the server when it starts |

**Technologies, and why each one.**

- **Plain HTML, CSS and JavaScript.** Three files, each with one job: structure, looks, behaviour.
- **Python 3 standard library only** (`http.server`, `sqlite3`, `json`). Python ships on a Mac, so
  there is nothing to install. The code avoids anything newer than Python 3.9.
- **SQLite.** One file, no database server of its own, and the `sqlite3` command can open it.
- **Polling, once a second.** `fetch('/posts?after=<last id>')` on a timer: each window asks the
  server *anything new?* It is the simplest thing that works.
- **`sessionStorage`, not `localStorage`, for the page-only version.** Two normal windows of one
  browser share `localStorage`, which would make the page-only version look shared. `sessionStorage`
  belongs to one window, as each person's phone has its own storage, and it survives a reload.

**The interfaces.**

| Request | What goes in | What comes out |
|---|---|---|
| `POST /posts` | `{"author": "Aiko", "text": "the library is open late tonight"}` · a reply adds `"reply_to": 12`, the `id` of the post it answers | the saved post, with its `id`, `posted_at` and `reply_to` · or `400` with the rule it broke |
| `GET /posts?after=12` | the last `id` this window has · `&following=Aiko` asks for Aiko's following timeline | every post with a larger `id`, replies too, oldest first; each with its number of `likes` · with `following`, only the conversations started by someone Aiko follows, or by Aiko |
| `POST /likes` | `{"author": "Ben", "post_id": 12}` | the liked post, with its new number of `likes` · or `400` with the rule it broke |
| `GET /likes` | nothing | `{"post_id", "likes"}` for every post that has at least one like, so a window can keep its counts fresh |
| `POST /follows` | `{"author": "Aiko", "follow": "Ben"}` | every name Aiko follows now, as a list · or `400` with the rule it broke |
| `GET /follows?by=Aiko` | a name | every name Aiko follows, as a list |
| `GET /` and the three files | nothing | the page |

**The model's rules:** text is not empty after trimming · text is at most 280 characters · author
is not empty, at most 40 characters · a reply answers a post that exists · replies go at most 2
deep, so a reply to a reply cannot be answered · a like names a post that exists · one name likes
one post only once · a follow names someone the timeline knows · nobody follows themselves · one
name follows another only once. The server checks them even though the page checks for an empty
post too, and shows no **Reply** button on a reply to a reply, because a user can change anything
that runs on their own device.

## 5. The data model

Four tables:

| `users` | |
|---|---|
| `id` | integer, primary key, given by SQLite |
| `name` | text, the display name, unique |

| `posts` | |
|---|---|
| `id` | integer, primary key, given by SQLite |
| `author_id` | integer, foreign key: the `id` of a row in `users` |
| `text` | text |
| `posted_at` | text, `HH:MM`, local time |
| `reply_to` | integer, foreign key: the `id` of the post this one answers · empty for a post that is not a reply |

| `likes` | |
|---|---|
| `post_id` | integer, foreign key: the `id` of the liked post |
| `user_id` | integer, foreign key: the `id` of the user who likes it |

| `follows` | |
|---|---|
| `follower_id` | integer, foreign key: the `id` of the user who follows |
| `followed_id` | integer, foreign key: the `id` of the user being followed |

The pair (`post_id`, `user_id`) is the primary key of `likes`. A like has no `id` of its own: the
public interfaces of X and Facebook name a like by its user and its post, never by a like id, and
the same pair is what makes "only once" true. The number of likes of a post is not a column: it is
counted from `likes` each time, so the fact is kept in one place.

Example rows: `users` `1 · Aiko` · `2 · Ben` · `posts` `1 · 1 · the library is open late tonight ·
15:42 · (empty)` · `2 · 2 · until when? · 15:42 · 1` · `3 · 1 · until ten · 15:43 · 2` · `likes`
`1 · 2` · `3 · 2`: Ben likes posts 1 and 3 · `follows` `2 · 1`: Ben follows Aiko.

The pair (`follower_id`, `followed_id`) is the primary key of `follows`, as with likes. The
following timeline is not stored either: it is a query. A conversation is shown if the user who
started it is followed by the viewer, or is the viewer. The post that started a conversation is
the post itself, or the post it answers, or the post that one answers; a reply is at most 2 deep,
so two steps always reach it. Choosing the conversation, and not each post, keeps every thread
whole: a reply never appears without the post it answers.

A reply is a post, so there is no third table. Post 2 answers post 1, and post 3 answers post 2: a
reply to a reply. Nothing can answer post 3. The depth of a post is not saved: the model counts it
by walking up `reply_to`, so the fact is kept in one place. A reply always has a larger `id` than
the post it answers, so a window that reads the posts oldest first has every post on the screen
before its replies arrive.

There are no accounts, so a user is found by name: the first post with a new name adds that person
to `users`, and every later post with the same name points at the same row. Each name is kept once,
and each post points at its author by number.

## 6. How I will know it works

1. When a post is sent with text, it should come back with an `id` and a time, and the same name
   should always point at the same user.
2. When a window asks for posts after an `id`, it should get only newer posts, oldest first.
   When a reply is sent, it should come back pointing at the post it answers, and a reply to a
   reply should be saved the same way. When a like is sent, the post should come back with one
   more like, and every window should show the new count within a second. When a follow is sent,
   the names followed should come back, and the following timeline should hold the conversations
   started by those names and by the viewer, and no others.
3. When two windows are open on the backend version, a post from one should appear in the other
   within a second.
4. **And when it goes wrong:** when a post is empty, or longer than 280 characters, or answers a
   post that does not exist, or answers a reply to a reply, or when a name likes a post it likes
   already, or follows itself, or follows someone twice, or follows a name the timeline has never
   seen, the server should refuse it and say which rule it broke. When the server is stopped, the page should say
   *Cannot reach the server*, and recover by itself when the server starts again.

Sentences 1 and 2, and the first half of 4, are checked by `make test`. Sentence 3 and the second
half of 4 are browser behaviour, and are checked by hand, in two windows.

---

## 7. Adversarial review

| Objection | About | Decision | Why | What changed |
|---|---|---|---|---|
| Two normal windows share `localStorage`, so the page-only version looks shared. | design | accept | It hides the one thing the app exists to show. | The page-only version uses `sessionStorage`. |
| The error message says "280" even if the limit is changed. | design | accept | A rule should be written in one place. | The message reads the limit from the rule. |
| The author's name is copied into every post, so a rename would break old posts. | design | accept | One fact, one place, even without accounts. | A `users` table; each post points at its author by `author_id`. |
| Pictures would make posts more realistic. | product | reject | A picture needs file storage as well as the database. | Nothing; section 2 says so. |
| The page should check every rule, not only an empty post. | design | reject | The server is where the rules count, and a long post shows the server refusing it. | Nothing. |

## 8. Build or borrow

- **Built:** the page, the server and the data model.
- **Borrowed:** Python and its standard library, SQLite (which comes with Python), and the browser.

---

## Files

```
README.md            what it is, how to run it, things to try
AGENTS.md            what each file does, for an AI agent working here
DESIGN.md            this document
Makefile             make run · make test · make reset
.claude/launch.json  starts the backend version from the Claude Code desktop app
page-only/           open index.html; nothing to start
  index.html  style.css  app.js
with-backend/        make run, then http://localhost:8009
  index.html  style.css  app.js
  server.py          controller · model · view, labelled
  test_server.py     unittest: the rules, saving, replies, likes, follows, "after", real round trips
```

`timeline.db` is created next to `server.py` and is git-ignored. `make reset` deletes it.
