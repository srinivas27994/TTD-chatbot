"""
TTD Seva Assistant - FastAPI backend
====================================

What this file does, step by step:

1. Loads the Groq API key from the .env file (the key never reaches the browser).
2. Exposes POST /api/chat  ->  { "message": "..." }
3. Validates the message (not empty, not too long).
4. Detects which TTD topic the question is about (darshan / seva / room / ...).
5. Picks the matching OFFICIAL TTD links for that topic.
6. Sends the question + a strict system prompt to the Groq API.
7. Returns { "answer": "...", "links": [ ... ] } back to the frontend.
8. Also serves the frontend folder, so one command runs the whole app.

Run it from the project root (the folder that contains backend/ and frontend/):

    uvicorn backend.main:app --reload
"""

import os
import re
import logging
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. Configuration
# ---------------------------------------------------------------------------

# backend/main.py -> backend/ -> project root
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")

# Read backend/.env
load_dotenv(os.path.join(BASE_DIR, ".env"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# If the .env still holds the example text, treat it as "not set yet".
if GROQ_API_KEY.lower() in {"paste_your_groq_key_here", "your_groq_api_key_here"}:
    GROQ_API_KEY = ""
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Comma separated list, e.g. ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:8000,http://127.0.0.1:8000,"
        "http://localhost:5500,http://127.0.0.1:5500",
    ).split(",")
    if o.strip()
]

MAX_MESSAGE_LENGTH = 1000
REQUEST_TIMEOUT_SECONDS = 30.0

FRIENDLY_ERROR = (
    "Sorry, I couldn't process your request right now. "
    "Please try again or check the official TTD website."
)

# Log normally, but never log the API key or full request bodies.
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ttd-seva-assistant")


# ---------------------------------------------------------------------------
# 2. Official TTD link directory
# ---------------------------------------------------------------------------
# IMPORTANT: only URLs that were verified as live official TTD domains are kept
# here. TTD runs two official domains:
#
#   www.tirumala.org            -> official information website
#   ttdevasthanams.ap.gov.in    -> official online booking portal
#   tirupatibalaji.ap.gov.in    -> the same official booking portal (mirror)
#
# Deep links inside the booking portal are created after login and change often,
# so for booking topics we send the devotee to the portal home page and tell
# them which section to open. We never invent a URL.

LINK_HOME = {
    "title": "TTD Official Website",
    "description": "Official Tirumala Tirupati Devasthanams information website.",
    "url": "https://www.tirumala.org/",
}

LINK_BOOKING_PORTAL = {
    "title": "TTD Official Online Booking Portal",
    "description": "The only official portal for darshan, seva, accommodation and donations.",
    "url": "https://ttdevasthanams.ap.gov.in/",
}

LINK_BOOKING_MIRROR = {
    "title": "TTD Booking Portal (official mirror)",
    "description": "Same official booking portal on the tirupatibalaji.ap.gov.in address.",
    "url": "https://tirupatibalaji.ap.gov.in/",
}

LINK_ADVANCE_BOOKING = {
    "title": "Advance Booking Information",
    "description": "Official TTD page explaining advance booking of tickets.",
    "url": "https://www.tirumala.org/Advancebooking.aspx",
}

LINK_FOOTPATH = {
    "title": "Tirupati to Tirumala on Foot",
    "description": "Official page about the Alipiri footpath route to Tirumala.",
    "url": "https://www.tirumala.org/TirumalatoTirupathiOnFoot.aspx",
}

# topic -> list of link cards shown for that topic
OFFICIAL_LINKS = {
    "darshan": [LINK_BOOKING_PORTAL, LINK_ADVANCE_BOOKING, LINK_HOME],
    "seva": [LINK_BOOKING_PORTAL, LINK_ADVANCE_BOOKING, LINK_HOME],
    "accommodation": [LINK_BOOKING_PORTAL, LINK_HOME],
    "donation": [LINK_BOOKING_PORTAL, LINK_HOME],
    "transport": [LINK_HOME, LINK_FOOTPATH],
    "prasadam": [LINK_HOME, LINK_BOOKING_PORTAL],
    "timings": [LINK_HOME],
    "festival": [LINK_HOME],
    "rules": [LINK_HOME],
    "booking_help": [LINK_BOOKING_PORTAL, LINK_BOOKING_MIRROR, LINK_HOME],
    "general": [LINK_HOME, LINK_BOOKING_PORTAL],
}

