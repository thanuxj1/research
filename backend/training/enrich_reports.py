"""
NLP Enrichment Job — processes all reports through the NLP pipeline.
Fills in: sentiment_score, is_scam, scam_type, risk_level, latitude, longitude, location_name
IT22629180
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal, engine
from app.db.models import Base, Report
from app.ml.nlp_pipeline import NLPPipeline


def enrich_all(force: bool = False):
    print("=" * 55)
    print("  NLP Enrichment Job — IT22629180")
    print("=" * 55)

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    nlp = NLPPipeline()

    # Get reports needing enrichment
    if force:
        reports = db.query(Report).all()
    else:
        # Only process reports without sentiment_score
        reports = db.query(Report).filter(Report.sentiment_score == None).all()

    print(f"\nReports to process: {len(reports)}")

    enriched = 0
    for i, report in enumerate(reports):
        content = (report.content or "").strip()
        if len(content) < 15:
            continue

        # Run NLP pipeline
        result = nlp.analyze_text(content)

        # Update report fields
        report.sentiment_score = result["sentiment_score"]
        report.is_scam = result["is_scam"]
        report.risk_level = result["risk_level"]

        # Only override scam_type if not already set (seed data has it pre-set)
        if not report.scam_type and result["scam_type"]:
            report.scam_type = result["scam_type"]

        # Only override location if not already set (seed data has GPS)
        if result["latitude"] and not report.latitude:
            report.latitude = result["latitude"]
            report.longitude = result["longitude"]
            report.location_name = result["location_name"]

        enriched += 1

        if (i + 1) % 100 == 0:
            db.commit()
            print(f"  Processed {i+1}/{len(reports)}...")

    db.commit()

    # Print summary stats
    total = db.query(Report).count()
    scam_count = db.query(Report).filter(Report.is_scam == True).count()
    geolocated = db.query(Report).filter(Report.latitude != None).count()
    high_risk = db.query(Report).filter(Report.risk_level == 3).count()
    med_risk = db.query(Report).filter(Report.risk_level == 2).count()

    print(f"\n{'='*55}")
    print(f"  Enrichment Complete")
    print(f"  Total reports:     {total}")
    print(f"  Enriched:          {enriched}")
    print(f"  Scam detected:     {scam_count}")
    print(f"  Geolocated:        {geolocated}")
    print(f"  High risk (3):     {high_risk}")
    print(f"  Moderate risk (2): {med_risk}")
    print(f"{'='*55}")

    db.close()


if __name__ == "__main__":
    force = "--force" in sys.argv
    enrich_all(force=force)
