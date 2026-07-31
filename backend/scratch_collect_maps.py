
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data_pipeline.collectors.google_maps import GoogleMapsCollector
from app.db.session import SessionLocal
from app.db.models import Report

def collect_extensive_maps():
    print("Starting extensive Google Maps data collection...")
    collector = GoogleMapsCollector()
    
    # Increase limit for "all related reviews" request
    items = collector.collect_all(limit_per_query=15)
    
    db = SessionLocal()
    saved = 0
    skipped = 0
    
    for item in items:
        url = item.get("url")
        # Deduplication
        if url and db.query(Report).filter(Report.url == url).first():
            skipped += 1
            continue
            
        report = Report(
            source=item.get("source"),
            title=item.get("title"),
            content=item.get("content"),
            url=url,
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            scam_type="Google Maps Review"
        )
        db.add(report)
        saved += 1
    
    db.commit()
    db.close()
    
    print(f"Collection complete. Saved {saved} new reports. Skipped {skipped} duplicates.")

if __name__ == "__main__":
    collect_extensive_maps()
