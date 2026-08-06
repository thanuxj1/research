"""
Main Data Collection Pipeline — Dynamic Safety Heatmap & Scam Analytics Engine
IT22629180

Sources (NEGATIVE TOURIST EXPERIENCES ONLY):
  1. Web          — Daily Mirror, Ada Derana, Sunday Times
  2. Social/News  — Google News RSS, 10+ LK news sites
  3. YouTube      — verified news channel transcripts (scam/safety content only)

Strict Filter (v2): Scored relevance gate — items must achieve a minimum
combined tourist-context + negative-experience score to be stored.
All accepted items include source URLs for traceability.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_pipeline.collectors.youtube import YouTubeCollector
from data_pipeline.collectors.web import WebCollector
from data_pipeline.collectors.social import SocialCollector
from app.db.session import SessionLocal
from app.db.models import Report
from data_pipeline.strict_filter import score_relevance


def run_collection(full_reddit: bool = False) -> dict:
    print("=" * 65)
    print("  SafeTravel LK — News Data Collection Pipeline  [IT22629180]")
    print("  Strict Filter v2: Scored relevance gating")
    print("=" * 65)

    db = SessionLocal()
    collected, skipped, rejected_filter = 0, 0, 0

    # Track rejection reasons for summary
    rejection_reasons: dict = {}

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

            # Minimum content length
            if not content or len(content) < 15:
                skipped += 1
                continue

            # ── SCORED RELEVANCE GATE (v2) ─────────────────────────────
            # Every item is scored across tourist-context + negative-experience
            # dimensions. Items must hit minimum thresholds on both dimensions
            # AND a combined total score. This prevents marginal matches
            # (e.g., a news article that mentions "bad road" near a Sri Lanka
            # location but has no tourist context) from polluting the dataset.
            scoring = score_relevance(title, content)
            if not scoring["passes"]:
                rejected_filter += 1
                reason = scoring["rejection_reason"] or "unknown"
                short_reason = reason.split("(")[0].strip()
                rejection_reasons[short_reason] = rejection_reasons.get(short_reason, 0) + 1
                continue

            # Deduplication by URL
            url = (item.get("url") or "").strip()
            if url:
                if db.query(Report).filter(Report.url == url).first():
                    skipped += 1
                    continue

            # Run AI Analysis
            analysis = nlp.analyze_text(content)

            # Prefer scraped coordinates if available (e.g. from Google Maps)
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
        print(f"  DONE: {collected} items stored | {rejected_filter} filtered out | {skipped} skipped (dup/short)")

        if rejection_reasons:
            print(f"\n  FILTER REJECTION BREAKDOWN:")
            for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
                print(f"    {reason:<45} {count:>5}")

        print(f"{'='*65}\n")

        return {
            "collected": collected,
            "rejected_filter": rejected_filter,
            "skipped": skipped,
            "rejection_reasons": rejection_reasons,
        }

    except Exception as e:
        db.rollback()
        print(f"\n  Pipeline error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    full_mode = "--full" in sys.argv
    run_collection(full_reddit=full_mode)
