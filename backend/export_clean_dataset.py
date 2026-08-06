"""
Clean Dataset Exporter — SafeTravel LK Research Engine
IT22629180

Reads ALL collected data from the database, re-runs the improved strict filter,
and exports a clean CSV dataset with source links.

Output CSV columns:
  id, source, source_url, title, content,
  location_name, latitude, longitude,
  scam_type, risk_level, sentiment_score, is_scam,
  relevance_score, tourist_score, negative_score,
  created_at

Usage:
    python export_clean_dataset.py                      # exports from DB
    python export_clean_dataset.py --audit              # also saves rejection log
    python export_clean_dataset.py --out my_data.csv    # custom output path
"""

import os
import sys
import csv
import argparse
from datetime import datetime

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BACKEND_DIR)

from app.db.session import SessionLocal
from app.db.models import Report
from data_pipeline.strict_filter import score_relevance

DEFAULT_OUTPUT = os.path.join(BACKEND_DIR, "exports", "safetravel_lk_clean_dataset.csv")
DEFAULT_REJECT_LOG = os.path.join(BACKEND_DIR, "exports", "rejection_audit_log.csv")

# CSV columns in output
FIELDNAMES = [
    "id",
    "source",
    "source_url",
    "title",
    "content",
    "location_name",
    "latitude",
    "longitude",
    "scam_type",
    "risk_level",
    "sentiment_score",
    "is_scam",
    "relevance_score",
    "tourist_score",
    "negative_score",
    "matched_signals",
    "created_at",
]

REJECT_FIELDNAMES = [
    "id",
    "source",
    "source_url",
    "title",
    "content_preview",
    "rejection_reason",
    "total_score",
    "negative_score",
    "tourist_score",
]


def export_clean_dataset(output_path: str, audit: bool = False, reject_log_path: str = DEFAULT_REJECT_LOG):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    db = SessionLocal()
    try:
        all_reports = db.query(Report).order_by(Report.created_at.desc()).all()
    finally:
        db.close()

    total = len(all_reports)
    print("=" * 65)
    print("  SafeTravel LK — Clean Dataset Exporter  [IT22629180]")
    print("=" * 65)
    print(f"\n  Total records in DB: {total:,}")
    print(f"  Re-running improved strict filter on all records...\n")

    accepted = []
    rejected = []

    for report in all_reports:
        title = report.title or ""
        content = report.content or ""

        scoring = score_relevance(title, content)

        row = {
            "id": report.id,
            "source": report.source,
            "source_url": report.url or "",
            "title": title,
            "content": content,
            "location_name": report.location_name or "",
            "latitude": report.latitude or "",
            "longitude": report.longitude or "",
            "scam_type": report.scam_type or "",
            "risk_level": report.risk_level or 1,
            "sentiment_score": round(report.sentiment_score, 4) if report.sentiment_score is not None else "",
            "is_scam": int(report.is_scam) if report.is_scam is not None else 0,
            "relevance_score": round(scoring["total_score"], 2),
            "tourist_score": round(scoring["tourist_score"], 2),
            "negative_score": round(scoring["negative_score"], 2),
            "matched_signals": " | ".join(scoring["matched_signals"]),
            "created_at": report.created_at.isoformat() if report.created_at else "",
        }

        if scoring["passes"]:
            accepted.append(row)
        else:
            rejected.append({
                "id": report.id,
                "source": report.source,
                "source_url": report.url or "",
                "title": title[:120],
                "content_preview": content[:200].replace("\n", " "),
                "rejection_reason": scoring["rejection_reason"],
                "total_score": round(scoring["total_score"], 2),
                "negative_score": round(scoring["negative_score"], 2),
                "tourist_score": round(scoring["tourist_score"], 2),
            })

    # ── Write clean dataset ──────────────────────────────────────────────────
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(accepted)

    # ── Source breakdown ─────────────────────────────────────────────────────
    source_counts = {}
    for row in accepted:
        src = row["source"]
        source_counts[src] = source_counts.get(src, 0) + 1

    print(f"  ✅  Accepted (relevant to Sri Lanka tourists): {len(accepted):,}")
    print(f"  ❌  Rejected (irrelevant / low score):         {len(rejected):,}")
    print(f"  📊  Filter pass rate: {len(accepted)/total:.1%}\n")
    print("  SOURCE BREAKDOWN (accepted records):")
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        print(f"    {src:<25} {count:>6,} records")

    print(f"\n  📁  Clean dataset saved to: {output_path}")

    # ── Optional audit log ───────────────────────────────────────────────────
    if audit and rejected:
        os.makedirs(os.path.dirname(reject_log_path), exist_ok=True)
        with open(reject_log_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=REJECT_FIELDNAMES)
            writer.writeheader()
            writer.writerows(rejected)
        print(f"  🔍  Rejection audit log saved to: {reject_log_path}")

        # Show top rejection reasons
        reasons = {}
        for r in rejected:
            reason = r["rejection_reason"] or "unknown"
            # Shorten scored reasons for display
            short = reason.split("(")[0].strip()
            reasons[short] = reasons.get(short, 0) + 1
        print("\n  REJECTION REASONS:")
        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"    {reason:<45} {count:>6,}")

    print("\n" + "=" * 65)
    return {
        "total": total,
        "accepted": len(accepted),
        "rejected": len(rejected),
        "output_path": output_path,
    }


def export_from_raw_items(raw_items: list, output_path: str, audit: bool = False):
    """
    Alternative entry point: filter and export from a list of raw pipeline items
    (dicts with 'source', 'title', 'content', 'url' keys).
    Used when you want to export pipeline results without writing to DB first.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    accepted = []
    rejected = []

    for i, item in enumerate(raw_items):
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        scoring = score_relevance(title, content)

        row = {
            "id": i + 1,
            "source": item.get("source", "unknown"),
            "source_url": item.get("url", ""),
            "title": title,
            "content": content,
            "location_name": item.get("location", ""),
            "latitude": item.get("latitude", ""),
            "longitude": item.get("longitude", ""),
            "scam_type": item.get("scam_type", ""),
            "risk_level": "",
            "sentiment_score": "",
            "is_scam": "",
            "relevance_score": round(scoring["total_score"], 2),
            "tourist_score": round(scoring["tourist_score"], 2),
            "negative_score": round(scoring["negative_score"], 2),
            "matched_signals": " | ".join(scoring["matched_signals"]),
            "created_at": datetime.utcnow().isoformat(),
        }

        if scoring["passes"]:
            accepted.append(row)
        else:
            rejected.append({
                "id": i + 1,
                "source": item.get("source", "unknown"),
                "source_url": item.get("url", ""),
                "title": title[:120],
                "content_preview": content[:200].replace("\n", " "),
                "rejection_reason": scoring["rejection_reason"],
                "total_score": round(scoring["total_score"], 2),
                "negative_score": round(scoring["negative_score"], 2),
                "tourist_score": round(scoring["tourist_score"], 2),
            })

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(accepted)

    return {"accepted": len(accepted), "rejected": len(rejected), "output_path": output_path}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Export clean Sri Lanka tourist safety dataset")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="Output CSV path")
    parser.add_argument("--audit", action="store_true", help="Also save rejection audit log")
    args = parser.parse_args()

    export_clean_dataset(output_path=args.out, audit=args.audit)
