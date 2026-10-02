// Timeline, the version WITH a backend.
//
// This page keeps nothing itself. It sends each new post to the server
// (server.py), and every second it asks the server: "anything new?"
// Because every window asks the same server, every window sees every post.

const MAX_TEXT = 280;
const MAX_REPLY_DEPTH = 2; // a reply is 1 deep, a reply to a reply is 2 deep, and nothing goes deeper
const CANNOT_REACH = "Cannot reach the server. Trying again every second.";

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

// The id of the newest post this window has shown. 0 means "none yet".
let lastId = 0;

// The id of the post that has the reply form open under it. null means the reply form is closed.
let replyTo = null;

// The Reply button that opened the reply form, or null while the form is closed.
let openButton = null;

// For each post on the screen that can be answered, the list that holds its replies.
// The key is the id of the post.
const replyLists = new Map();

// For each post on the screen, how deep it is: 0 for a post, 1 for a reply, 2 for a reply to a reply.
const depths = new Map();

// Put one post on the screen: a reply under the post it answers,
// and any other post at the top of the timeline, so the newest is always first.
function showPost(post) {
  // Skip a post this window already shows.
  if (post.id <= lastId) {
    return;
  }
  lastId = post.id;

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

// Ask the server for every post newer than the last one we have.
async function checkForNewPosts() {
  try {
    const response = await fetch("/posts?after=" + lastId);
    const posts = await response.json();
    // The server sends them oldest first. Each one goes on top, so the newest ends up first.
    // A reply always comes after the post it answers, so that post is already on the screen.
    for (const post of posts) {
      showPost(post);
    }
    // The server answered, so take away "Cannot reach the server" wherever it is shown.
    for (const line of [statusLine, replyStatus]) {
      if (line.textContent === CANNOT_REACH) {
        line.textContent = "";
      }
    }
  } catch (error) {
    showStatus(CANNOT_REACH);
  }
}

// Ask, wait for the answer, wait one second, then ask again. Forever.
async function keepChecking() {
  await checkForNewPosts();
  setTimeout(keepChecking, 1000);
}

// Send a new post, or a reply, to the server. Gives back true if the server saved it.
// `author` is the name from the form that was used.
// `replyToId` is the id of the post being answered, or null for a new post.
// `say` shows a problem under the form that was used.
async function send(author, text, replyToId, say) {
  // A quick check on the page, so the person does not wait for an answer.
  // The server checks the same rules again. Never trust only the screen:
  // anyone can send a request without using this page at all.
  // The page needs no check here for the two reply rules. A Reply button is only on a post
  // the server sent, and never on a reply to a reply. The server still checks both rules.
  if (text.trim() === "") {
    say("The post must not be empty.");
    return false;
  }

  try {
    const response = await fetch("/posts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: author, text: text, reply_to: replyToId }),
    });
    const answer = await response.json();
    if (!response.ok) {
      // The server refused the post. It says which rule was broken.
      say(answer.error);
      return false;
    }
    say("");
    return true;
  } catch (error) {
    say(CANNOT_REACH);
    return false;
  }
}

// The Post button: send what is in the top box as a new post.
async function sendPost(event) {
  event.preventDefault();
  if (await send(authorBox.value, textBox.value, null, showStatus)) {
    textBox.value = "";
    updateCount(textBox, countLine);
    // Saved. Ask for new posts now, instead of waiting for the next second.
    // This also brings in any post from another window that came just before ours.
    await checkForNewPosts();
  }
}

// The Send button of the reply form: send what is in it as a reply to the post above it.
async function sendReply(event) {
  event.preventDefault();
  if (await send(replyAuthorBox.value, replyBox.value, replyTo, showReplyStatus)) {
    closeReply();
    await checkForNewPosts();
  }
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
postForm.addEventListener("submit", sendPost);
replyForm.addEventListener("submit", sendReply);
replyCancel.addEventListener("click", closeReply);
keepChecking();
