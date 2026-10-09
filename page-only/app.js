// Timeline, the PAGE-ONLY version.
//
// Everything happens inside this one browser window. There is no server.
// The rules run here, and the posts and likes are kept in this window's sessionStorage.
//
// Why sessionStorage, and not localStorage?
// localStorage is shared by every normal window of the same browser, so two
// windows could look "shared" when nothing is really shared.
// sessionStorage belongs to one window only, like each person's own phone.
// It survives a reload, but a second window starts empty and never sees
// this window's posts. That is the point of this version.
// Timeline, 화면만 있는 버전.
//
// 모든 일이 이 브라우저 창 하나 안에서 일어납니다. 서버가 없습니다.
// 규칙은 여기서 돌고, 글과 좋아요는 이 창의 sessionStorage에 보관됩니다.
//
// 왜 localStorage가 아니라 sessionStorage인가?
// localStorage는 같은 브라우저의 모든 일반 창이 함께 쓰므로, 실제로는 아무것도
// 공유되지 않는데 두 창이 "공유되는" 것처럼 보일 수 있습니다.
// sessionStorage는 창 하나만의 것입니다. 각자의 휴대폰에 저장되는 것과 같습니다.
// 새로고침에는 살아남지만, 두 번째 창은 비어 있는 채로 시작하고 이 창의 글을
// 절대 보지 못합니다. 그것이 이 버전의 요점입니다.

const MAX_TEXT = 280;
const MAX_AUTHOR = 40;
const MAX_REPLY_DEPTH = 2; // a reply is 1 deep, a reply to a reply is 2 deep, and nothing goes deeper / 답글은 깊이 1, 답글의 답글은 깊이 2, 그보다 깊어지지 않음
const STORAGE_KEY = "timeline-posts";
const LIKES_KEY = "timeline-likes";
const FOLLOWS_KEY = "timeline-follows";

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

// Read the saved posts from this window. Oldest first.
// 이 창에 저장된 글을 읽습니다. 오래된 것부터.
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

// Read the saved likes from this window. Each one is { post_id, user }: this name likes this post.
// The backend version keeps the same pairs in its likes table, with the user as a number.
// 이 창에 저장된 좋아요를 읽습니다. 각각은 { post_id, user }: 이 이름이 이 글을 좋아합니다.
// 백엔드 버전은 같은 짝을 likes 표에 두되, 사용자를 번호로 적습니다.
function loadLikes() {
  try {
    return JSON.parse(sessionStorage.getItem(LIKES_KEY)) || [];
  } catch (error) {
    return [];
  }
}

function saveLikes(likes) {
  sessionStorage.setItem(LIKES_KEY, JSON.stringify(likes));
}

// Read the saved follows from this window. Each one is { follower, followed }: two names.
// The backend version keeps the same pairs in its follows table, with both as numbers.
// 이 창에 저장된 팔로우를 읽습니다. 각각은 { follower, followed }: 이름 둘입니다.
// 백엔드 버전은 같은 짝을 follows 표에 두되, 둘 다 번호로 적습니다.
function loadFollows() {
  try {
    return JSON.parse(sessionStorage.getItem(FOLLOWS_KEY)) || [];
  } catch (error) {
    return [];
  }
}

function saveFollows(follows) {
  sessionStorage.setItem(FOLLOWS_KEY, JSON.stringify(follows));
}

// The names this name follows, in alphabetical order.
// 이 이름이 팔로우하는 이름들, 가나다순.
function followedBy(name, follows) {
  return follows
    .filter(function (one) { return one.follower === name; })
    .map(function (one) { return one.followed; })
    .sort();
}

// Who started the conversation a post is in: the author of the post, or of the post it
// answers, or of the post that one answers.
// 글이 속한 대화를 시작한 사람: 글의 작성자이거나, 답하는 글의 작성자이거나, 그 글이 답하는 글의 작성자.
function rootAuthor(post, posts) {
  let root = post;
  while (root && root.reply_to) {
    const answered = root.reply_to;
    root = posts.find(function (one) { return one.id === answered; });
  }
  return root ? root.author : post.author;
}

// How many users like a post. It is counted, never stored, so it is always right.
// 글을 좋아하는 사용자 수. 저장하지 않고 셀 뿐이므로 언제나 정확합니다.
function countLikes(postId, likes) {
  return likes.filter(function (one) { return one.post_id === postId; }).length;
}

