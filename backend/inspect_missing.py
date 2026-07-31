import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.db.session import SessionLocal
from app.db.models import Report

db = SessionLocal()
# Check a sample of reports with missing fields
missing = db.query(Report).filter(Report.scam_type.is_(None)).limit(8).all()
for r in missing:
    content = (r.content or "")[:250]
    print(f"ID: {r.id} | Source: {r.source}")
    print(f"  Scam Type: {r.scam_type} | Location: {r.location_name}")
    print(f"  Content: {content}")
    print()
db.close()
