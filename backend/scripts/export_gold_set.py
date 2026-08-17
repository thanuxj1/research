"""
Gold Set Export — SafeTravel LK
IT22629180

Exports all DB records to a CSV ready for hand-labelling.
The gold_ columns are blank — fill them in manually.

Usage:
    cd backend
    python scripts/export_gold_set.py

Then open scripts/gold_set_export.csv in Excel or Google Sheets.
Fill in the gold_* columns following scripts/gold_set_instructions.md.
When done, run:
    python scripts/evaluate_gold_set.py --gold scripts/gold_set_export.csv
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.db.models import Report

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gold_set_export.csv")

db = SessionLocal()
records = db.query(Report).order_by(Report.id).all()

# Determine corpus type heuristically for the 'corpus' column
def guess_corpus(r):
    src = (r.source or "").lower()
    if any(x in src for x in ["tripadvisor", "reviews", "dataset_csv"]):
        return "reviews"
    return "news"

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow([
        "id", "corpus", "source", "title", "content_preview",
        "is_scam_model", "scam_type_model", "location_name_model",
        "geocode_confidence",
        # Blank columns you fill in:
        "gold_is_scam", "gold_scam_type", "gold_location",
        "gold_victim_profile", "gold_confidence", "notes"
    ])
    for r in records:
        w.writerow([
            r.id,
            guess_corpus(r),
            r.source,
            r.title,
            (r.content or "")[:300],
            int(r.is_scam or 0),
            r.scam_type,
            r.location_name,
            r.geocode_confidence,
            # Leave blank for annotation:
            "", "", "", "", "", ""
        ])

db.close()
print(f"Exported {len(records)} records -> {OUT}")
print()
print("Next steps:")
print("  1. Open gold_set_export.csv in Excel or Google Sheets")
print("  2. Fill in gold_is_scam, gold_scam_type, gold_location, gold_victim_profile, gold_confidence")
print("     following the instructions in scripts/gold_set_instructions.md")
print("  3. Ask a second annotator to independently label the first 20 rows")
print("  4. Run: python scripts/evaluate_gold_set.py --gold scripts/gold_set_export.csv")
