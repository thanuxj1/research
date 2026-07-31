"""
Main Data Collection Pipeline — Dynamic Safety Heatmap & Scam Analytics Engine
IT22629180

Sources (NEGATIVE TOURIST EXPERIENCES ONLY):
  1. Reddit       — 8 subs fast / 25+ subs full
  2. Web          — TripAdvisor, Lonely Planet, travel safety sites
  3. Social/News  — Twitter/X, Google News, WikiVoyage, Quora, 10+ LK news sites
  4. YouTube      — video transcripts (scam/safety content only)
  5. Facebook     — public travel groups via Apify
  6. Google Maps  — negative reviews via Apify
  7. TikTok       — hashtag search via Apify
  8. Instagram    — hashtag search via Apify

Strict Filter: ALL data must be about negative tourist experiences in Sri Lanka.
No mock or positive/safe zone data is ever stored.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_pipeline.collectors.youtube import YouTubeCollector
from data_pipeline.collectors.web import WebCollector
from data_pipeline.collectors.social import SocialCollector
from app.db.session import SessionLocal
from app.db.models import Report
from data_pipeline.strict_filter import passes_strict_filter


def run_collection(full_reddit: bool = False) -> dict:
    print("=" * 65)
    print("  SafeTravel LK — News Data Collection Pipeline  [IT22629180]")
    print("  Mode: News-Only")
    print("=" * 65)

    db = SessionLocal()
    collected, skipped = 0, 0

    try:
        all_data = []

        # ── 1. Web News Scraping ─────────────────────────────────────────
        print("\n--- [1/3] Web News Scraping ---")
        web = WebCollector()
        web_items = web.collect_all()
        all_data.extend(web_items)
        print(f"  Web News total: {len(web_items)} items")

        # ── 2. News Aggregators & Outlets ───────────────────────────────
        print("\n--- [2/3] News Aggregators & Outlets ---")
        social = SocialCollector()
        social_items = social.collect_all()
        all_data.extend(social_items)
        print(f"  News RSS/Newswire total: {len(social_items)} items")

        # ── 3. YouTube News Channels ────────────────────────────────────
        print("\n--- [3/3] YouTube News Channels ---")
        youtube = YouTubeCollector()
        yt_queries = [
            "Sri Lanka tourist scams",
            "Sri Lanka travel safety",
            "Sri Lanka gem shop scam",
            "Sri Lanka tuk tuk scam tourists",
            "Sri Lanka dangerous places avoid",
            "Sri Lanka solo female travel safety",
            "Sri Lanka Tourist Police scam report",
        ]
        yt_count = 0
        for q in yt_queries:
            items = youtube.collect(query=q, limit=5)
            all_data.extend(items)
            yt_count += len(items)
        print(f"  YouTube News total: {yt_count} transcripts")

        # ── Persist to DB with AI Analysis ──────────────────────────────
        print(f"\nTotal collected raw: {len(all_data)}")
        print("Analyzing and saving new items...")

        from app.ml.nlp_pipeline import NLPPipeline
        nlp = NLPPipeline()

        for item in all_data:
            title = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()
            if not content or len(content) < 15:
                skipped += 1
                continue

            # ── STRICT RELEVANCE GATE ──────────────────────────────────────
            # EVERY item must be a negative tourist experience in Sri Lanka.
            # No exceptions. No safe/positive data stored here.
            if not passes_strict_filter(title, content):
                skipped += 1
                continue

            # Deduplication by URL
            url = (item.get("url") or "").strip()
            if url:
                if db.query(Report).filter(Report.url == url).first():
                    skipped += 1
                    continue

            # Run AI Analysis
            analysis = nlp.analyze_text(content)
            
            # Merge scraped data with AI analysis
            # We prefer scraped coordinates if available (e.g. from Google Maps)
            lat = item.get("latitude") or analysis.get("latitude")
            lon = item.get("longitude") or analysis.get("longitude")
            loc_name = item.get("location") or analysis.get("location_name")

            report = Report(
                source=item.get("source", "unknown"),
                url=url or None,
                title=item.get("title") or analysis.get("scam_type") or "Safety Report",
                content=content,
                latitude=lat,
                longitude=lon,
                is_scam=analysis.get("is_scam", False),
                scam_type=item.get("scam_type") or analysis.get("scam_type"),
                risk_level=analysis.get("risk_level", 1),
                sentiment_score=analysis.get("sentiment_score", 0.0),
                location_name=loc_name,
                demographic_target=item.get("demographic"),
            )
            db.add(report)
            collected += 1
            
            if collected % 50 == 0:
                print(f"  Processed {collected} items...")
                db.commit()

        db.commit()
        print(f"\n{'='*65}")
        print(f"  DONE: {collected} items analyzed & saved | {skipped} skipped")
        print(f"{'='*65}\n")

        return {"collected": collected, "skipped": skipped}

    except Exception as e:
        db.rollback()
        print(f"\n  Pipeline error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    full_mode = "--full" in sys.argv
    run_collection(full_reddit=full_mode)