// How deep a saved post is: 0 for a post, 1 for a reply, 2 for a reply to a reply.
// 저장된 글의 깊이: 글은 0, 답글은 1, 답글의 답글은 2.
function depthOf(id, posts) {
  let depth = 0;
  let post = posts.find(function (one) { return one.id === id; });
  while (post && post.reply_to) { // walk up, one answered post at a time / 답한 글을 따라 한 단계씩 위로
    depth += 1;
    const answered = post.reply_to;
    post = posts.find(function (one) { return one.id === answered; });
  }
  return depth;
}

// The rules. The backend version keeps the same rules in server.py.
// Returns the broken rule, or "" if every rule is kept.
// `replyTo` is the id of the post being answered, or null. `posts` is every saved post.
// 규칙들. 백엔드 버전은 같은 규칙을 server.py에 둡니다.
// 어긴 규칙을 돌려주고, 모든 규칙을 지켰으면 ""를 돌려줍니다.
// `replyTo`는 답하려는 글의 id 또는 null입니다. `posts`는 저장된 모든 글입니다.
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
  // 답글은 실제로 있는 글에 답해야 합니다. 그 글이 답글일 수도 있지만,
  // 답글의 답글에는 답할 수 없습니다.
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

// The rules for a like. Returns the broken rule, or "" if every rule is kept.
// 좋아요의 규칙들. 어긴 규칙을 돌려주고, 모든 규칙을 지켰으면 ""를 돌려줍니다.
function brokenLikeRule(name, postId, posts, likes) {
  if (name === "") {
    return "The name must not be empty.";
  }
  if (name.length > MAX_AUTHOR) {
    return "The name must be 40 characters or fewer.";
  }
  if (!posts.some(function (post) { return post.id === postId; })) {
    return "The post you are liking does not exist.";
  }
  // The pair (post, user) is the like, so one user can like one post only once.
  // (글, 사용자) 짝이 곧 좋아요이므로, 한 사용자는 한 글을 한 번만 좋아할 수 있습니다.
  if (likes.some(function (one) { return one.post_id === postId && one.user === name; })) {
    return "You already like this post.";
  }
  return "";
}

// The rules for a follow. Returns the broken rule, or "" if every rule is kept.
// `name` follows `followed`. `posts` is every saved post, `follows` every saved follow.
// 팔로우의 규칙들. 어긴 규칙을 돌려주고, 모든 규칙을 지켰으면 ""를 돌려줍니다.
// `name`이 `followed`를 팔로우합니다. `posts`는 저장된 모든 글, `follows`는 저장된 모든 팔로우입니다.
function brokenFollowRule(name, followed, posts, follows) {
  if (name === "") {
    return "The name must not be empty.";
  }
  if (name.length > MAX_AUTHOR) {
    return "The name must be 40 characters or fewer.";
  }
  if (name === followed) {
    return "You cannot follow yourself.";
  }
  // Only someone who has posted here can be followed.
  // 여기에 글을 쓴 적이 있는 사람만 팔로우할 수 있습니다.
  if (!posts.some(function (post) { return post.author === followed; })) {
    return "There is no one called " + followed + " here.";
  }
  // The pair (follower, followed) is the follow, so one person can follow another only once.
  // (팔로우하는 사람, 팔로우받는 사람) 짝이 곧 팔로우이므로, 한 사람은 다른 사람을 한 번만 팔로우할 수 있습니다.
  if (follows.some(function (one) { return one.follower === name && one.followed === followed; })) {
    return "You already follow " + followed + ".";
  }
  return "";
}

// The time now, as HH:MM.
// 지금 시각, HH:MM 형식.
function timeNow() {
  const now = new Date();
  const hours = String(now.getHours()).padStart(2, "0");
  const minutes = String(now.getMinutes()).padStart(2, "0");
  return hours + ":" + minutes;
}

// Put one post on the screen: a reply under the post it answers,
// and any other post at the top of the timeline, so the newest is always first.
// 글 하나를 화면에 놓습니다: 답글은 답하는 글 아래에,
// 그 밖의 글은 타임라인 맨 위에. 그래서 가장 새 글이 항상 먼저 옵니다.
function showPost(post) {
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
  showLikeCount(post.id, countLikes(post.id, loadLikes()));

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

// Check the rules, then save and show a new post, or a reply. Gives back true if it was saved.
// `author` is the name from the form that was used.
// `replyToId` is the id of the post being answered, or null for a new post.
// `say` shows a broken rule under the form that was used.
// 규칙을 검사한 뒤, 새 글이나 답글을 저장하고 보여 줍니다. 저장했으면 true를 돌려줍니다.
// `author`는 사용한 폼의 이름입니다.
// `replyToId`는 답하려는 글의 id이고, 새 글이면 null입니다.
// `say`는 사용한 폼 아래에 어긴 규칙을 보여 줍니다.
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
  // reply_to는 이 글이 답하는 글의 id입니다. 답글이 아니면 null입니다.
  const post = { id: posts.length + 1, author: author, text: text, posted_at: timeNow(),
                 reply_to: replyToId };
  posts.push(post);
  savePosts(posts);

  showTimeline();
  say("");
  return true;
}

