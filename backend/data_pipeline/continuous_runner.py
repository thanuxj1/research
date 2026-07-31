"""
Continuous Data Collection Runner - Sri Lanka Tourist Safety Project.

Keeps web and social/news scraping active in the background. Heavier sources
are staggered so the API remains responsive while the scraper keeps running.
Every saved item must pass the strict negative-tourist-experience filter.
"""

import concurrent.futures
import os
import sys
import time
import traceback
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import Report
from app.db.session import SessionLocal
from app.ml.clustering_service import ClusteringService
from app.ml.nlp_pipeline import NLPPipeline
from data_pipeline.collectors.social import SocialCollector
from data_pipeline.collectors.web import WebCollector
from data_pipeline.collectors.youtube import YouTubeCollector
from data_pipeline.strict_filter import passes_strict_filter


nlp = NLPPipeline()


def process_item(item, db):
    """Analyze and save a single collected item."""
    try:
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        url = (item.get("url") or "").strip()

        if not content or len(content) < 15:
            return False

        if not passes_strict_filter(title, content):
            return False

        if url and db.query(Report).filter(Report.url == url).first():
            return False

        analysis = nlp.analyze_text(content)
        lat = item.get("latitude") or analysis.get("latitude")
        lon = item.get("longitude") or analysis.get("longitude")
        loc_name = item.get("location") or analysis.get("location_name")

        report = Report(
            source=item.get("source", "unknown"),
            url=url or None,
            title=title or analysis.get("scam_type") or "Safety Report",
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
        db.commit()
        return True
    except Exception as exc:
        db.rollback()
        print(f"  [Error] Failed to process item: {exc}")
        return False


def run_collector_task(name, collector_func):
    """Run one collector and return its results without crashing the loop."""
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Starting collector: {name}")
        items = collector_func()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {name} finished. Collected {len(items)} items.")
        return name, items
    except Exception as exc:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {name} failed: {exc}")
        return name, []


def main():
    print("=" * 65)
    print("  SafeTravel LK - Continuous News Collector")
    print("  Mode: Always-on | News Web/RSS every cycle | YT News staggered")
    print("=" * 65)

    youtube = YouTubeCollector()
    web = WebCollector()
    social = SocialCollector()

    db = SessionLocal()
    iteration = 1
    cycle_interval = 300  # 5 minutes.

    try:
        while True:
            start_time = time.time()
            print(f"\n--- [Iteration {iteration} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---")

            tasks = {
                "News RSS": lambda: social.fast_collect_all(),
                "Web News": lambda: web.collect_all(),
            }
            if iteration % 6 == 1:
                queries = [
                    "Ella Sri Lanka tourist safety",
                    "Sigiriya Lion Rock tourist guide scam",
                    "Mirissa whale watching harassment warning",
                    "Galle Fort tourist overcharge restaurant",
                    "Kandy Temple of the Tooth flower scam",
                    "Colombo Pettah market pickpocket warning",
                    "Sri Lanka tourist assault physical incident",
                    "Sri Lanka travel harassment warning",
                    "Sri Lanka tuk tuk overcharge scam",
                ]
                import random
                tasks["YouTube News"] = lambda: youtube.collect(
                    query=random.choice(queries),
                    limit=3,
                )

            total_collected = 0
            total_saved = 0
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
                future_to_collector = {
                    executor.submit(run_collector_task, name, func): name
                    for name, func in tasks.items()
                }
                for future in concurrent.futures.as_completed(future_to_collector):
                    _name, items = future.result()
                    total_collected += len(items)
                    for item in items:
                        if process_item(item, db):
                            total_saved += 1

            elapsed = time.time() - start_time
            print("\nIteration Summary:")
            print(f"  Raw items found: {total_collected}")
            print(f"  New items saved : {total_saved}")
            print(f"  Total time taken: {elapsed:.2f} seconds")

            if total_saved:
                try:
                    zones = ClusteringService(eps_km=2.0, min_samples=3).run(db)
                    print(f"  Risk zones refreshed: {zones}")
                except Exception as exc:
                    print(f"  [Clustering] Skipped after collection: {exc}")

            wait_time = max(5, cycle_interval - elapsed)
            print(f"  Next update in {wait_time:.1f}s...")
            time.sleep(wait_time)
            iteration += 1

    except KeyboardInterrupt:
        print("\nRunner stopped by user.")
    except Exception as exc:
        print(f"\n[FATAL ERROR] Runner crashed: {exc}")
        traceback.print_exc()
    finally:
        db.close()


if __name__ == "__main__":
    main()
