"""
Strict Purge — Remove all reports that don't meet the
tourist negative-experience research criteria.
"""
import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report, RiskZone
from data_pipeline.strict_filter import passes_strict_filter

def strict_purge():
    print("=" * 60)
    print("  SafeTravel LK — Strict Research Data Purge")
    print("=" * 60)

    db = SessionLocal()
    all_reports = db.query(Report).all()
    total_before = len(all_reports)
    print(f"\nTotal before purge: {total_before}")

    removed = 0
    kept = 0
    for r in all_reports:
        title = r.title or ""
        content = r.content or ""
        if not passes_strict_filter(title, content):
            db.delete(r)
            removed += 1
        else:
            kept += 1

    db.commit()

    # Also clear old risk zones so they get recalculated cleanly
    db.query(RiskZone).delete()
    db.commit()

    total_after = db.query(Report).count()
    print(f"Removed:            {removed} irrelevant reports")
    print(f"Kept:               {kept} valid research reports")
    print(f"Total after purge:  {total_after}")
    print(f"\nAll remaining reports are strictly about negative")
    print(f"tourist experiences in Sri Lanka.")
    print("=" * 60)

    db.close()

if __name__ == "__main__":
    strict_purge()
