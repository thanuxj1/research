"""
Main Data Collection Pipeline — Dynamic Safety Heatmap & Scam Analytics Engine
IT22629180

Sources (Tourist Safety — Incident Reports AND Advisories):
  1. Web News     — Daily Mirror, Ada Derana, Sunday Times LK
  2. Social/News  — Google News RSS, 10+ LK news sites
  3. YouTube      — verified travel safety channel content
  4. Reddit       — 25+ subreddits, no API key required  ← ACTIVE
  5. Travel Forums — WikiVoyage, TripAdvisor, Gov Advisories ← NEW
  6. Google Maps  — Official Places API + Apify fallback

Strict Filter v2: Scored relevance gate.
All accepted items include source URLs for traceability.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_pipeline.collectors.youtube import YouTubeCollector
from data_pipeline.collectors.web import WebCollector
from data_pipeline.collectors.social import SocialCollector
from data_pipeline.collectors.reddit import RedditCollector
from data_pipeline.collectors.google_maps import GoogleMapsCollector
from data_pipeline.collectors.travel_forums import TravelForumsCollector
from app.db.session import SessionLocal
from app.db.models import Report
from data_pipeline.strict_filter import score_relevance


def run_collection(full_reddit: bool = False, skip_maps: bool = False) -> dict:
    print("=" * 65)
    print("  SafeTravel LK — Full Data Collection Pipeline  [IT22629180]")
    print("  Strict Filter v2 | 6 source groups active")
    print("=" * 65)

    db = SessionLocal()
    collected, skipped, rejected_filter = 0, 0, 0
    rejection_reasons: dict = {}
    source_counts: dict = {}

    try:
        all_data = []

        # ── 1. Web News Scraping ──────────────────────────────────────────
        print("\n--- [1/6] Web News (Ada Derana, Daily Mirror, Sunday Times) ---")
        try:
            web = WebCollector()
            web_items = web.collect_all()
            all_data.extend(web_items)
            print(f"  Web News total: {len(web_items)} items")
        except Exception as e:
            print(f"  [!] Web News failed: {e}")

        # ── 2. Google News RSS + LK News Outlets ─────────────────────────
        print("\n--- [2/6] Google News RSS + Sri Lanka News Outlets ---")
        try:
            social = SocialCollector()
            social_items = social.collect_all()
            all_data.extend(social_items)
            print(f"  News RSS/Newswire total: {len(social_items)} items")
        except Exception as e:
            print(f"  [!] Social/News failed: {e}")

        # ── 3. YouTube Travel Safety Videos ──────────────────────────────
        print("\n--- [3/6] YouTube Travel Safety Channels ---")
        try:
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
            print(f"  YouTube total: {yt_count} items")
        except Exception as e:
            print(f"  [!] YouTube failed: {e}")

        # ── 4. Reddit — 25+ subreddits (was disconnected, now active) ────
        print("\n--- [4/6] Reddit (25+ subreddits, no API key required) ---")
        try:
            reddit = RedditCollector()
            if full_reddit:
                reddit_items = reddit.collect_all()
            else:
                reddit_items = reddit.fast_collect_all()
            all_data.extend(reddit_items)
            print(f"  Reddit total: {len(reddit_items)} posts")
        except Exception as e:
            print(f"  [!] Reddit failed: {e}")

        # ── 5. Travel Forums & Government Advisories ── NEW ───────────────
        print("\n--- [5/6] Travel Forums (WikiVoyage, TripAdvisor, Gov Advisories) ---")
        try:
            forums = TravelForumsCollector()
            forum_items = forums.collect_all()
            all_data.extend(forum_items)
            print(f"  Travel Forums total: {len(forum_items)} items")
        except Exception as e:
            print(f"  [!] Travel Forums failed: {e}")

        # ── 6. Google Maps Reviews ────────────────────────────────────────
        if not skip_maps:
            print("\n--- [6/6] Google Maps Reviews (API + Apify fallback) ---")
            try:
                maps = GoogleMapsCollector()
                maps_items = maps.collect_all(limit_per_query=2)
                all_data.extend(maps_items)
                print(f"  Google Maps total: {len(maps_items)} reviews")
            except Exception as e:
                print(f"  [!] Google Maps failed: {e}")
        else:
            print("\n--- [6/6] Google Maps Reviews (skipped via --no-maps) ---")

        # ── Strict Filter v2 + NLP Analysis + Persist ────────────────────
        print(f"\nTotal raw collected: {len(all_data)}")
        print("Running scored relevance filter and saving...\n")

        from app.ml.nlp_pipeline import NLPPipeline
        nlp = NLPPipeline()

        for item in all_data:
            title   = (item.get("title") or "").strip()
            content = (item.get("content") or "").strip()

            # Skip empty/short entries
            if not content or len(content) < 15:
                skipped += 1
                continue

            # Scored Relevance Gate
            scoring = score_relevance(title, content)
            if not scoring["passes"]:
                rejected_filter += 1
                reason = (scoring["rejection_reason"] or "unknown").split("(")[0].strip()
                rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
                continue

            # URL-based deduplication
            url = (item.get("url") or "").strip()
            if url and db.query(Report).filter(Report.url == url).first():
                skipped += 1
                continue

            # NLP Analysis
            analysis = nlp.analyze_text(content)

            lat      = item.get("latitude")  or analysis.get("latitude")
            lon      = item.get("longitude") or analysis.get("longitude")
            loc_name = item.get("location")  or analysis.get("location_name")
            geocode_conf = item.get("geocode_confidence") or analysis.get("geocode_confidence")

            # published_at: prefer collector-parsed source date; fall back to None (created_at will be used)
            published_at_raw = item.get("published_at")
            has_pub_date = published_at_raw is not None

            # Override is_scam / scam_type if the source explicitly flags advisory
            item_is_scam   = item.get("is_scam")   # None means let NLP decide
            item_scam_type = item.get("scam_type")

            is_scam   = item_is_scam   if item_is_scam   is not None else analysis.get("is_scam", False)
            scam_type = item_scam_type if item_scam_type is not None else analysis.get("scam_type")

            report = Report(
                source=item.get("source", "unknown"),
                url=url or None,
                title=title or analysis.get("scam_type") or "Safety Report",
                content=content,
                latitude=lat,
                longitude=lon,
                is_scam=is_scam,
                scam_type=scam_type,
                risk_level=analysis.get("risk_level", 1),
                sentiment_score=analysis.get("sentiment_score", 0.0),
                location_name=loc_name,
                demographic_target=item.get("demographic"),
                published_at=published_at_raw,
                has_publish_date=has_pub_date,
                geocode_confidence=geocode_conf,
            )
            db.add(report)
            collected += 1
            src = item.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

            if collected % 50 == 0:
                print(f"  Saved {collected} items...")
                db.commit()

        db.commit()

        # ── Final Report ──────────────────────────────────────────────────
        print(f"\n{'='*65}")
        print(f"  COLLECTION COMPLETE")
        print(f"  ✅  Stored:          {collected:>6,}")
        print(f"  ❌  Filter rejected: {rejected_filter:>6,}")
        print(f"  ⏭️   Skipped (dup):   {skipped:>6,}")
        print(f"  📦  Total raw:       {len(all_data):>6,}")

        if source_counts:
            print(f"\n  STORED BY SOURCE:")
            for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
                print(f"    {src:<30} {count:>5}")

        if rejection_reasons:
            print(f"\n  FILTER REJECTION REASONS:")
            for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
                print(f"    {reason:<45} {count:>5}")

        print(f"{'='*65}\n")

        return {
            "collected": collected,
            "rejected_filter": rejected_filter,
            "skipped": skipped,
            "source_counts": source_counts,
        }

    except Exception as e:
        db.rollback()
        print(f"\n  Pipeline error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    full_mode = "--full"    in sys.argv
    skip_maps = "--no-maps" in sys.argv
    run_collection(full_reddit=full_mode, skip_maps=skip_maps)
