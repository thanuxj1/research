"""
Corpus Snapshot & Freeze — SafeTravel LK
IT22629180

Run before EVERY evaluation run. Writes a deterministic JSONL snapshot of the
corpus and prints the SHA-256 hash to cite in the thesis.

Usage:
    cd backend
    python scripts/freeze_corpus.py

Cite the printed hash in the thesis as:
    "Evaluation conducted against corpus snapshot sha256:<hash>"

RESEARCH_MODE=true must be set in .env to prevent the pipeline from mutating
the corpus between freeze and evaluation.
"""
import hashlib
import json
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.db.models import Report

FIELDS = [
    "id", "source", "url", "title", "content", "is_scam", "scam_type",
    "risk_level", "latitude", "longitude", "location_name",
    "source_weight", "published_at", "has_publish_date",
    "geocode_confidence", "created_at",
]

db = SessionLocal()
rows = [
    {f: (str(getattr(r, f)) if getattr(r, f) is not None else None) for f in FIELDS}
    for r in db.query(Report).order_by(Report.id).all()
]
db.close()

payload = "\n".join(json.dumps(row, sort_keys=True) for row in rows)
digest = hashlib.sha256(payload.encode()).hexdigest()[:12]
today = dt.date.today().isoformat()
name = f"corpus_v1_{today}_sha256-{digest}.jsonl"

out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "dataset_exports")
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, name)

with open(out_path, "w", encoding="utf-8") as fh:
    fh.write(payload)

print(f"\n{len(rows)} records -> {out_path}")
print(f"\nCite this hash in the thesis:")
print(f"  sha256:{digest}")
print(f"\nReminder: RESEARCH_MODE=true must remain set during evaluation.")
print(f"          Run: python scripts/sensitivity_analysis.py --csv dataset_exports/safety_incidents_dataset.csv")
