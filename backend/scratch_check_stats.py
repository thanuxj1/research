
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report
from sqlalchemy import func

def check_stats():
    db = SessionLocal()
    total = db.query(Report).count()
    sources = db.query(Report.source, func.count(Report.id)).group_by(Report.source).all()
    
    print(f"Total reports: {total}")
    for source, count in sources:
        print(f"  {source}: {count}")
    db.close()

if __name__ == "__main__":
    check_stats()