// Show the saved posts again from the start: all of them, or, while the switch is on, only the
// conversations started by someone the name at the top follows, or by that name itself.
// 저장된 글을 처음부터 다시 보여 줍니다: 전부, 또는 스위치가 켜져 있는 동안은 맨 위의 이름이
// 팔로우하는 사람이나 그 이름 자신이 시작한 대화만.
function showTimeline() {
  const me = authorBox.value.trim();
  const posts = loadPosts();
  const following = followedBy(me, loadFollows());
  closeReply();
  timeline.replaceChildren();
  for (const map of [replyLists, depths, likeCounts, followButtons]) {
    map.clear();
  }
  for (const post of posts) {
    const starter = rootAuthor(post, posts);
    if (!followingOnly.checked || starter === me || following.includes(starter)) {
      showPost(post);
    }
  }
  markFollowing(following);
  // Ask for a name while the switch is on and there is none; take the question away once there is.
  // 스위치가 켜져 있는데 이름이 없으면 이름을 묻고, 이름이 생기면 그 질문을 지웁니다.
  const askForName = "Type your name first, to see the people you follow.";
  if (followingOnly.checked && me === "") {
    showStatus(askForName);
  } else if (statusLine.textContent === askForName) {
    showStatus("");
  }
}

// The Follow button next to a name: check the rules, then save that the name at the top follows
// that person. `note` is where a refused follow is explained, under the post.
// 이름 옆의 Follow 버튼: 규칙을 검사한 뒤, 맨 위의 이름이 그 사람을 팔로우한다고 저장합니다.
// `note`는 거절된 팔로우의 이유를 글 아래에 보여 주는 자리입니다.
function follow(name, note) {
  const me = authorBox.value.trim();
  const follows = loadFollows();
  const problem = brokenFollowRule(me, name, loadPosts(), follows);
  if (problem !== "") {
    note.textContent = problem;
    return;
  }
  follows.push({ follower: me, followed: name });
  saveFollows(follows);
  showTimeline(); // the Follow buttons change, and so may the timeline / Follow 버튼이 바뀌고, 타임라인도 바뀔 수 있음
}

// The Like button of a post: check the rules, then save that the name at the top likes this post.
// `note` is where a refused like is explained, next to the button.
// 글의 Like 버튼: 규칙을 검사한 뒤, 맨 위의 이름이 이 글을 좋아한다고 저장합니다.
// `note`는 거절된 좋아요의 이유를 버튼 옆에 보여 주는 자리입니다.
function like(post, note) {
  const name = authorBox.value.trim();
  const likes = loadLikes();
  const problem = brokenLikeRule(name, post.id, loadPosts(), likes);
  if (problem !== "") {
    note.textContent = problem;
    return;
  }
  likes.push({ post_id: post.id, user: name });
  saveLikes(likes);
  note.textContent = "";
  showLikeCount(post.id, countLikes(post.id, likes));
}

// The Post button: add what is in the top box as a new post.
// Post 버튼: 위쪽 칸의 내용을 새 글로 추가합니다.
function addPost(event) {
  event.preventDefault();
  if (add(authorBox.value, textBox.value, null, showStatus)) {
    textBox.value = "";
    updateCount(textBox, countLine);
  }
}

// The Send button of the reply form: add what is in it as a reply to the post above it.
// 답글 폼의 Send 버튼: 폼의 내용을 바로 위 글의 답글로 추가합니다.
function addReply(event) {
  event.preventDefault();
  if (add(replyAuthorBox.value, replyBox.value, replyTo, showReplyStatus)) {
    closeReply();
  }
}

// When the page opens, show what this window saved before a reload.
// The posts are saved oldest first, so a post is on the screen before its replies.
// 화면이 열릴 때, 새로고침 전에 이 창이 저장한 것을 보여 줍니다.
// 글은 오래된 것부터 저장되어 있으므로, 답글보다 글이 먼저 화면에 놓입니다.
showTimeline();

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
postForm.addEventListener("submit", addPost);
replyForm.addEventListener("submit", addReply);
replyCancel.addEventListener("click", closeReply);

// The switch, and a new name at the top: both can change which posts are shown and who is followed.
// 스위치와 맨 위의 새 이름: 둘 다 어떤 글을 보여 줄지, 누구를 팔로우하는지를 바꿀 수 있습니다.
followingOnly.addEventListener("change", showTimeline);
authorBox.addEventListener("change", showTimeline);
