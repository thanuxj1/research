import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report, RiskZone
from app.ml.clustering_service import ClusteringService

def purge():
    db = SessionLocal()
    
    # Define allowed news sources
    allowed_sources = {
        'daily_mirror', 'daily_mirror_lk',
        'adaderana',
        'sundaytimes', 'sundaytimes_lk',
        'google_news',
        'newswire_lk',
        'colombo_gazette',
        'ceylon_today',
        'themorning_lk',
        'hirunews_lk',
        'theisland_lk',
        'economynext_lk',
        'youtube',
        'youtube (recovered)',
        'news (recovered)'
    }
    
    reports = db.query(Report).all()
    deleted_count = 0
    kept_count = 0
    for r in reports:
        if r.source not in allowed_sources:
            db.delete(r)
            deleted_count += 1
        else:
            kept_count += 1
            
    print(f"Purging non-news reports:")
    print(f"  Deleted: {deleted_count} reports")
    print(f"  Kept: {kept_count} news-only reports")
    
    db.commit()
    
    # Recalculate clusters
    print("Recalculating risk zones...")
    db.query(RiskZone).delete()
    db.commit()
    
    try:
        zones = ClusteringService(eps_km=2.0, min_samples=3).run(db)
        print(f"Risk zones recalculated: {zones} zones created.")
    except Exception as e:
        print(f"Error recalculating risk zones: {e}")
    
    db.close()

if __name__ == '__main__':
    purge()
