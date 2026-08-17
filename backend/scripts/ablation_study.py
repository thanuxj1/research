"""
Ablation Study — SafeTravel LK Scoring System
IT22629180

Computes district risk rankings under four model variants and reports
Spearman rank-correlation between each variant and the full model.

Variants:
  V1 — Raw incident count (no weighting, no decay)
  V2 — + Source credibility weighting
  V3 — + Temporal decay (published_at if available, else created_at)
  V4 — Full model (V3 + exposure-adjusted base_risk for 8 SLTDA districts)

Usage:
    cd backend
    python -m scripts.ablation_study

This is a research audit tool, not part of the live API.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__) + "/..")

import math
from datetime import datetime, timezone
from scipy.stats import spearmanr
from app.db.session import SessionLocal
from app.db.models import Report
from app.core.district_engine import DECAY_LAMBDA, get_boundary_index


def resolve_district(report) -> str | None:
    """Map a report to its district using the same point-in-polygon path the
    live scoring engine uses. Using location_name strings instead causes the
    ablation to measure a different unit than the map (city names vs district
    polygons), which invalidates the comparison."""
    lat = getattr(report, "latitude", None)
    lon = getattr(report, "longitude", None)
    if lat is None or lon is None:
        return None
    return get_boundary_index().locate(lat, lon)

# ── Constants ─────────────────────────────────────────────────────────────────
SEVERITY_W = 0.70
SCAM_RATIO_W = 0.30

# SLTDA published footfall (Jan–Oct 2024, 8 districts only)
OFFICIAL_FOOTFALL = {
    "Colombo": 4_193_342, "Galle": 2_671_580, "Gampaha": 2_100_780,
    "Kandy": 1_722_666, "Matale": 1_249_150, "Kalutara": 1_181_326,
    "Matara": 1_170_772, "Badulla": 818_133,
}


def _days_ago(report) -> float:
    dt = getattr(report, "published_at", None) or getattr(report, "created_at", None)
    if not dt:
        return 0
    if hasattr(dt, "tzinfo") and dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - dt).days)


def score_districts(reports, variant: str) -> dict[str, float]:
    """Returns {district: score} for the given variant."""
    aggregated: dict[str, dict] = {}
    for r in reports:
        d = resolve_district(r)         # same point-in-polygon path district_engine uses
        if not d or d.lower() in {"sri lanka", "national"}:
            continue                    # national-scope records are not district evidence
        if d not in aggregated:
            aggregated[d] = {"count": 0, "w_evidence": 0.0, "w_sev_n": 0.0, "w_sev_d": 0.0, "scam_count": 0}
        a = aggregated[d]
        a["count"] += 1
        src_w = getattr(r, "source_weight", 0.35) or 0.35
        days = _days_ago(r)
        decay = math.exp(-DECAY_LAMBDA * days) if variant in ("V3", "V4") else 1.0
        w = decay * (src_w if variant in ("V2", "V3", "V4") else 1.0)
        a["w_evidence"] += w
        is_scam = bool(getattr(r, "is_scam", False))
        risk = getattr(r, "risk_level", 1) or 1
        if is_scam:
            a["scam_count"] += 1
            a["w_sev_n"] += w * (risk / 3.0)
            a["w_sev_d"] += w

    scores = {}
    for d, a in aggregated.items():
        if variant == "V1":
            scores[d] = a["count"]
        else:
            e = max(a["w_evidence"], 1e-9)
            sev = a["w_sev_n"] / max(a["w_sev_d"], 1e-9)
            ratio = a["w_sev_n"] / e
            base = SEVERITY_W * sev + SCAM_RATIO_W * ratio
            if variant == "V4" and d in OFFICIAL_FOOTFALL:
                rate = (a["w_sev_n"] / OFFICIAL_FOOTFALL[d]) * 100_000
                base = min(base * (1.0 + 0.20 * min(rate / 10.0, 1.0)), 1.0)
            scores[d] = base
    return scores


def main():
    db = SessionLocal()
    try:
        reports = db.query(Report).all()
        print(f"Loaded {len(reports)} reports from DB\n")

        v1 = score_districts(reports, "V1")
        v2 = score_districts(reports, "V2")
        v3 = score_districts(reports, "V3")
        v4 = score_districts(reports, "V4")

        districts = sorted(v4, key=lambda d: -v4[d])
        print(f"{'District':<18} {'V1-rank':>7} {'V2-rank':>7} {'V3-rank':>7} {'V4-rank':>7}  {'V4 Score':>9}")
        print("-" * 62)
        v1r = {d: i+1 for i, d in enumerate(sorted(v1, key=lambda x: -v1[x]))}
        v2r = {d: i+1 for i, d in enumerate(sorted(v2, key=lambda x: -v2[x]))}
        v3r = {d: i+1 for i, d in enumerate(sorted(v3, key=lambda x: -v3[x]))}
        v4r = {d: i+1 for i, d in enumerate(sorted(v4, key=lambda x: -v4[x]))}
        for d in districts[:15]:
            print(f"{d:<18} {v1r.get(d,'—'):>7} {v2r.get(d,'—'):>7} {v3r.get(d,'—'):>7} {v4r.get(d,'—'):>7}  {v4[d]:>9.4f}")

        shared = [d for d in v4 if d in v1 and d in v2 and d in v3]
        _v4s = [v4[d] for d in shared]
        rho12, p12 = spearmanr([v1[d] for d in shared], _v4s)
        rho23, p23 = spearmanr([v2[d] for d in shared], _v4s)
        rho34, p34 = spearmanr([v3[d] for d in shared], _v4s)

        print("\nSpearman ρ vs full model (V4):")
        print(f"  V1 (raw count)             ρ = {rho12:.3f}  (p={p12:.3f})")
        print(f"  V2 (+source weighting)     ρ = {rho23:.3f}  (p={p23:.3f})")
        print(f"  V3 (+temporal decay)       ρ = {rho34:.3f}  (p={p34:.3f})")
        print("\nInterpretation: ρ < 0.7 indicates meaningful rank change from that component.")
        print("If all ρ ≥ 0.95, the weighting/decay components have minimal empirical effect at this corpus size.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
