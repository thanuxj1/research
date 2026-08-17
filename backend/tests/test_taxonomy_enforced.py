"""
P3 regression test — all scam_type values in DB must be canonical.
IT22629180

Run after any bulk ingestion to catch non-canonical taxonomy values
before they accumulate and corrupt type-frequency analyses.
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_all_scam_types_are_canonical():
    from app.core.scam_taxonomy import CANONICAL_SCAM_TYPES
    from app.db.session import SessionLocal
    from app.db.models import Report

    db = SessionLocal()
    try:
        bad = {
            r.scam_type for r in db.query(Report).all()
            if r.scam_type and r.scam_type not in CANONICAL_SCAM_TYPES
        }
    finally:
        db.close()

    assert not bad, (
        f"Non-canonical scam_type values in DB: {sorted(bad)}. "
        f"Run normalise_scam_type() at every insert site (see PATCHES.md §P3)."
    )
