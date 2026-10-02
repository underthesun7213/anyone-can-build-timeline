// Timeline, the PAGE-ONLY version.
//
// Everything happens inside this one browser window. There is no server.
// The rules run here, and the posts are kept in this window's sessionStorage.
//
// Why sessionStorage, and not localStorage?
// localStorage is shared by every normal window of the same browser, so two
// windows could look "shared" when nothing is really shared.
// sessionStorage belongs to one window only, like each person's own phone.
// It survives a reload, but a second window starts empty and never sees
// this window's posts. That is the point of this version.

const MAX_TEXT = 280;
const MAX_AUTHOR = 40;
const MAX_REPLY_DEPTH = 2; // a reply is 1 deep, a reply to a reply is 2 deep, and nothing goes deeper
const STORAGE_KEY = "timeline-posts";

const authorBox = document.getElementById("author");
const textBox = document.getElementById("text");
const countLine = document.getElementById("count");
const statusLine = document.getElementById("status");
const timeline = document.getElementById("timeline");
const postForm = document.getElementById("post-form");
const replyForm = document.getElementById("reply-form");
const replyAuthorBox = document.getElementById("reply-author");
const replyLabel = document.getElementById("reply-label");
const replyBox = document.getElementById("reply-text");
const replyCount = document.getElementById("reply-count");
const replyStatus = document.getElementById("reply-status");
const replyCancel = document.getElementById("reply-cancel");

// The id of the post that has the reply form open under it. null means the reply form is closed.
let replyTo = null;

// The Reply button that opened the reply form, or null while the form is closed.
let openButton = null;

// For each post on the screen that can be answered, the list that holds its replies.
// The key is the id of the post.
const replyLists = new Map();

// For each post on the screen, how deep it is: 0 for a post, 1 for a reply, 2 for a reply to a reply.
const depths = new Map();

// Read the saved posts from this window. Oldest first.
function loadPosts() {
  try {
    return JSON.parse(sessionStorage.getItem(STORAGE_KEY)) || [];
  } catch (error) {
    return [];
  }
}

function savePosts(posts) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(posts));
}

// How deep a saved post is: 0 for a post, 1 for a reply, 2 for a reply to a reply.
function depthOf(id, posts) {
  let depth = 0;
  let post = posts.find(function (one) { return one.id === id; });
  while (post && post.reply_to) { // walk up, one answered post at a time
    depth += 1;
    const answered = post.reply_to;
    post = posts.find(function (one) { return one.id === answered; });
  }
  return depth;
}

// The rules. The backend version keeps the same rules in server.py.
// Returns the broken rule, or "" if every rule is kept.
// `replyTo` is the id of the post being answered, or null. `posts` is every saved post.
function brokenRule(author, text, replyTo, posts) {
  if (author === "") {
    return "The name must not be empty.";
  }
  if (author.length > MAX_AUTHOR) {
    return "The name must be 40 characters or fewer.";
  }
  if (text === "") {
    return "The post must not be empty.";
  }
  if (text.length > MAX_TEXT) {
    return "The post must be 280 characters or fewer.";
  }
  // A reply must answer a post that exists. That post can be a reply too,
  // but a reply to a reply cannot be answered.
  if (replyTo !== null) {
    if (!posts.some(function (post) { return post.id === replyTo; })) {
      return "The post you are replying to does not exist.";
    }
    if (depthOf(replyTo, posts) >= MAX_REPLY_DEPTH) {
      return "Replies go only " + MAX_REPLY_DEPTH + " levels deep, so this reply cannot be answered.";
    }
  }
  return "";
}

// The time now, as HH:MM.
function timeNow() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  return hours + ":" + minutes;
}

// Put one post on the screen: a reply under the post it answers,
// and any other post at the top of the timeline, so the newest is always first.
function showPost(post) {
  const item = document.createElement("li");
  item.className = "post";

  const author = document.createElement("span");
  author.className = "post-author";
  author.textContent = post.author;

  const time = document.createElement("span");
  time.className = "post-time";
  time.textContent = post.posted_at;

  const text = document.createElement("p");
  text.className = "post-text";
  text.textContent = post.text;

  // textContent, never innerHTML: a post is shown as words, so it cannot run code on the page.
  item.append(author, time, text);

  // A reply goes under the post it answers, oldest first, like a conversation.
  // That post can be a reply too. A post that is not a reply goes on top of the timeline.
  const parentList = replyLists.get(post.reply_to);
  let depth = 0;
  if (parentList) {
    depth = depths.get(post.reply_to) + 1;
    parentList.append(item);
  } else {
    timeline.prepend(item);
  }
  depths.set(post.id, depth);

  // A reply to a reply cannot be answered, so it gets no Reply button and no list for replies.
  if (depth < MAX_REPLY_DEPTH) {
    const replyButton = document.createElement("button");
    replyButton.type = "button";
    replyButton.className = "small-button";
    replyButton.textContent = "Reply";
    // aria-expanded tells a screen reader whether the reply form is open under this post.
    replyButton.setAttribute("aria-expanded", "false");
    replyButton.setAttribute("aria-controls", "reply-form");
    replyButton.addEventListener("click", function () {
      toggleReply(post, replyButton);
    });

    // The replies to this post will go in this list, inside the post.
    const replies = document.createElement("ol");
    replies.className = "replies";
    replyLists.set(post.id, replies);

    item.append(replyButton, replies);
  }
}

