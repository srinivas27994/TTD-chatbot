/* =========================================================
   TTD Seva Assistant - frontend logic

   Flow:
   user types  ->  sendMessage()  ->  fetch POST /api/chat
               ->  FastAPI + Groq ->  { answer, links }
               ->  addAssistantMessage() + renderLinks()

   The Groq API key lives only in backend/.env.
   Nothing secret is ever stored here or in localStorage.
   ========================================================= */

// ---------- config ----------

// Empty string = same origin (FastAPI serves this page at http://127.0.0.1:8000).
// If you open index.html with Live Server instead, set:
// const API_BASE = "http://127.0.0.1:8000";
const API_BASE = "";

const STORAGE_KEY = "ttd_seva_chat_v1";
const THEME_KEY = "ttd_seva_theme";
const MAX_LENGTH = 1000;

const WELCOME_TEXT =
  "🙏 Govinda! Welcome to TTD Seva Assistant.\n\n" +
  "I can help you with information about:\n" +
  "• Darshan\n" +
  "• Sevas\n" +
  "• Accommodation\n" +
  "• Tickets\n" +
  "• Temple timings\n" +
  "• Transportation\n" +
  "• Prasadam\n" +
  "• Donations\n" +
  "• Festivals\n" +
  "• TTD rules and facilities\n\n" +
  "Ask me anything about Tirumala Tirupati Devasthanams.";

// ---------- element handles ----------

const messagesEl = document.getElementById("messages");
const composerEl = document.getElementById("composer");
const inputEl = document.getElementById("messageInput");
const sendBtn = document.getElementById("sendBtn");
const sendLabel = document.getElementById("sendLabel");
const stopBtn = document.getElementById("stopBtn");
const statusEl = document.getElementById("connStatus");
const quickRow = document.getElementById("quickRow");
const newChatBtn = document.getElementById("newChatBtn");
const clearChatBtn = document.getElementById("clearChatBtn");
const scrollBtn = document.getElementById("scrollBottomBtn");
const aboutBtn = document.getElementById("aboutBtn");
const aboutDialog = document.getElementById("aboutDialog");
const aboutCloseBtn = document.getElementById("aboutCloseBtn");
const themeBtn = document.getElementById("themeBtn");
const themeIcon = document.getElementById("themeIcon");

// chat state kept in memory, mirrored to localStorage
let history = [];
let isWaiting = false;
let controller = null;     // lets the Stop button cancel the fetch
let lastUserMessage = "";

// ---------- small helpers ----------

function escapeHtml(text) {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Very light formatting: **bold** and * bullets. No raw HTML from the model. */
function formatAnswer(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/^\s*[-*]\s+/gm, "• ");
}

function timeNow() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function scrollToBottom(smooth) {
  messagesEl.scrollTo({
    top: messagesEl.scrollHeight,
    behavior: smooth ? "smooth" : "auto",
  });
}

function setStatus(text, kind) {
  statusEl.textContent = text;
  statusEl.className = "chat-status" + (kind ? " " + kind : "");
}

// ---------- rendering ----------

function addUserMessage(text, stamp) {
  const wrap = document.createElement("div");
  wrap.className = "msg user";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = stamp || timeNow();

  wrap.append(bubble, meta);
  messagesEl.appendChild(wrap);
  scrollToBottom(true);
  return wrap;
}

