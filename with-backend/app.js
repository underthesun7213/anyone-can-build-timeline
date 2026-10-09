// Timeline, the version WITH a backend.
//
// This page keeps nothing itself. It sends each new post and each like to the
// server (server.py), and every second it asks the server: "anything new?"
// Because every window asks the same server, every window sees every post.
// Timeline, 백엔드가 있는 버전.
//
// 이 화면은 스스로 아무것도 보관하지 않습니다. 새 글과 좋아요를 서버(server.py)에
// 보내고, 1초마다 서버에 묻습니다: "새로운 것 있어?"
// 모든 창이 같은 서버에 묻기 때문에, 모든 창이 모든 글을 봅니다.

const MAX_TEXT = 280;
const MAX_REPLY_DEPTH = 2; // a reply is 1 deep, a reply to a reply is 2 deep, and nothing goes deeper / 답글은 깊이 1, 답글의 답글은 깊이 2, 그보다 깊어지지 않음
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
const followingOnly = document.getElementById("following-only");

// The name whose following timeline is on the screen, while the switch is on. "" otherwise.
// 스위치가 켜져 있는 동안 화면에 있는 팔로우 타임라인의 주인 이름. 아니면 "".
let viewer = "";

// The id of the newest post this window has shown. 0 means "none yet".
// 이 창이 보여 준 가장 새 글의 id. 0은 "아직 없음"입니다.
let lastId = 0;

// The id of the post that has the reply form open under it. null means the reply form is closed.
// 답글 폼이 아래에 열려 있는 글의 id. null이면 답글 폼이 닫혀 있다는 뜻입니다.
let replyTo = null;

// The Reply button that opened the reply form, or null while the form is closed.
// 답글 폼을 연 Reply 버튼. 폼이 닫혀 있는 동안은 null입니다.
let openButton = null;

// For each post on the screen that can be answered, the list that holds its replies.
// The key is the id of the post.
// 화면에 있는 글 중 답할 수 있는 글마다, 그 답글들이 들어갈 목록. 키는 글의 id입니다.
const replyLists = new Map();

// For each post on the screen, how deep it is: 0 for a post, 1 for a reply, 2 for a reply to a reply.
// 화면에 있는 글마다 그 깊이: 글은 0, 답글은 1, 답글의 답글은 2.
const depths = new Map();

// For each post on the screen, the line that shows how many users like it. The key is the id of the post.
// 화면에 있는 글마다, 몇 명이 좋아하는지 보여 주는 줄. 키는 글의 id입니다.
const likeCounts = new Map();

// For each name on the screen, its Follow buttons: one on every post by that person.
// 화면에 있는 이름마다 그 Follow 버튼들. 그 사람의 글마다 하나씩 있습니다.
const followButtons = new Map();

