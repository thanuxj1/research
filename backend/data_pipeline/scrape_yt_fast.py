"""
Fast YouTube Safety Scraper — SafeTravel LK Engine
IT22629180

Directly queries YouTube API, extracts transcripts, performs fast rule-based
relevance & location extraction, and saves non-duplicate tourist safety/scam reports to the database.
"""
import sys
import os
import re
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Report

# Comprehensive search queries targeted at tourist safety/scam reports in Sri Lanka
YT_SAFETY_QUERIES = [
    "Sri Lanka tourist scams",
    "Sri Lanka travel safety warning",
    "Sri Lanka tuk tuk scam",
    "Sri Lanka gem shop scam",
    "Sri Lanka travel nightmare scam",
    "avoid in Sri Lanka tourist warning",
    "Sri Lanka dangerous places tourists",
    "Colombo tourist scam warning",
    "Kandy fake guide scam Sri Lanka",
    "Ella Rock tour guide scam",
    "Galle Fort overcharged tourist scam",
    "Sri Lanka solo female travel safety warning",
    "Sri Lanka taxi overcharging scam",
    "Sigiriya tourist overcharge scam",
    "Mirissa whale watching scam warning",
    "Sri Lanka travel scam alert",
]

# Sri Lanka Location Mapping (lat, lon)
SL_LOCATIONS = {
    "colombo": (6.9271, 79.8612),
    "kandy": (7.2906, 80.6337),
    "galle": (6.0535, 80.2210),
    "ella": (6.8728, 81.0464),
    "sigiriya": (7.9573, 80.7600),
    "negombo": (7.2083, 79.8358),
    "mirissa": (5.9483, 80.4716),
    "arugam": (6.8399, 81.8325),
    "nuwara eliya": (6.9497, 80.7891),
    "trincomalee": (8.5874, 81.2152),
    "hikkaduwa": (6.1395, 80.1061),
    "unawatuna": (5.9997, 80.2489),
    "bentota": (6.4221, 80.0009),
    "matara": (5.9549, 80.5550),
    "jaffna": (9.6615, 80.0255),
    "dambulla": (7.8675, 80.6517),
}


# ── Positive reassurance & pro-safety patterns
POSITIVE_REASSURANCE = [
    "i felt safe", "felt completely safe", "never felt unsafe", "not felt unsafe",
    "have not felt unsafe", "i feel safe", "felt very safe", "actually safe",
    "surprisingly safe", "safer than i expected", "perfectly safe", "totally safe",
    "completely safe", "so safe", "quite safe", "very safe",
    "amazing country", "beautiful people", "friendly locals", "everyone was so kind",
    "don't be afraid", "don't worry", "nothing to worry", "myths about",
    "debunking", "misconception", "travel advisory is wrong", "is it safe? yes",
    "sri lanka is safe", "lanka is safe", "safe to visit", "safe country",
    "if you're wondering if sri lanka", "afraid to come", "not as dangerous",
    "unfounded fears", "travel alerts amplify", "damage our economy",
    "revoke travel warning", "tighten security", "security measures tighten",
]

# ── General travel tips, itineraries, & educational overview patterns (NOT single incident reports)
TIPS_AND_ADVISORIES = [
    "things i wish i knew", "things you need to know", "things to know",
    "things to avoid", "what to know", "how to avoid",
    "common scams", "types of scams", "scams tourists face",
    "travel guide", "itinerary", "dos and don'ts", "do's and don'ts",
    "before you go", "before travelling", "before visiting",
    "in 10 mins", "in 10 minutes", "honest review", "honest take",
    "top 5 places", "top 10 places", "watch before", "watch before coming",
]

# ── Confirmed scam/incident signals — these must be present for is_scam=True
CONFIRMED_SCAM_SIGNALS = [
    "scammed", "got scammed", "i was scammed", "they scammed",
    "ripped off", "ripped me off", "they ripped",
    "overcharged", "charged me extra", "charged too much",
    "fake guide", "fake monk", "fake ticket",
    "tuk tuk scam", "gem scam", "gem shop scam",
    "stolen", "my bag", "pickpocket", "robbed", "mugged",
    "harassed me", "followed me", "groped",
    "avoid this man", "avoid this guy", "don't trust this",
    "tourist trap", "they will scam", "watch out for",
    "beware of", "warning about",
]

# ── Direct first-person incident signals
FIRST_PERSON_SIGNALS = [
    "i got scammed", "we got scammed", "i was scammed", "we were scammed",
    "scammed me", "robbed me", "attacked me", "stole my", "ripped me off",
    "avoid this man", "avoid this guy", "caught on camera", "scammed 5 times",
]


def is_genuinely_negative(title: str, content: str) -> bool:
    """
    Returns True only if the video content contains confirmed scam/incident signals
    AND is NOT primarily a positive-safety-reassurance or general travel tips video.
    """
    combined = (title + " " + content).lower()

    # If it contains clear general travel tips/itinerary or pro-safety reassurance, exclude from scam rating
    is_educational_or_tips = any(t in combined for t in TIPS_AND_ADVISORIES)
    is_pro_safety = any(p in combined for p in POSITIVE_REASSURANCE)

    # First-person incident signals override general tips
    has_first_person = any(fp in combined for fp in FIRST_PERSON_SIGNALS)

    if (is_educational_or_tips or is_pro_safety) and not has_first_person:
        return False

    # Count positive reassurance signals
    positive_hits = sum(1 for p in POSITIVE_REASSURANCE if p in combined)

    # Count confirmed scam signals
    scam_hits = sum(1 for s in CONFIRMED_SCAM_SIGNALS if s in combined)

    # If positive signals dominate, this is a reassurance video — exclude it
    if positive_hits >= 2 and scam_hits == 0:
        return False
    if positive_hits > scam_hits and scam_hits < 2:
        return False

    # Must have at least one confirmed scam signal
    return scam_hits >= 1


