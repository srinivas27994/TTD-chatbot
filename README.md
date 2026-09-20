# TTD Seva Assistant

An AI chatbot that answers devotee questions about **Tirumala Tirupati Devasthanams** —
darshan, sevas, accommodation, timings, transport, prasadam, donations, festivals and
temple rules — and shows the matching **official TTD links** as glass cards under every answer.

Independent student project. Not affiliated with, or endorsed by, TTD.

---

## 1. Project overview

You type a question in the browser. The question goes to a FastAPI backend, which figures out
which TTD topic you asked about, picks the official links for that topic, asks the Groq API for
an answer using a strict system prompt, and sends both back as JSON.

The Groq API key stays on the server. It is never sent to the browser.

---

## 2. Features

- Chat UI with glassmorphism panels over an original Tirumala dawn illustration
- Topic detection: darshan, seva, accommodation, donation, transport, prasadam, timings, festivals, rules
- Official link cards chosen per question, not the same generic link every time
- 8 quick-question chips
- Enter to send, Shift + Enter for a new line, auto-growing textarea
- "TTD Assistant is thinking..." indicator, Stop button, Regenerate, Copy answer
- Chat history in browser localStorage, with New chat and Clear chat
- Dark / light glass toggle, scroll-to-bottom button
- Telugu, English or Tenglish answers — the model replies in the language you asked in
- Keyboard navigation, aria-labels, visible focus rings, reduced-motion support
- Friendly errors for empty input, long input, timeouts, missing key and server failures

---

## 3. Technologies used

| Layer | Tech |
|---|---|
| Frontend | HTML5, CSS3, vanilla JavaScript |
| Backend | Python, FastAPI, Uvicorn, HTTPX, python-dotenv, Pydantic |
| AI | Groq API (chat completions) |
| Database | none in v1 — the code is plain enough to add SQLite later |

---

## 4. Folder structure

```
ttd-chatbot/
│
├── backend/
│   ├── main.py            FastAPI app, topic detection, link directory, Groq call
│   ├── requirements.txt   pinned dependencies
│   ├── .env               your real key (git-ignored)
│   └── .env.example       template to copy
│
├── frontend/
│   ├── index.html         page structure
│   ├── style.css          glassmorphism theme
│   ├── script.js          chat logic, localStorage, link cards
│   └── assets/
│       └── tirumala-background.jpg
│
├── README.md
└── .gitignore
```

---

## 5. Install Python

Install Python 3.10 or newer from <https://www.python.org/downloads/>.
On Windows, tick **Add Python to PATH** during installation.

Check it:

```bat
python --version
```

---

## 6. Create a virtual environment

From the `ttd-chatbot` folder:

```bat
python -m venv venv
venv\Scripts\activate
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 7. Install dependencies

```bat
pip install -r backend/requirements.txt
```

---

## 8. Configure .env

Copy the template and open it in a text editor:

```bat
copy backend\.env.example backend\.env
```

Fill in your key:

```
GROQ_API_KEY=gsk_your_real_key_here
GROQ_MODEL=openai/gpt-oss-120b
ALLOWED_ORIGINS=http://localhost:8000,http://127.0.0.1:8000
```

`GROQ_MODEL` is configurable on purpose. Groq retires models from time to time, so if you get an
error about the model, open <https://console.groq.com/docs/models>, copy a current model ID and
paste it here. No code change needed.

---

## 9. Start FastAPI

Run this from the `ttd-chatbot` folder (not from inside `backend/`):

```bat
uvicorn backend.main:app --reload
```

You should see `Uvicorn running on http://127.0.0.1:8000`.

---

## 10. Open the application

Go to **<http://127.0.0.1:8000>** in your browser. FastAPI serves the frontend itself, so there
is nothing else to start.

To check the server separately: <http://127.0.0.1:8000/api/health> returns the model name and
whether the key loaded.

**Running the frontend separately (optional):** if you prefer VS Code Live Server, open
`frontend/index.html` with it, then in `frontend/script.js` change

```js
const API_BASE = "";
```

to