// Put one post on the screen: a reply under the post it answers,
// and any other post at the top of the timeline, so the newest is always first.
// 글 하나를 화면에 놓습니다: 답글은 답하는 글 아래에,
// 그 밖의 글은 타임라인 맨 위에. 그래서 가장 새 글이 항상 먼저 옵니다.
function showPost(post) {
  // Skip a post this window already shows.
  // 이 창이 이미 보여 주는 글은 건너뜁니다.
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

  // A problem with a like or a follow is shown here, under the post.
  // 좋아요나 팔로우의 문제는 여기, 글 아래에 보여 줍니다.
  const note = document.createElement("span");
  note.className = "post-note";
  note.setAttribute("role", "status");

  // Follow, next to the name. Every post by the same person gets one.
  // 이름 옆의 Follow. 같은 사람의 글마다 하나씩 있습니다.
  const followButton = document.createElement("button");
  followButton.type = "button";
  followButton.className = "small-button follow-button";
  followButton.textContent = "Follow";
  followButton.addEventListener("click", function () {
    follow(post.author, note);
  });
  if (!followButtons.has(post.author)) {
    followButtons.set(post.author, []);
  }
  followButtons.get(post.author).push(followButton);

  const text = document.createElement("p");
  text.className = "post-text";
  text.textContent = post.text;

  // textContent, never innerHTML: a post is shown as words, so it cannot run code on the page.
  // innerHTML이 아니라 textContent: 글은 글자로만 보이므로, 화면에서 코드를 실행할 수 없습니다.
  item.append(author, time, followButton, text);

  // A reply goes under the post it answers, oldest first, like a conversation.
  // That post can be a reply too. A post that is not a reply goes on top of the timeline.
  // 답글은 답하는 글 아래에, 대화처럼 오래된 것부터 놓입니다.
  // 그 글이 답글일 수도 있습니다. 답글이 아닌 글은 타임라인 맨 위로 갑니다.
  const parentList = replyLists.get(post.reply_to);
  let depth = 0;
  if (parentList) {
    depth = depths.get(post.reply_to) + 1;
    parentList.append(item);
  } else {
    timeline.prepend(item);
  }
  depths.set(post.id, depth);

  // The row under the post: Like, how many like it, Reply, and a note for a refused like.
  // 글 아래의 한 줄: Like, 좋아요 수, Reply, 그리고 거절된 좋아요의 설명.
  const actions = document.createElement("div");
  actions.className = "post-actions";

  const likeButton = document.createElement("button");
  likeButton.type = "button";
  likeButton.className = "small-button";
  likeButton.textContent = "Like";
  likeButton.addEventListener("click", function () {
    like(post, note);
  });

  const likes = document.createElement("span");
  likes.className = "like-count";
  likeCounts.set(post.id, likes); // so the count can be changed later / 나중에 숫자를 바꿀 수 있도록
  actions.append(likeButton, likes);
  item.append(actions); // Reply and the note join this row below / Reply와 설명은 아래에서 이 줄에 합류
  showLikeCount(post.id, post.likes);

  // A reply to a reply cannot be answered, so it gets no Reply button and no list for replies.
  // 답글의 답글에는 답할 수 없으므로, Reply 버튼도 답글 목록도 두지 않습니다.
  if (depth < MAX_REPLY_DEPTH) {
    const replyButton = document.createElement("button");
    replyButton.type = "button";
    replyButton.className = "small-button";
    replyButton.textContent = "Reply";
    // aria-expanded tells a screen reader whether the reply form is open under this post.
    // aria-expanded는 화면 낭독기에 이 글 아래에 답글 폼이 열렸는지 알려 줍니다.
    replyButton.setAttribute("aria-expanded", "false");
    replyButton.setAttribute("aria-controls", "reply-form");
    replyButton.addEventListener("click", function () {
      toggleReply(post, replyButton);
    });
    actions.append(replyButton);

    // The replies to this post will go in this list, inside the post.
    // 이 글의 답글들은 글 안의 이 목록에 들어갑니다.
    const replies = document.createElement("ol");
    replies.className = "replies";
    replyLists.set(post.id, replies);
    item.append(replies);
  }
  actions.append(note);
}

// Show how many users like a post, next to its Like button.
// 글을 좋아하는 사용자 수를 Like 버튼 옆에 보여 줍니다.
function showLikeCount(postId, count) {
  const line = likeCounts.get(postId);
  if (line) {
    line.textContent = "\u2665 " + count; // a heart, then the number / 하트, 그 다음 숫자
  }
}

// Show on every Follow button whether that person is followed already.
// `names` is who the name at the top follows.
// Follow 버튼마다 그 사람을 이미 팔로우하는지 보여 줍니다.
// `names`는 맨 위의 이름이 팔로우하는 사람들입니다.
function markFollowing(names) {
  for (const [name, buttons] of followButtons) {
    const followed = names.includes(name);
    for (const button of buttons) {
      button.textContent = followed ? "Following" : "Follow";
      button.disabled = followed;
    }
  }
}

// A Reply button was pressed. Open the reply form under that post, or close it if it is
// already open there. There is one reply form, so only one post has it open at a time.
// Reply 버튼이 눌렸습니다. 그 글 아래에 답글 폼을 열고, 이미 거기 열려 있으면 닫습니다.
// 답글 폼은 하나뿐이므로, 한 번에 한 글에만 열립니다.
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
  replyAuthorBox.value = authorBox.value; // start with the name from the top of the page / 화면 맨 위의 이름으로 시작
  button.parentElement.after(replyForm); // move the form to just under the row of buttons / 폼을 버튼 줄 바로 아래로 옮김
  replyForm.hidden = false;
  // Put the cursor where the person must write next: the name if there is none yet, or the reply.
  // 다음에 써야 할 곳에 커서를 둡니다: 이름이 아직 없으면 이름, 있으면 답글.
  if (replyAuthorBox.value.trim() === "") {
    replyAuthorBox.focus();
  } else {
    replyBox.focus();
  }
}

// Close the reply form and empty its reply box. Does nothing if it is already closed.
// 답글 폼을 닫고 답글 칸을 비웁니다. 이미 닫혀 있으면 아무것도 하지 않습니다.
function closeReply() {
  if (openButton === null) {
    return;
  }
  openButton.setAttribute("aria-expanded", "false");
  openButton.focus(); // so a person using the keyboard stays at the same post / 키보드를 쓰는 사람이 같은 글에 머물도록
  replyTo = null;
  openButton = null;
  replyForm.hidden = true;
  replyBox.value = "";
  showReplyStatus("");
  updateCount(replyBox, replyCount);
}