function addAssistantMessage(text, links, stamp, options) {
  const opts = options || {};

  const wrap = document.createElement("div");
  wrap.className = "msg bot";

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.innerHTML = formatAnswer(text);
  wrap.appendChild(bubble);

  if (links && links.length) {
    wrap.appendChild(renderLinks(links));
  }

  const meta = document.createElement("div");
  meta.className = "meta";

  const stampEl = document.createElement("span");
  stampEl.textContent = stamp || timeNow();
  meta.appendChild(stampEl);

  if (!opts.isWelcome) {
    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.textContent = "Copy";
    copyBtn.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(text);
        copyBtn.textContent = "Copied";
        setTimeout(() => (copyBtn.textContent = "Copy"), 1600);
      } catch {
        copyBtn.textContent = "Copy failed";
      }
    });
    meta.appendChild(copyBtn);

    const againBtn = document.createElement("button");
    againBtn.type = "button";
    againBtn.textContent = "Regenerate";
    againBtn.addEventListener("click", () => {
      if (!isWaiting && lastUserMessage) sendMessage(lastUserMessage, { repeat: true });
    });
    meta.appendChild(againBtn);
  }

  wrap.appendChild(meta);
  messagesEl.appendChild(wrap);
  scrollToBottom(true);
  return wrap;
}

/** Build the glass link cards shown under an answer. */
function renderLinks(links) {
  const grid = document.createElement("div");
  grid.className = "links";

  links.forEach((link) => {
    const card = document.createElement("a");
    card.className = "link-card";
    card.href = link.url;
    card.target = "_blank";
    card.rel = "noopener noreferrer";
    card.setAttribute("aria-label", link.title + " - opens the official page in a new tab");

    const title = document.createElement("span");
    title.className = "lc-title";
    title.textContent = "🔗 " + link.title;

    const desc = document.createElement("span");
    desc.className = "lc-desc";
    desc.textContent = link.description || "Official TTD information.";

    const open = document.createElement("span");
    open.className = "lc-open";
    open.textContent = "Open official page ↗";

    card.append(title, desc, open);
    grid.appendChild(card);
  });

  return grid;
}

function showTypingIndicator() {
  const wrap = document.createElement("div");
  wrap.className = "msg bot";
  wrap.id = "typingIndicator";
  wrap.innerHTML =
    '<div class="bubble"><span class="typing">' +
    '<span class="dots"><i></i><i></i><i></i></span>' +
    "TTD Assistant is thinking...</span></div>";
  messagesEl.appendChild(wrap);
  scrollToBottom(true);
}

function removeTypingIndicator() {
  const el = document.getElementById("typingIndicator");
  if (el) el.remove();
}

// ---------- history in localStorage ----------

function saveChat() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history));
  } catch {
    // Private mode or storage full - the chat still works for this session.
  }
}

function loadChat() {
  let saved = [];
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    saved = [];
  }

  if (!Array.isArray(saved) || saved.length === 0) {
    newChat();
    return;
  }

  history = saved;
  messagesEl.innerHTML = "";
  history.forEach((item) => {
    if (item.role === "user") {
      addUserMessage(item.text, item.time);
      lastUserMessage = item.text;
    } else {
      addAssistantMessage(item.text, item.links, item.time, { isWelcome: item.welcome });
    }
  });
  scrollToBottom(false);
}

function clearChat() {
  history = [];
  lastUserMessage = "";
  messagesEl.innerHTML = "";
  saveChat();
  setStatus("Chat cleared");
}

function newChat() {
  clearChat();
  const stamp = timeNow();
  history.push({ role: "bot", text: WELCOME_TEXT, links: [], time: stamp, welcome: true });
  addAssistantMessage(WELCOME_TEXT, [], stamp, { isWelcome: true });
  saveChat();
  setStatus("Ready");
}

// ---------- sending ----------

function setBusy(busy) {
  isWaiting = busy;
  sendBtn.disabled = busy;
  sendLabel.textContent = busy ? "Sending" : "Send";
  stopBtn.hidden = !busy;
  quickRow.querySelectorAll(".chip").forEach((chip) => (chip.disabled = busy));
  setStatus(busy ? "TTD Assistant is thinking..." : "Ready", busy ? "busy" : null);
}