```js
const API_BASE = "http://127.0.0.1:8000";
```

and add your Live Server origin (usually `http://127.0.0.1:5500`) to `ALLOWED_ORIGINS` in `.env`.

---

## 11. Groq API setup

1. Sign up at <https://console.groq.com>.
2. Open **API Keys** and create a key. It starts with `gsk_`.
3. Copy it once — Groq will not show it again.
4. Paste it into `backend/.env` as `GROQ_API_KEY`.
5. Restart uvicorn so the new value is read.

---

## 12. Security precautions

- The key is read with `python-dotenv` from `backend/.env` and used only inside `main.py`.
- `.env` is in `.gitignore`, so it never reaches GitHub. If you ever push a key by mistake,
  delete that key in the Groq console immediately and create a new one.
- The key never appears in HTML, CSS, JavaScript or localStorage.
- Errors are logged as status codes only. The key and request bodies are never logged.
- CORS is limited to the origins listed in `ALLOWED_ORIGINS`.
- Messages are validated: non-empty and at most 1000 characters.
- Groq calls time out after 30 seconds.
- A catch-all handler returns a friendly sentence instead of a stack trace.

---

## 13. How official links are handled

The chatbot must not send devotees to fake booking sites, so links are **not** generated by the AI.
The system prompt tells the model not to write URLs at all. Instead `backend/main.py` holds a small
dictionary of verified official TTD URLs:

| Domain | What it is |
|---|---|
| `www.tirumala.org` | Official TTD information website |
| `ttdevasthanams.ap.gov.in` | Official online booking portal |
| `tirupatibalaji.ap.gov.in` | The same official booking portal, alternate address |

`detect_topics()` matches keywords in the question (English and common Telugu words — `gadi`,
`samayam`, `laddu`, `suprabhatam`, `srivani` and so on), and `select_links()` returns up to three
cards for the top topics.

Deep links inside the booking portal are created after login and change every month, so for booking
questions the app sends devotees to the portal home page and the answer explains which section to
open. This follows the rule in the brief: when an exact official page cannot be verified, give the
official home page instead. Before you submit or demo the project, click each card once and confirm
the pages still load.

---

## 14. Troubleshooting

| Problem | Fix |
|---|---|
| `The assistant is not configured yet` | `.env` is missing, empty, or still has the placeholder text. Add the real key and restart uvicorn. |
| `Could not import module "backend"` | You are inside `backend/`. Go up one level and run `uvicorn backend.main:app --reload` from the project root. |
| `Sorry, I couldn't process your request` | Groq returned an error. Check the terminal: status 401 means a bad key, 429 means rate limited, 404 or 400 usually means the model ID in `GROQ_MODEL` no longer exists. |
| `I couldn't reach the server` | uvicorn is not running, or the page was opened as `file://`. Open `http://127.0.0.1:8000` instead. |
| CORS error in the browser console | Add the exact origin you are browsing from to `ALLOWED_ORIGINS` in `.env`, then restart. |
| `venv\Scripts\activate` blocked on Windows | Run PowerShell as admin once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`. |
| Background image missing | Check `frontend/assets/tirumala-background.jpg` exists. The page falls back to a dark colour if it doesn't. |
| Old messages keep coming back | That is localStorage. Click **Clear chat** or **New chat**. |

---

## 15. Request flow

```
Browser  ->  fetch POST /api/chat  { "message": "How can I book darshan?" }
   |
FastAPI  ->  validate length and emptiness
         ->  detect_topics()  ->  ["darshan", "booking_help"]
         ->  select_links()   ->  official darshan link cards
         ->  ask_groq()       ->  system prompt + question  ->  Groq API
   |
Response ->  { "answer": "...", "links": [ {title, description, url} ], "topic": "darshan" }
   |
Browser  ->  addAssistantMessage()  +  renderLinks()  ->  glass link cards
```

---

## 16. Note on answers

Answers are AI-generated. Ticket availability, quota release dates, prices and timings change
often. Always confirm anything time-sensitive on the official TTD website before you travel.
Never share your Aadhaar number, card details or OTP in the chat.