def extract_location(text):
    text_l = text.lower()
    for loc, coords in SL_LOCATIONS.items():
        if loc in text_l:
            return loc.title(), coords[0], coords[1]
    return "Sri Lanka", 6.9271, 79.8612


def detect_scam_type(text):
    t = text.lower()
    if "gem" in t and ("scam" in t or "fake" in t or "shop" in t):
        return "Gem Scam"
    elif "tuk tuk" in t or "tuktuk" in t or "three wheeler" in t:
        return "Tuk-Tuk Scam"
    elif ("taxi" in t or "meter" in t) and ("scam" in t or "overcharge" in t or "refused" in t):
        return "Transport Fraud"
    elif "fake guide" in t or "fake monk" in t or "fake ticket" in t:
        return "Fake Guide"
    elif "overcharge" in t or "ripped off" in t or "rip off" in t or "charged extra" in t:
        return "Overcharging"
    elif "stolen" in t or "theft" in t or "robbed" in t or "pickpocket" in t or "mugged" in t:
        return "Theft / Robbery"
    elif "harass" in t or "followed me" in t or "groped" in t:
        return "Harassment"
    return "Tourist Scam / Warning"


def run_fast_youtube_scraper():
    api_key = settings.YOUTUBE_API_KEY
    if not api_key or "your_" in api_key:
        print("[ERR] No YOUTUBE_API_KEY configured in backend/.env")
        return

    youtube = build('youtube', 'v3', developerKey=api_key)
    db = SessionLocal()

    print("=" * 65)
    print("  SafeTravel LK — Fast YouTube Safety Scraper")
    print(f"  Searching {len(YT_SAFETY_QUERIES)} targeted queries...")
    print("=" * 65)

    all_videos = []
    seen_ids = set()

    for q in YT_SAFETY_QUERIES:
        print(f"Searching: '{q}'...")
        try:
            req = youtube.search().list(
                q=q,
                part="snippet",
                maxResults=10,
                type="video"
            )
            res = req.execute()
            for item in res.get('items', []):
                vid = item['id']['videoId']
                if vid not in seen_ids:
                    seen_ids.add(vid)
                    all_videos.append({
                        "id": vid,
                        "title": item['snippet']['title'],
                        "description": item['snippet'].get('description', ''),
                        "channel_title": item['snippet'].get('channelTitle', ''),
                        "url": f"https://www.youtube.com/watch?v={vid}"
                    })
            time.sleep(0.2)
        except Exception as e:
            print(f"  [ERR] Search failed for '{q}': {e}")

    print(f"\nFetched {len(all_videos)} unique YouTube videos. Processing transcripts...")

    saved_count = 0
    skipped_count = 0

    for idx, video in enumerate(all_videos, 1):
        vid = video['id']
        url = video['url']
        raw_title = video['title']
        channel = video['channel_title']

        # Skip if URL already exists in database
        if db.query(Report).filter(Report.url == url).first():
            skipped_count += 1
            continue

        # Extract transcript
        transcript = ""
        try:
            ts = YouTubeTranscriptApi().fetch(vid)
            parts = [getattr(s, 'text', None) or str(s) for s in ts]
            transcript = " ".join(p for p in parts if p)
        except Exception:
            pass

        content = transcript if len(transcript) > 50 else f"{raw_title}. {video['description']}".strip()
        if len(content) < 30:
            skipped_count += 1
            continue

        text_lower = f"{raw_title} {content}".lower()

        # 1. Geographic gate — must mention Sri Lanka
        has_lanka = any(k in text_lower for k in ["sri lanka", "lankan", "colombo", "kandy", "galle", "ella", "sigiriya", "negombo", "mirissa"])
        if not has_lanka:
            skipped_count += 1
            continue

        # 2. Check if genuinely negative vs positive reassurance / travel discussion
        is_neg = is_genuinely_negative(raw_title, content)
        loc_name, lat, lon = extract_location(text_lower)

        if is_neg:
            is_scam_val = True
            scam_type_val = detect_scam_type(text_lower)
            risk_val = 2
            sent_val = -0.6
        else:
            is_scam_val = False
            scam_type_val = "Safety Advisory"
            risk_val = 1
            sent_val = 0.5

        try:
            report = Report(
                source="youtube",
                url=url,
                title=raw_title,
                content=content[:3000],
                latitude=lat,
                longitude=lon,
                is_scam=is_scam_val,
                scam_type=scam_type_val,
                risk_level=risk_val,
                sentiment_score=sent_val,
                location_name=loc_name,
                demographic_target="Tourists / Travel Vloggers",
            )
            db.add(report)
            db.commit()
            saved_count += 1
            safe_t = raw_title.encode('ascii', errors='replace').decode('ascii')
            tag = "SCAM" if is_scam_val else "ADVISORY"
            print(f"  [{saved_count}] [{tag}] {safe_t[:60]} ({loc_name})")
        except Exception as e:
            db.rollback()
            print(f"  [ERR] DB save failed for {vid}: {e}")

    db.close()
    print("\n" + "=" * 65)
    print(f"  DONE: {saved_count} new YouTube safety reports saved to DB | {skipped_count} skipped/duplicate")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_fast_youtube_scraper()
