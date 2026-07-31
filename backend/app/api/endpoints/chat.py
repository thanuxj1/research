"""
SafeTravel LK — AI Chat Endpoint
IT22629180

Powers the conversational AI advisor. Uses Google Gemini (gemini-1.5-flash, free)
as the language model and injects live safety data from the database as context
so responses are grounded in real incident data rather than hallucinated.

POST /advisor/chat
  body: { message, history, profile, city, month }
  returns: { reply, structured_data }
"""
import os
import re
import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.db.models import Report

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Gemini client (lazy-loaded) ───────────────────────────────────────────────
_gemini_model = None

def _get_gemini():
    global _gemini_model
    if _gemini_model is not None:
        return _gemini_model
    try:
        import google.generativeai as genai
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        _gemini_model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_PROMPT,
        )
        logger.info("[Chat] Gemini model loaded ✓")
        return _gemini_model
    except Exception as e:
        logger.warning(f"[Chat] Gemini unavailable: {e}")
        return None


# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are SafeTravel AI, an expert travel safety advisor specialised in Sri Lanka.
You have access to a real-time database of 16,000+ tourist reviews and verified incident reports
from news sources, Reddit, YouTube, and Google Maps — all classified by an AI pipeline.

YOUR ROLE:
- Answer any travel question about Sri Lanka conversationally, like a knowledgeable local friend
- Always ground your answers in the live database context provided with each message
- Be specific, practical, and genuinely useful — not generic
- Mention specific scams, their methods, and exact locations when relevant
- Give honest risk assessments (don't downplay real dangers)
- Suggest concrete alternatives (e.g., "Use PickMe app instead of street taxis")
- If asked about topics outside Sri Lanka travel, politely redirect to what you know

TONE:
- Conversational, warm, and direct — like ChatGPT for travel safety
- Use emojis sparingly but effectively for visual structure
- Keep responses concise but complete — around 150–300 words for most questions

FORMAT RULES:
- Use **bold** for key warnings or important terms
- Use bullet points (•) for lists
- Never use markdown headers (##) — just bold text
- Always end with 1–2 follow-up suggestions as: SUGGESTIONS: ["question1", "question2"]

DATABASE CONTEXT will be injected before each user message — use it to give data-backed answers.
"""

# ── Request / Response models ─────────────────────────────────────────────────
class ChatMessage(BaseModel):
    role: str        # "user" or "model"
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []
    profile: str = "General"
    city: Optional[str] = None
    month: Optional[int] = None


# ── DB context builder ────────────────────────────────────────────────────────
def _build_db_context(db: Session, city: Optional[str], profile: str, month: Optional[int]) -> str:
    """Pull relevant live data from the database and format as context text."""
    parts = []

    try:
        # 1. City-level incident summary
        if city:
            q = (
                db.query(
                    Report.scam_type,
                    func.count(Report.id).label("cnt"),
                    func.avg(Report.risk_level).label("avg_risk"),
                )
                .filter(Report.location_name.ilike(f"%{city}%"))
                .filter(Report.scam_type.isnot(None))
                .group_by(Report.scam_type)
                .order_by(func.count(Report.id).desc())
                .limit(8)
                .all()
            )
            if q:
                threats = ", ".join(
                    f"{r.scam_type} ({r.cnt} cases, avg risk {r.avg_risk:.1f}/3)"
                    for r in q
                )
                parts.append(f"LIVE THREAT DATA for {city.title()}: {threats}")

            # 2. Recent high-risk incidents with titles
            recent = (
                db.query(Report)
                .filter(Report.location_name.ilike(f"%{city}%"))
                .filter(Report.risk_level >= 2)
                .filter(Report.title.isnot(None))
                .order_by(Report.created_at.desc())
                .limit(6)
                .all()
            )
            if recent:
                incident_lines = "\n".join(
                    f'  - [{r.scam_type or "Incident"}] {(r.title or "")[:100]} (source: {r.source or "unknown"})'
                    for r in recent
                )
                parts.append(f"RECENT VERIFIED INCIDENTS in {city.title()}:\n{incident_lines}")

            # 3. Total stats
            total = db.query(func.count(Report.id)).filter(
                Report.location_name.ilike(f"%{city}%")
            ).scalar() or 0
            negative = db.query(func.count(Report.id)).filter(
                Report.location_name.ilike(f"%{city}%"),
                Report.risk_level >= 2,
            ).scalar() or 0
            if total > 0:
                parts.append(
                    f"CITY STATS for {city.title()}: {total} total reports, "
                    f"{negative} negative/high-risk ({round(negative/total*100)}% negative rate)"
                )

        else:
            # No city — show top cities by incident count
            top_cities = (
                db.query(
                    Report.location_name,
                    func.count(Report.id).label("cnt"),
                )
                .filter(Report.location_name.isnot(None))
                .filter(Report.risk_level >= 2)
                .group_by(Report.location_name)
                .order_by(func.count(Report.id).desc())
                .limit(5)
                .all()
            )
            if top_cities:
                city_list = ", ".join(f"{r.location_name} ({r.cnt} incidents)" for r in top_cities)
                parts.append(f"TOP HIGH-RISK CITIES by incident count: {city_list}")

            # Overall scam types across Sri Lanka
            top_scams = (
                db.query(
                    Report.scam_type,
                    func.count(Report.id).label("cnt"),
                )
                .filter(Report.scam_type.isnot(None))
                .group_by(Report.scam_type)
                .order_by(func.count(Report.id).desc())
                .limit(8)
                .all()
            )
            if top_scams:
                scam_list = ", ".join(f"{r.scam_type} ({r.cnt})" for r in top_scams)
                parts.append(f"TOP SCAM TYPES across Sri Lanka: {scam_list}")

        # 4. Profile context
        profile_risks = {
            "Solo Female": "higher risk of harassment and unwanted attention; avoid isolated areas at night; be firm with tuk-tuk drivers",
            "Family": "dengue fever risk for children; unsafe beaches with rip currents; menu/food scams at tourist restaurants",
            "Couple": "gem investment scams target couples; romantic beach vendors; overpriced romantic dinners",
            "Solo Male": "gem scams and tuk-tuk diversions; overcharging at markets; fake guide scams near temples",
            "Group": "bill padding at restaurants; group transport overcharging; pickpocketing in crowds",
            "General": "tuk-tuk scams, gem shop diversions, overcharging, fake guides",
        }
        parts.append(f"PROFILE RISKS for {profile}: {profile_risks.get(profile, profile_risks['General'])}")

        # 5. Seasonal info
        if month:
            MONTH_NAMES = {
                1:"January",2:"February",3:"March",4:"April",5:"May",6:"June",
                7:"July",8:"August",9:"September",10:"October",11:"November",12:"December"
            }
            if month in range(5, 10):
                parts.append(
                    f"SEASONAL NOTE: {MONTH_NAMES.get(month, '')} is SW Monsoon season — "
                    "heavy rain on west & south coasts; some attractions closed; roads can flood"
                )
            elif month in range(10, 13):
                parts.append(
                    f"SEASONAL NOTE: {MONTH_NAMES.get(month, '')} is NE Monsoon — "
                    "rain on north & east coasts; best time for west/south coast beaches"
                )
            else:
                parts.append(
                    f"SEASONAL NOTE: {MONTH_NAMES.get(month, '')} is Dry Season — generally good travel conditions"
                )

    except Exception as e:
        logger.warning(f"[Chat] DB context error: {e}")

    return "\n\n".join(parts) if parts else "No specific database context available for this query."


# ── Fallback rule-based response ──────────────────────────────────────────────
_FALLBACK_KNOWLEDGE = {
    "gem": "**Gem Scam** is Sri Lanka's #1 tourist trap. A tuk-tuk driver befriends you, takes you to a 'government gem store', and convinces you to buy gems as a 'tax-free investment'. The gems are worthless. **Never enter a gem shop with a tuk-tuk driver.** If approached, firmly say 'No thank you' and walk away.\n\nSUGGESTIONS: [\"What other scams should I know about?\", \"How do I find safe transport?\"]",
    "tuk": "**Tuk-tuk scams** are very common. Drivers may: (1) claim the meter is broken and overcharge, (2) take you to shops for commission, (3) say your hotel/attraction is 'closed' and redirect you. \n\n• Always negotiate the fare **before** getting in\n• Use **PickMe app** (like Uber) for metered rides in cities\n• Show the destination on Google Maps if uncertain\n\nSUGGESTIONS: [\"What are gem scams?\", \"Is PickMe available everywhere?\"]",
    "safe": "Sri Lanka is generally safe for tourists but has some well-known scam hotspots. Overall crime against tourists is low, but petty scams are extremely common — especially in Colombo, Kandy, and Galle Fort.\n\n• **Colombo**: Gem shops near Pettah market\n• **Kandy**: Fake tooth relic ceremony helpers, overpriced spice gardens\n• **Galle Fort**: Art gallery scams, overpriced restaurants\n\nSUGGESTIONS: [\"Is Kandy safe to visit?\", \"What are the top scams to avoid?\"]",
    "hello": "👋 Hello! I'm **SafeTravel AI**, your intelligent guide to safe travel in Sri Lanka.\n\nI'm powered by 16,000+ real tourist reviews and incident reports. I can help with:\n• Scam alerts and how to avoid them\n• City-by-city safety assessments\n• Seasonal weather and risk warnings\n• Tips personalised to your travel style\n\nJust ask me anything!\n\nSUGGESTIONS: [\"Is Kandy safe?\", \"What are common scams?\", \"Tips for solo female travel\"]",
}

def _fallback_response(message: str, db_context: str) -> dict:
    """Rule-based fallback when Gemini is unavailable."""
    t = message.lower()

    # Check keyword matches
    for kw, reply in _FALLBACK_KNOWLEDGE.items():
        if kw in t:
            return {"reply": reply, "suggestions": _extract_suggestions(reply)}

    # Generic fallback with DB context summary
    reply = (
        "I can help with **Sri Lanka travel safety** questions. Based on our database:\n\n"
        f"{db_context[:400]}...\n\n"
        "Ask me about specific cities, scam types, or travel tips!\n\n"
        "SUGGESTIONS: [\"What are the top scams?\", \"Is Colombo safe?\"]"
    )
    return {"reply": reply, "suggestions": ["What are the top scams?", "Is Colombo safe?"]}


def _extract_suggestions(text: str) -> List[str]:
    """Extract SUGGESTIONS: [...] from the AI reply text."""
    match = re.search(r'SUGGESTIONS:\s*\[([^\]]+)\]', text)
    if match:
        raw = match.group(1)
        items = re.findall(r'"([^"]+)"', raw)
        return items
    return []


def _clean_reply(text: str) -> str:
    """Remove the SUGGESTIONS line from the visible reply."""
    return re.sub(r'\n*SUGGESTIONS:\s*\[.*?\]', '', text, flags=re.DOTALL).strip()


# ── Main chat endpoint ────────────────────────────────────────────────────────
@router.post("/advisor/chat")
async def ai_chat(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Conversational AI endpoint.
    Accepts a message + conversation history, injects live DB context,
    and returns a natural language reply from Gemini.
    """
    # Build live context from DB
    db_context = _build_db_context(db, req.city, req.profile, req.month)

    # Prepend context to the user message
    context_prefix = (
        f"[LIVE DATABASE CONTEXT — use this to ground your answer]\n{db_context}\n\n"
        f"[USER PROFILE: {req.profile}]\n"
        f"[USER QUESTION]: "
    )
    augmented_message = context_prefix + req.message

    # Try Gemini first
    model = _get_gemini()
    if model:
        try:
            # Convert history to Gemini format
            history = [
                {"role": msg.role, "parts": [msg.content]}
                for msg in req.history
            ]
            chat_session = model.start_chat(history=history)
            response = chat_session.send_message(augmented_message)
            raw_reply = response.text

            suggestions = _extract_suggestions(raw_reply)
            clean = _clean_reply(raw_reply)

            return {
                "reply": clean,
                "suggestions": suggestions[:4],
                "source": "gemini",
                "db_context_used": True,
            }
        except Exception as e:
            logger.warning(f"[Chat] Gemini call failed: {e}")

    # Fallback to rule-based
    result = _fallback_response(req.message, db_context)
    result["source"] = "fallback"
    result["db_context_used"] = True
    return result