# Keywords for each topic. English + common Telugu/Tenglish words.
TOPIC_KEYWORDS = {
    "accommodation": [
        "accommodation", "room", "rooms", "cottage", "stay", "lodging", "guest house",
        "guesthouse", "cro", "srinivasam", "vishnu nivasam", "madhavam", "dormitory",
        "gadi", "gadulu", "bus rooms",
    ],
    "seva": [
        "seva", "sevas", "arjitha", "suprabhata", "suprabhatam", "thomala", "archana",
        "kalyanotsavam", "kalyanam", "unjal", "abhishekam", "sahasra deepalankara",
        "nijapada", "virtual seva", "online seva", "angapradakshinam",
    ],
    "donation": [
        "donation", "donate", "donations", "srivani", "hundi", "e-hundi", "ehundi",
        "trust", "contribution", "danam", "chanda",
    ],
    "transport": [
        "bus", "buses", "apsrtc", "transport", "travel", "reach", "how to go",
        "how to reach", "train", "railway", "airport", "flight", "taxi", "ghat road",
        "alipiri", "footpath", "steps", "walk", "srivari mettu", "parking",
    ],
    "prasadam": [
        "prasadam", "prasad", "laddu", "laddoo", "anna prasadam", "annaprasadam",
        "free food", "vada", "dadhyodanam", "matrusri",
    ],
    "timings": [
        "timing", "timings", "time", "open", "opening", "close", "closing", "schedule",
        "samayam", "hours", "darshan time",
    ],
    "festival": [
        "festival", "brahmotsavam", "brahmotsavams", "vaikunta", "ekadasi",
        "rathasapthami", "utsavam", "garuda seva", "pushpa yagam", "panchami theertham",
    ],
    "rules": [
        "rule", "rules", "dress code", "dress", "id proof", "aadhaar", "aadhar",
        "mobile allowed", "luggage", "children", "cloak room", "tonsure", "kalyanakatta",
    ],
    "darshan": [
        "darshan", "darshanam", "dharsan", "special entry", "300", "₹300", "rs 300",
        "sarva darshan", "sarvadarshan", "ssd", "divya darshan", "break darshan",
        "senior citizen", "vip break", "slotted", "dip", "e-dip", "token", "queue",
        "vaikuntam queue",
    ],
    "booking_help": [
        "book", "booking", "ticket", "tickets", "quota", "release", "login",
        "registration", "register", "cancel", "refund", "payment", "otp",
    ],
}

# When two topics match, the more specific one should win.
TOPIC_PRIORITY = [
    "accommodation", "seva", "donation", "transport", "prasadam",
    "festival", "rules", "darshan", "timings", "booking_help",
]