// Show a problem under the top form.
// 위쪽 폼 아래에 문제를 보여 줍니다.
function showStatus(words) {
  statusLine.textContent = words;
}

// Show a problem under the reply form.
// 답글 폼 아래에 문제를 보여 줍니다.
function showReplyStatus(words) {
  replyStatus.textContent = words;
}

// The live count under a box: "x / 280".
// 입력 칸 아래의 실시간 글자 수: "x / 280".
function updateCount(box, line) {
  const length = box.value.length;
  line.textContent = length + " / " + MAX_TEXT;
  line.classList.toggle("too-long", length > MAX_TEXT);
}

// Empty the timeline and start again from the first post: for another timeline.
// 다른 타임라인을 위해, 화면을 비우고 첫 글부터 다시 시작합니다.
function startOver(name) {
  viewer = name;
  lastId = 0;
  closeReply();
  timeline.replaceChildren();
  for (const map of [replyLists, depths, likeCounts, followButtons]) {
    map.clear();
  }
}

// Ask the server for every post newer than the last one we have, for the likes of every post,
// and for who the name at the top follows.
// 우리가 가진 마지막 글보다 새 글을 모두, 모든 글의 좋아요 수, 그리고 맨 위의 이름이
// 누구를 팔로우하는지 서버에 묻습니다.
async function checkForNewPosts() {
  try {
    const name = authorBox.value.trim();
    // With the switch on, the timeline belongs to one name. If the name changed, start over.
    // 스위치가 켜져 있으면 타임라인은 한 이름의 것입니다. 이름이 바뀌었으면 다시 시작합니다.
    if (followingOnly.checked && name !== viewer) {
      startOver(name);
      showStatus("");
    }
    const only = followingOnly.checked ? "&following=" + encodeURIComponent(viewer) : "";
    const response = await fetch("/posts?after=" + lastId + only);
    const posts = await response.json();
    // The server sends them oldest first. Each one goes on top, so the newest ends up first.
    // A reply always comes after the post it answers, so that post is already on the screen.
    // 서버는 오래된 것부터 보냅니다. 하나씩 맨 위에 놓으므로 가장 새 글이 맨 앞이 됩니다.
    // 답글은 항상 답하는 글 뒤에 오므로, 그 글은 이미 화면에 있습니다.
    for (const post of posts) {
      showPost(post);
    }
    // A like can be given in another window, so the counts are asked for every time.
    // 좋아요는 다른 창에서도 누를 수 있으므로, 숫자는 매번 다시 묻습니다.
    const counts = await (await fetch("/likes")).json();
    for (const count of counts) {
      showLikeCount(count.post_id, count.likes);
    }
    // Who this name follows, so that each Follow button can say "Following" when it should.
    // 이 이름이 누구를 팔로우하는지. Follow 버튼마다 필요할 때 "Following"이라고 쓰기 위해서입니다.
    const following = await (await fetch("/follows?by=" + encodeURIComponent(name))).json();
    markFollowing(following);
    // The server answered, so take away "Cannot reach the server" wherever it is shown.
    // 서버가 답했으므로, "Cannot reach the server"가 보이는 곳마다 지웁니다.
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
// 묻고, 답을 기다리고, 1초 기다리고, 다시 묻습니다. 계속.
async function keepChecking() {
  await checkForNewPosts();
  setTimeout(keepChecking, 1000);
}

// Send a new post, or a reply, to the server. Gives back true if the server saved it.
// `author` is the name from the form that was used.
// `replyToId` is the id of the post being answered, or null for a new post.
// `say` shows a problem under the form that was used.
// 새 글이나 답글을 서버에 보냅니다. 서버가 저장했으면 true를 돌려줍니다.
// `author`는 사용한 폼의 이름입니다.
// `replyToId`는 답하려는 글의 id이고, 새 글이면 null입니다.
// `say`는 사용한 폼 아래에 문제를 보여 줍니다.
async function send(author, text, replyToId, say) {
  // A quick check on the page, so the person does not wait for an answer.
  // The server checks the same rules again. Never trust only the screen:
  // anyone can send a request without using this page at all.
  // The page needs no check here for the two reply rules. A Reply button is only on a post
  // the server sent, and never on a reply to a reply. The server still checks both rules.
  // 화면에서 먼저 빠르게 검사해서, 답을 기다리지 않게 합니다.
  // 서버는 같은 규칙을 다시 검사합니다. 화면만 믿으면 안 됩니다:
  // 누구나 이 화면을 거치지 않고 요청을 보낼 수 있습니다.
  // 답글 규칙 두 가지는 여기서 검사할 필요가 없습니다. Reply 버튼은 서버가 보낸 글에만
  // 있고, 답글의 답글에는 없습니다. 그래도 서버는 두 규칙을 모두 검사합니다.
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
      // 서버가 글을 거절했습니다. 어느 규칙을 어겼는지 말해 줍니다.
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

// The Like button of a post: tell the server that the name at the top likes this post.
// `note` is where a refused like is explained, next to the button.
// 글의 Like 버튼: 맨 위의 이름이 이 글을 좋아한다고 서버에 알립니다.
// `note`는 거절된 좋아요의 이유를 버튼 옆에 보여 주는 자리입니다.
async function like(post, note) {
  try {
    const response = await fetch("/likes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: authorBox.value, post_id: post.id }),
    });
    const answer = await response.json();
    if (!response.ok) {
      // The server refused the like. It says why: no name, or this name likes the post already.
      // 서버가 좋아요를 거절했습니다. 이유를 말해 줍니다: 이름이 없거나, 이미 좋아한 글.
      note.textContent = answer.error;
      return;
    }
    note.textContent = "";
    showLikeCount(post.id, answer.likes); // the server answers with the post and its new count / 서버는 글과 새 좋아요 수로 답함
  } catch (error) {
    note.textContent = CANNOT_REACH;
  }
}

// The Follow button next to a name: tell the server that the name at the top follows that person.
// `note` is where a refused follow is explained, under the post.
// 이름 옆의 Follow 버튼: 맨 위의 이름이 그 사람을 팔로우한다고 서버에 알립니다.
// `note`는 거절된 팔로우의 이유를 글 아래에 보여 주는 자리입니다.
async function follow(name, note) {
  try {
    const response = await fetch("/follows", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ author: authorBox.value, follow: name }),
    });
    const answer = await response.json();
    if (!response.ok) {
      // The server refused the follow. It says why: no name, yourself, or followed already.
      // 서버가 팔로우를 거절했습니다. 이유를 말해 줍니다: 이름이 없거나, 자기 자신이거나, 이미 팔로우함.
      note.textContent = answer.error;
      return;
    }
    note.textContent = "";
    markFollowing(answer); // the server answers with every name followed now / 서버는 지금 팔로우하는 모든 이름으로 답함
    if (followingOnly.checked) {
      startOver(viewer); // that person's conversations belong on this timeline now / 이제 그 사람의 대화도 이 타임라인에 속함
    }
    await checkForNewPosts();
  } catch (error) {
    note.textContent = CANNOT_REACH;
  }
}