// A Reply button was pressed. Open the reply form under that post, or close it if it is
// already open there. There is one reply form, so only one post has it open at a time.
function toggleReply(post, button) {
  const wasOpenHere = replyTo === post.id;
  closeReply();
  if (wasOpenHere) {
    return;
  }
  replyTo = post.id;
  openButton = button;
  button.setAttribute("aria-expanded", "true");
  replyLabel.textContent = "Your reply to " + post.author;
  replyAuthorBox.value = authorBox.value; // start with the name from the top of the page
  button.after(replyForm); // move the form to just under this Reply button
  replyForm.hidden = false;
  // Put the cursor where the person must write next: the name if there is none yet, or the reply.
  if (replyAuthorBox.value.trim() === "") {
    replyAuthorBox.focus();
  } else {
    replyBox.focus();
  }
}

// Close the reply form and empty its reply box. Does nothing if it is already closed.
function closeReply() {
  if (openButton === null) {
    return;
  }
  openButton.setAttribute("aria-expanded", "false");
  openButton.focus(); // so a person using the keyboard stays at the same post
  replyTo = null;
  openButton = null;
  replyForm.hidden = true;
  replyBox.value = "";
  showReplyStatus("");
  updateCount(replyBox, replyCount);
}

// Show a problem under the top form.
function showStatus(words) {
  statusLine.textContent = words;
}

// Show a problem under the reply form.
function showReplyStatus(words) {
  replyStatus.textContent = words;
}

// The live count under a box: "x / 280".
function updateCount(box, line) {
  const length = box.value.length;
  line.textContent = length + " / " + MAX_TEXT;
  line.classList.toggle("too-long", length > MAX_TEXT);
}

// Check the rules, then save and show a new post, or a reply. Gives back true if it was saved.
// `author` is the name from the form that was used.
// `replyToId` is the id of the post being answered, or null for a new post.
// `say` shows a broken rule under the form that was used.
function add(author, text, replyToId, say) {
  author = author.trim();
  text = text.trim();

  const posts = loadPosts();
  const problem = brokenRule(author, text, replyToId, posts);
  if (problem !== "") {
    say(problem);
    return false;
  }

  // reply_to is the id of the post this one answers. It is null for a post that is not a reply.
  const post = { id: posts.length + 1, author: author, text: text, posted_at: timeNow(),
                 reply_to: replyToId };
  posts.push(post);
  savePosts(posts);

  showPost(post);
  say("");
  return true;
}

// The Post button: add what is in the top box as a new post.
function addPost(event) {
  event.preventDefault();
  if (add(authorBox.value, textBox.value, null, showStatus)) {
    textBox.value = "";
    updateCount(textBox, countLine);
  }
}

// The Send button of the reply form: add what is in it as a reply to the post above it.
function addReply(event) {
  event.preventDefault();
  if (add(replyAuthorBox.value, replyBox.value, replyTo, showReplyStatus)) {
    closeReply();
  }
}

// When the page opens, show what this window saved before a reload.
// The posts are saved oldest first, so a post is on the screen before its replies.
for (const post of loadPosts()) {
  showPost(post);
}

// A person has one name, shown in two boxes: at the top of the page, and in the reply form.
// Typing a name in one box copies it into the other.
authorBox.addEventListener("input", function () {
  replyAuthorBox.value = authorBox.value;
});
replyAuthorBox.addEventListener("input", function () {
  authorBox.value = replyAuthorBox.value;
});

textBox.addEventListener("input", function () {
  updateCount(textBox, countLine);
});
replyBox.addEventListener("input", function () {
  updateCount(replyBox, replyCount);
});
postForm.addEventListener("submit", addPost);
replyForm.addEventListener("submit", addReply);
replyCancel.addEventListener("click", closeReply);
