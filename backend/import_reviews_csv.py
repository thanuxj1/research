"""
Import low-rated TripAdvisor reviews (1-2 stars) from Reviews.csv
into the safety_heatmap.db database.
Runs NLP analysis and reclusters risk zones after import.
"""
import sys, os, csv, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.db.session import SessionLocal
from app.db.models import Report, RiskZone
from app.ml.nlp_pipeline import NLPPipeline
from app.ml.clustering_service import ClusteringService

# Coordinate map for all cities present in the dataset
CITY_COORDS = {
    "Ahangama":        (5.9706,  80.3574),
    "Ambalangoda":     (6.2348,  80.0551),
    "Anuradhapura":    (8.3114,  80.4037),
    "Arugam Bay":      (6.8399,  81.8325),
    "Bentota":         (6.4208,  80.0006),
    "Beruwala":        (6.4801,  79.9838),
    "Colombo":         (6.9271,  79.8612),
    "Deniyaya":        (6.3465,  80.5664),
    "Ella":            (6.8667,  81.0466),
    "Embilipitiya":    (6.3433,  80.8447),
    "Galle":           (6.0535,  80.2210),
    "Habarana":        (8.0097,  80.7489),
    "Haputale":        (6.7681,  80.9603),
    "Hikkaduwa":       (6.1395,  80.1008),
    "Jaffna":          (9.6615,  80.0255),
    "Kalkudah":        (8.0000,  81.3667),
    "Kalutara":        (6.5854,  79.9607),
    "Kandy":           (7.2906,  80.6337),
    "Katukitula":      (7.3833,  80.7000),
    "Koslanda":        (6.7167,  80.9167),
    "Mirissa":         (5.9483,  80.4716),
    "Negombo":         (7.2083,  79.8358),
    "Nilaveli":        (8.7167,  81.2000),
    "Nuwara Eliya":    (6.9497,  80.7891),
    "Peradeniya":      (7.2667,  80.5933),
    "Pinnawala":       (7.3000,  80.3833),
    "Polonnaruwa":     (7.9403,  81.0188),
    "Pussellawa":      (7.0667,  80.6333),
    "Saliyapura":      (8.3667,  80.4167),
    "Sigiriya":        (7.9572,  80.7603),
    "Tissamaharama":   (6.2833,  81.2833),
    "Trincomalee":     (8.5922,  81.2152),
    "Unawatuna":       (5.9997,  80.2489),
    "Weligatta":       (6.1000,  80.4000),
}

def run_import():
    print("=" * 60)
    print("  Reviews.csv Import — Low-Rated Reviews (1-2 stars)")
    print("=" * 60)

    db = SessionLocal()
    nlp = NLPPipeline()

    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Reviews.csv")
    csv_path = os.path.normpath(csv_path)

    with open(csv_path, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        rows = [r for r in reader if r.get("Rating") in ("1", "2")]

    print(f"Low-rated reviews to process: {len(rows)}")

    saved = 0
    skipped = 0
    errors = 0

    for i, row in enumerate(rows):
        try:
            title   = (row.get("Title") or "").strip()
            content = (row.get("Text")  or "").strip()
            city    = (row.get("Located_City") or "").strip()
            location_str = (row.get("Location") or city).strip()
            rating  = row.get("Rating", "")
            travel_date = row.get("Travel_Date", "")

            if not content or len(content) < 20:
                skipped += 1
                continue

            full_text = f"{title}. {content}".strip()

            # Deduplicate by content
            existing = db.query(Report).filter(Report.content == full_text).first()
            if existing:
                skipped += 1
                continue

            # Get coordinates
            coords = CITY_COORDS.get(city)
            lat = coords[0] if coords else None
            lon = coords[1] if coords else None

            # NLP analysis
            analysis = nlp.analyze_text(full_text)

            # Use NLP coords as fallback
            if not lat:
                lat = analysis.get("latitude")
                lon = analysis.get("longitude")

            # Risk level: 1-star = high(3), 2-star = moderate(2)
            risk_level = 3 if rating == "1" else 2

            report = Report(
                source="tripadvisor_csv",
                url=None,
                title=title or analysis.get("scam_type") or "Tourist Review",
                content=full_text,
                latitude=lat,
                longitude=lon,
                is_scam=analysis.get("is_scam", False),
                scam_type=analysis.get("scam_type"),
                risk_level=risk_level,
                sentiment_score=analysis.get("sentiment_score", 0.0),
                location_name=location_str or city,
                demographic_target=None,
            )
            db.add(report)
            saved += 1

            if saved % 50 == 0:
                db.commit()
                print(f"  Saved {saved} / {len(rows)} ...")

        except Exception as e:
            errors += 1
            db.rollback()
            print(f"  [Error] Row {i}: {e}")

    db.commit()
    print(f"\nImport complete:")
    print(f"  Saved  : {saved}")
    print(f"  Skipped: {skipped}")
    print(f"  Errors : {errors}")

    # Recluster
    print("\nRecalculating risk zones...")
    db.query(RiskZone).delete()
    db.commit()
    try:
        zones = ClusteringService(eps_km=2.0, min_samples=3).run(db)
        print(f"Risk zones updated: {zones} zones")
    except Exception as e:
        print(f"[Clustering Error] {e}")

    db.close()

if __name__ == "__main__":
    run_import()
