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


def extract_location(text):
    text_l = text.lower()
    for loc, coords in SL_LOCATIONS.items():
        if loc in text_l:
            return loc.title(), coords[0], coords[1]
    return "Sri Lanka", 6.9271, 79.8612


def detect_scam_type(text):
    t = text.lower()
    if "gem" in t:
        return "Gem Scam"
    elif "tuk tuk" in t or "tuktuk" in t or "three wheeler" in t:
        return "Tuk Tuk Scam"
    elif "taxi" in t or "meter" in t or "uber" in t:
        return "Transport Fraud"
    elif "guide" in t:
        return "Fake Guide"
    elif "overcharge" in t or "ripped off" in t or "rip off" in t or "expensive" in t:
        return "Overcharging"
    elif "stolen" in t or "theft" in t or "robbed" in t or "pickpocket" in t:
        return "Theft / Robbery"
    elif "harass" in t or "follow" in t or "touch" in t or "stalk" in t:
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

        # Relevance filter
        has_lanka = any(k in text_lower for k in ["sri lanka", "lankan", "colombo", "kandy", "galle", "ella", "sigiriya", "negombo", "mirissa"])
        has_negative = any(k in text_lower for k in ["scam", "avoid", "warning", "overcharge", "danger", "worst", "cheat", "trap", "bad", "harass", "fake", "stolen", "robbed", "theft", "alert"])

        if not (has_lanka and has_negative):
            skipped_count += 1
            continue

        loc_name, lat, lon = extract_location(text_lower)
        scam_type = detect_scam_type(text_lower)

        try:
            report = Report(
                source="youtube",
                url=url,
                title=raw_title,
                content=content[:3000],
                latitude=lat,
                longitude=lon,
                is_scam=True,
                scam_type=scam_type,
                risk_level=2,
                sentiment_score=-0.5,
                location_name=loc_name,
                demographic_target="Tourists / Travel Vloggers",
            )
            db.add(report)
            db.commit()
            saved_count += 1
            safe_t = raw_title.encode('ascii', errors='replace').decode('ascii')
            print(f"  [{saved_count}] [SAVED] {safe_t[:60]} ({loc_name})")
        except Exception as e:
            db.rollback()
            print(f"  [ERR] DB save failed for {vid}: {e}")

    db.close()
    print("\n" + "=" * 65)
    print(f"  DONE: {saved_count} new YouTube safety reports saved to DB | {skipped_count} skipped/duplicate")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_fast_youtube_scraper()