async function sendMessage(rawText, options) {
  const opts = options || {};
  const text = (rawText || "").trim();

  if (isWaiting) return;

  if (!text) {
    setStatus("Type a question first", "error");
    inputEl.focus();
    return;
  }

  if (text.length > MAX_LENGTH) {
    setStatus("Question is too long. Keep it under " + MAX_LENGTH + " characters.", "error");
    return;
  }

  // "Regenerate" reuses the previous question, so do not print it twice.
  if (!opts.repeat) {
    const stamp = timeNow();
    addUserMessage(text, stamp);
    history.push({ role: "user", text: text, time: stamp });
    saveChat();
  }

  lastUserMessage = text;
  inputEl.value = "";
  autoGrow();
  setBusy(true);
  showTypingIndicator();

  controller = new AbortController();

  try {
    const response = await fetch(API_BASE + "/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
      signal: controller.signal,
    });

    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }

    removeTypingIndicator();

    if (!response.ok) {
      const detail =
        (data && typeof data.detail === "string" && data.detail) ||
        "Sorry, I couldn't process your request right now. " +
          "Please try again or check the official TTD website.";
      showBotError(detail);
      return;
    }

    if (!data || typeof data.answer !== "string") {
      showBotError(
        "The reply came back in an unexpected format. Please try asking again."
      );
      return;
    }

    const stamp = timeNow();
    addAssistantMessage(data.answer, data.links || [], stamp);
    history.push({ role: "bot", text: data.answer, links: data.links || [], time: stamp });
    saveChat();
    setStatus("Ready");
  } catch (err) {
    removeTypingIndicator();
    if (err && err.name === "AbortError") {
      setStatus("Stopped");
    } else {
      showBotError(
        "I couldn't reach the server. Check that FastAPI is running, then try again."
      );
    }
  } finally {
    controller = null;
    setBusy(false);
    inputEl.focus();
  }
}

function showBotError(message) {
  const stamp = timeNow();
  addAssistantMessage(message, [], stamp, { isWelcome: true });
  history.push({ role: "bot", text: message, links: [], time: stamp, welcome: true });
  saveChat();
  setStatus("Something went wrong", "error");
}

function handleQuickQuestion(event) {
  const chip = event.target.closest(".chip");
  if (!chip || chip.disabled) return;
  sendMessage(chip.dataset.question);
}

function handleEnterKey(event) {
  // Enter sends, Shift + Enter makes a new line.
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendMessage(inputEl.value);
  }
}

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 160) + "px";
}

// ---------- theme ----------

function applyTheme(mode) {
  const light = mode === "light";
  document.body.classList.toggle("light-glass", light);
  themeIcon.textContent = light ? "☀" : "☾";
  try {
    localStorage.setItem(THEME_KEY, light ? "light" : "dark");
  } catch {
    /* ignore */
  }
}

// ---------- wiring ----------

composerEl.addEventListener("submit", (e) => {
  e.preventDefault();
  sendMessage(inputEl.value);
});

inputEl.addEventListener("keydown", handleEnterKey);
inputEl.addEventListener("input", autoGrow);
quickRow.addEventListener("click", handleQuickQuestion);
newChatBtn.addEventListener("click", newChat);
clearChatBtn.addEventListener("click", clearChat);

stopBtn.addEventListener("click", () => {
  if (controller) controller.abort();
});

messagesEl.addEventListener("scroll", () => {
  const nearBottom =
    messagesEl.scrollHeight - messagesEl.scrollTop - messagesEl.clientHeight < 120;
  scrollBtn.hidden = nearBottom;
});

scrollBtn.addEventListener("click", () => scrollToBottom(true));

aboutBtn.addEventListener("click", () => aboutDialog.showModal());
aboutCloseBtn.addEventListener("click", () => aboutDialog.close());

themeBtn.addEventListener("click", () => {
  applyTheme(document.body.classList.contains("light-glass") ? "dark" : "light");
});

// ---------- start ----------

try {
  applyTheme(localStorage.getItem(THEME_KEY) || "dark");
} catch {
  applyTheme("dark");
}

loadChat();
autoGrow();
inputEl.focus();
