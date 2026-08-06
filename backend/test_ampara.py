import sqlite3

conn = sqlite3.connect(r'E:\research\backend\safety_heatmap.db')
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM reports WHERE location_name LIKE '%Ampara%' OR title LIKE '%Ampara%' OR content LIKE '%Ampara%'")
print("Reports mentioning Ampara:", cur.fetchone()[0])

cur.execute("SELECT COUNT(*) FROM reports WHERE location_name LIKE '%Arugam%' OR title LIKE '%Arugam%' OR content LIKE '%Arugam%'")
print("Reports mentioning Arugam:", cur.fetchone()[0])

# Check how Ampara district reports are scored in score_all_districts
from app.core.district_engine import score_all_districts
from app.db.models import Report
from app.db.session import SessionLocal

db = SessionLocal()
all_reports = db.query(Report).filter(Report.latitude.isnot(None), Report.longitude.isnot(None)).all()
scores = score_all_districts(all_reports)

ampara_score = scores.get("Ampara")
print("\nAmpara district engine score:")
if ampara_score:
    print(f"  report_count: {ampara_score['report_count']}")
    print(f"  scam_report_count: {ampara_score['scam_report_count']}")
    print(f"  risk_tier: {ampara_score['risk_tier']}")
    print(f"  recent_reports count: {len(ampara_score['recent_reports_raw'])}")
    for r in ampara_score['recent_reports_raw'][:5]:
        print(f"    - [{r.source}] {r.title} ({r.location_name})")
else:
    print("  Ampara NOT FOUND in scores!")

db.close()
conn.close()
