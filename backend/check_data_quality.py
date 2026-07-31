import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report

db = SessionLocal()
total = db.query(Report).count()
no_type = db.query(Report).filter(Report.scam_type.is_(None)).count()
no_loc = db.query(Report).filter(Report.location_name.is_(None)).count()
no_both = db.query(Report).filter(Report.scam_type.is_(None), Report.location_name.is_(None)).count()

print(f"Total reports:         {total}")
print(f"Missing scam_type:     {no_type}  ({no_type*100//total}%)")
print(f"Missing location:      {no_loc}   ({no_loc*100//total}%)")
print(f"Missing both:          {no_both}  ({no_both*100//total}%)")

print("\nSample missing-type reports:")
samples = db.query(Report).filter(Report.scam_type.is_(None)).limit(5).all()
for s in samples:
    content_preview = (s.content or "")[:120]
    print(f"  [{s.source}] {content_preview}")

db.close()