def detect_topics(message: str) -> List[str]:
    """Return the topics a question is about, most relevant first."""
    text = message.lower()
    found = []
    for topic in TOPIC_PRIORITY:
        for keyword in TOPIC_KEYWORDS[topic]:
            # word-ish match so "book" does not fire inside "bookshop"
            if re.search(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", text):
                found.append(topic)
                break
    return found


def select_links(message: str) -> List[dict]:
    """Pick official link cards that actually match the question."""
    topics = detect_topics(message)

    if not topics:
        return list(OFFICIAL_LINKS["general"])

    # "how to book a room" -> accommodation wins, booking_help is only a helper
    main_topics = [t for t in topics if t != "booking_help"] or ["booking_help"]

    links: List[dict] = []
    seen = set()
    for topic in main_topics[:2]:          # at most two topics
        for link in OFFICIAL_LINKS[topic]:
            if link["url"] not in seen:
                seen.add(link["url"])
                links.append(link)

    return links[:3]                        # at most three cards, keeps UI clean


# ---------------------------------------------------------------------------
# 3. System prompt for the AI
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are TTD Seva Assistant, an information assistant for devotees \
visiting Tirumala Tirupati Devasthanams (TTD).

Your purpose is to give clear, accurate and useful information about TTD services: \
darshan, Special Entry Darshan, sevas, accommodation, laddu prasadam, temple timings, \
festivals, transportation, Tirumala and Tirupati facilities, donations, booking \
procedures, devotee rules and general pilgrimage information.

RULES YOU MUST FOLLOW:

1. Never invent ticket availability, prices, timings, rules or booking information.
2. When information can change, tell the user to confirm the latest details on the \
official TTD website.
3. Prefer official TTD sources.
4. Never claim that a third-party website is an official TTD website. The official \
sites are www.tirumala.org and ttdevasthanams.ap.gov.in only.
5. For booking questions, point the devotee to the official TTD booking portal.
6. If you do not know something, say clearly that you do not have reliable \
information instead of guessing.
7. Keep answers short and useful. Use short paragraphs or simple bullet points.
8. Be polite and respectful. The users are devotees.
9. Use simple language.
10. Answer in the language the user used. Telugu question -> Telugu answer. \
English question -> English answer. Mixed Telugu-English -> reply in the same mixed style.
11. Never ask for or repeat sensitive personal information such as Aadhaar numbers, \
card numbers or OTPs.
12. Do not present unofficial information as confirmed TTD policy.
13. Do not write URLs inside your answer. The application shows official links \
separately below your answer. You may say "see the official links below".
"""


# ---------------------------------------------------------------------------
# 4. Request / response models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=MAX_MESSAGE_LENGTH)


class LinkCard(BaseModel):
    title: str
    description: str
    url: str


class ChatResponse(BaseModel):
    answer: str
    links: List[LinkCard]
    topic: Optional[str] = None


# ---------------------------------------------------------------------------
# 5. FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TTD Seva Assistant API",
    description="AI chatbot backend for Tirumala Tirupati Devasthanams information.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(Exception)
async def unhandled_error_handler(request, exc):
    """Never leak a stack trace to the browser."""
    logger.exception("Unhandled server error")
    return JSONResponse(status_code=500, content={"detail": FRIENDLY_ERROR})


async def ask_groq(message: str) -> str:
    """Send the question to Groq and return the plain text answer."""
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is missing. Add it to backend/.env")
        raise HTTPException(
            status_code=503,
            detail="The assistant is not configured yet. Please add the API key in .env.",
        )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "temperature": 0.3,
        "max_tokens": 700,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(GROQ_URL, json=payload, headers=headers)
    except httpx.TimeoutException:
        logger.warning("Groq request timed out")
        raise HTTPException(status_code=504, detail=FRIENDLY_ERROR)
    except httpx.HTTPError:
        logger.warning("Network error while calling Groq")
        raise HTTPException(status_code=502, detail=FRIENDLY_ERROR)

    if response.status_code != 200:
        # Log the status only - never the key, never the full body.
        logger.warning("Groq returned status %s", response.status_code)
        raise HTTPException(status_code=502, detail=FRIENDLY_ERROR)

    try:
        data = response.json()
        answer = data["choices"][0]["message"]["content"].strip()
    except (ValueError, KeyError, IndexError, AttributeError):
        logger.warning("Could not read the Groq response shape")
        raise HTTPException(status_code=502, detail=FRIENDLY_ERROR)

    if not answer:
        raise HTTPException(status_code=502, detail=FRIENDLY_ERROR)

    return answer


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint: validate -> detect topic -> pick links -> ask Groq."""
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Please type a question first.")

    if len(message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Your question is too long. Please keep it under "
                   f"{MAX_MESSAGE_LENGTH} characters.",
        )

    topics = detect_topics(message)
    links = select_links(message)
    answer = await ask_groq(message)

    return ChatResponse(
        answer=answer,
        links=[LinkCard(**link) for link in links],
        topic=topics[0] if topics else None,
    )


@app.get("/api/health")
async def health():
    """Quick check that the server is up and the key is loaded."""
    return {
        "status": "ok",
        "model": GROQ_MODEL,
        "api_key_loaded": bool(GROQ_API_KEY),
    }


# ---------------------------------------------------------------------------
# 6. Serve the frontend (so http://127.0.0.1:8000 opens the chatbot)
# ---------------------------------------------------------------------------

if os.path.isdir(FRONTEND_DIR):
    app.mount("/assets",
              StaticFiles(directory=os.path.join(FRONTEND_DIR, "assets")),
              name="assets")

    @app.get("/")
    async def index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

    @app.get("/style.css")
    async def style():
        return FileResponse(os.path.join(FRONTEND_DIR, "style.css"))

    @app.get("/script.js")
    async def script():
        return FileResponse(os.path.join(FRONTEND_DIR, "script.js"))
else:
    logger.warning("frontend/ folder not found - API will run without the UI")