// The Post button: send what is in the top box as a new post.
// Post 버튼: 위쪽 칸의 내용을 새 글로 보냅니다.
async function sendPost(event) {
  event.preventDefault();
  if (await send(authorBox.value, textBox.value, null, showStatus)) {
    textBox.value = "";
    updateCount(textBox, countLine);
    // Saved. Ask for new posts now, instead of waiting for the next second.
    // This also brings in any post from another window that came just before ours.
    // 저장됨. 다음 1초를 기다리지 않고 지금 바로 새 글을 묻습니다.
    // 우리 글 직전에 다른 창에서 온 글도 이때 함께 들어옵니다.
    await checkForNewPosts();
  }
}

// The Send button of the reply form: send what is in it as a reply to the post above it.
// 답글 폼의 Send 버튼: 폼의 내용을 바로 위 글의 답글로 보냅니다.
async function sendReply(event) {
  event.preventDefault();
  if (await send(replyAuthorBox.value, replyBox.value, replyTo, showReplyStatus)) {
    closeReply();
    await checkForNewPosts();
  }
}

// A person has one name, shown in two boxes: at the top of the page, and in the reply form.
// Typing a name in one box copies it into the other.
// 한 사람의 이름은 하나이고, 두 칸에 보입니다: 화면 맨 위와 답글 폼.
// 한쪽 칸에 이름을 치면 다른 쪽에도 복사됩니다.
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

// The switch: everyone's posts, or only the conversations of the people I follow.
// 스위치: 모두의 글, 또는 내가 팔로우하는 사람들의 대화만.
followingOnly.addEventListener("change", async function () {
  startOver(followingOnly.checked ? authorBox.value.trim() : "");
  if (followingOnly.checked && viewer === "") {
    showStatus("Type your name first, to see the people you follow.");
  }
  await checkForNewPosts();
});

keepChecking();
