"""
Dedicated Standalone YouTube Safety Scraper — SafeTravel LK Engine
IT22629180

Scrapes tourist safety warnings, scam reports, and negative travel experiences
in Sri Lanka from YouTube, extracts transcripts/descriptions, runs AI NLP analysis,
and persists non-duplicate reports to the PostgreSQL database.
"""
import sys
import os
import time

# Ensure root path is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from youtube_transcript_api import YouTubeTranscriptApi
from googleapiclient.discovery import build
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Report
from app.ml.nlp_pipeline import NLPPipeline
from data_pipeline.strict_filter import passes_strict_filter

# Expanded YouTube queries targeted at tourist experiences in Sri Lanka
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


def run_youtube_scraper():
    api_key = settings.YOUTUBE_API_KEY
    if not api_key or "your_" in api_key:
        print("[ERR] Valid YOUTUBE_API_KEY not configured in backend/.env")
        return

    youtube = build('youtube', 'v3', developerKey=api_key)
    nlp = NLPPipeline()
    db = SessionLocal()

    print("=" * 65)
    print("  SafeTravel LK — Dedicated YouTube Safety Scraper")
    print(f"  Total Queries: {len(YT_SAFETY_QUERIES)}")
    print("=" * 65)

    all_videos = []
    seen_ids = set()

    # 1. Search YouTube for each query
    for q in YT_SAFETY_QUERIES:
        print(f"\n--- Searching: '{q}' ---")
        try:
            req = youtube.search().list(
                q=q,
                part="snippet",
                maxResults=8,
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
            time.sleep(0.3)
        except Exception as e:
            print(f"  [ERR] Search failed for '{q}': {e}")

    print(f"\nTotal unique YouTube videos fetched: {len(all_videos)}")
    print("Extracting transcripts & analyzing content...\n")

    saved_count = 0
    skipped_count = 0

    for idx, video in enumerate(all_videos, 1):
        vid = video['id']
        url = video['url']
        raw_title = video['title']
        channel = video['channel_title']

        # Skip if URL already exists in database
        if db.query(Report).filter(Report.url == url).first():
            print(f"  [{idx}/{len(all_videos)}] [SKIP] Duplicate in DB: {raw_title[:50]}...")
            skipped_count += 1
            continue

        # Extract transcript
        transcript = ""
        try:
            ts = YouTubeTranscriptApi().fetch(vid)
            parts = [getattr(s, 'text', None) or str(s) for s in ts]
            transcript = " ".join(p for p in parts if p)
        except Exception as e:
            pass

        # Fallback to title + description if transcript unavailable
        content = transcript if len(transcript) > 50 else f"{raw_title}. {video['description']}".strip()

        if len(content) < 30:
            skipped_count += 1
            continue

        # Strict Filter check (or fallback geographic + negative check)
        is_relevant = passes_strict_filter(raw_title, content)
        if not is_relevant:
            # Secondary check specifically for YouTube travel vlogs
            text_lower = f"{raw_title} {content}".lower()
            has_lanka = any(k in text_lower for k in ["sri lanka", "lankan", "colombo", "kandy", "galle", "ella", "sigiriya"])
            has_negative = any(k in text_lower for k in ["scam", "avoid", "warning", "overcharge", "danger", "worst", "cheat", "trap", "bad", "harass", "fake", "stolen", "robbed"])
            if has_lanka and has_negative:
                is_relevant = True

        if not is_relevant:
            print(f"  [{idx}/{len(all_videos)}] [FILTERED] Not relevant: {raw_title[:50]}...")
            skipped_count += 1
            continue

        # AI NLP Analysis
        try:
            analysis = nlp.analyze_text(content[:1500])  # send snippet to NLP
            lat = analysis.get("latitude")
            lon = analysis.get("longitude")
            loc_name = analysis.get("location_name")

            report = Report(
                source="youtube",
                url=url,
                title=raw_title,
                content=content[:3000],  # cap at 3000 chars
                latitude=lat,
                longitude=lon,
                is_scam=analysis.get("is_scam", True),
                scam_type=analysis.get("scam_type", "Tourist Scam / Warning"),
                risk_level=analysis.get("risk_level", 2),
                sentiment_score=analysis.get("sentiment_score", -0.4),
                location_name=loc_name or "Sri Lanka",
                demographic_target="Tourists / Travel Vloggers",
            )
            db.add(report)
            db.commit()
            saved_count += 1
            safe_t = raw_title.encode('ascii', errors='replace').decode('ascii')
            print(f"  [{idx}/{len(all_videos)}] [SAVED] {safe_t[:55]} | Channel: {channel}")
        except Exception as e:
            db.rollback()
            print(f"  [{idx}/{len(all_videos)}] [ERR] DB error for {vid}: {e}")

    db.close()
    print("\n" + "=" * 65)
    print(f"  FINISHED YOUTUBE SCRAPING: {saved_count} new reports saved | {skipped_count} skipped/filtered")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    run_youtube_scraper()
