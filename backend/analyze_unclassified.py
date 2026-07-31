
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report
from app.ml.nlp_pipeline import NLPPipeline

def analyze_all_unclassified():
    print("=" * 65)
    print("  SafeTravel LK — Catch-up AI Analysis  ")
    print("=" * 65)
    
    db = SessionLocal()
    nlp = NLPPipeline()
    
    # Find reports where is_scam is False but content exists 
    # (or more precisely, where sentiment_score is 0.0 or risk_level is default)
    # Actually, let's just re-analyze everything that doesn't have coordinates
    reports = db.query(Report).filter(
        (Report.latitude.is_(None)) | (Report.scam_type.is_(None))
    ).all()
    
    print(f"Found {len(reports)} items needing analysis.")
    
    updated = 0
    for r in reports:
        if not r.content:
            continue
            
        analysis = nlp.analyze_text(r.content)
        
        # Only update if AI found something useful
        if analysis.get("latitude") and not r.latitude:
            r.latitude = analysis.get("latitude")
            r.longitude = analysis.get("longitude")
        
        r.is_scam = analysis.get("is_scam", False)
        if not r.scam_type:
            r.scam_type = analysis.get("scam_type")
        r.risk_level = analysis.get("risk_level", 1)
        r.sentiment_score = analysis.get("sentiment_score", 0.0)
        if not r.location_name:
            r.location_name = analysis.get("location_name")
            
        updated += 1
        if updated % 100 == 0:
            print(f"  Analyzed {updated} items...")
            db.commit()
            
    db.commit()
    db.close()
    print(f"\nAnalysis complete! Updated {updated} reports with AI insights.")
    print("=" * 65)

if __name__ == "__main__":
    analyze_all_unclassified()
