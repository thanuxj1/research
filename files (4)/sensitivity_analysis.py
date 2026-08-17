"""
Parameter Sensitivity Analysis — SafeTravel LK district scoring
IT22629180

Every constant in the district risk formula is a researcher-chosen free
parameter:

    H     decay half-life (days)              default 180
    beta  severity weight vs scam-ratio       default 0.70
    alpha Bayesian shrinkage pseudo-count     default 0.05
    pi    global prior                        default 0.30
    T1/T2 confidence thresholds (5 / 15)

A panel is entitled to ask "why 0.70?" for each of them. "It seemed reasonable"
is not an answer. This script produces the answer: a table showing how much the
district ranking moves when each parameter is swept, so that each value can be
defended as either (a) consequential and chosen for a stated reason, or
(b) inconsequential at this corpus size, which is itself a reportable result.

Reads the exported corpus CSV directly, so it runs without the database.

Usage
-----
    python sensitivity_analysis.py --csv dataset_exports/safety_incidents_dataset.csv
    python sensitivity_analysis.py --csv data.csv --json sensitivity.json

Reporting
---------
Kendall tau-b between each perturbed ranking and the default ranking:

    tau >= 0.95   parameter is inert at this corpus size — say so explicitly
    0.70-0.95     parameter is consequential — justify the chosen value
    tau <  0.70   ranking is unstable under this parameter — the headline
                  ordering must be presented with that caveat
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

DEFAULTS = {"half_life": 180.0, "beta": 0.70, "alpha": 0.05, "prior": 0.30}
MIN_REPORTS = 5           # below this a district is 'insufficient_data'


# ─────────────────────────────────────────────────────────────────────────────

def wilson_lower(k: float, n: float, z: float = 1.96) -> float:
    """Wilson score lower bound. Stops a single report reaching a ratio of 1.0."""
    if n <= 0:
        return 0.0
    p = min(max(k / n, 0.0), 1.0)
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, centre - half)


def score_districts(df: pd.DataFrame, half_life: float, beta: float,
                    alpha: float, prior: float,
                    demographic_mult: dict[str, float] | None = None,
                    min_reports: int = MIN_REPORTS) -> dict[str, float]:
    """District scores under one parameter set. Mirrors district_engine.py."""
    lam = math.log(2) / half_life
    now = datetime.now(timezone.utc)
    agg: dict[str, dict] = {}

    for _, r in df.iterrows():
        d = str(r.get("district") or "").strip()
        if not d or d.lower() in {"sri lanka", "national", "nan"}:
            continue          # national-scope records are not district evidence

        ts = r.get("published_at") or r.get("created_at")
        try:
            dt = pd.to_datetime(ts, utc=True, errors="coerce")
            days = 0.0 if pd.isna(dt) else max(0.0, (now - dt.to_pydatetime()).days)
        except Exception:
            days = 0.0

        decay = math.exp(-lam * days)
        src_w = float(r.get("source_weight") or 0.35)
        w = decay * src_w

        a = agg.setdefault(d, {"n": 0, "E": 0.0, "I": 0.0, "scam_n": 0})
        a["n"] += 1
        a["E"] += w

        if int(r.get("is_scam") or 0) == 1:
            risk = float(r.get("risk_level") or 1)
            contrib = w * (risk / 3.0)
            if demographic_mult:
                key = str(r.get("scam_type_normalised") or r.get("scam_type") or "")
                contrib *= demographic_mult.get(key, 1.0)
            a["I"] += contrib
            a["scam_n"] += 1

    out = {}
    for d, a in agg.items():
        if a["n"] < min_reports:
            continue
        severity = a["I"] / max(a["scam_n"], 1)
        ratio = wilson_lower(a["I"], max(a["E"], 1e-9))
        base = beta * severity + (1 - beta) * ratio
        out[d] = (a["n"] * base + alpha * prior) / (a["n"] + alpha)
    return out


def _ranking(scores: dict[str, float]) -> list[str]:
    return [d for d, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def _tau(a: dict[str, float], b: dict[str, float]) -> tuple[float, float, int]:
    shared = sorted(set(a) & set(b))
    if len(shared) < 3:
        return float("nan"), float("nan"), len(shared)
    t, p = kendalltau([a[d] for d in shared], [b[d] for d in shared])
    return float(t), float(p), len(shared)


def _verdict(tau: float) -> str:
    if math.isnan(tau):
        return "too few districts to assess"
    if tau >= 0.95:
        return "INERT — report as having no effect at this corpus size"
    if tau >= 0.70:
        return "CONSEQUENTIAL — the chosen value must be justified"
    return "UNSTABLE — ranking must be reported with this caveat"


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="Sweep every free parameter in district scoring.")
    ap.add_argument("--csv", required=True)
    ap.add_argument("--json")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)
    base = score_districts(df, **DEFAULTS)

    print("=" * 78)
    print("  PARAMETER SENSITIVITY — district risk ranking   [IT22629180]")
    print("=" * 78)
    print(f"  Corpus records      : {len(df)}")
    print(f"  Districts scored    : {len(base)} (>= {MIN_REPORTS} reports)")
    print(f"  Defaults            : {DEFAULTS}")
    print(f"\n  Default ranking     : {' > '.join(_ranking(base))}")

    sweeps = {
        "half_life": [30, 90, 180, 365, 730, 1e9],   # 1e9 ~ decay disabled
        "beta":      [0.0, 0.3, 0.5, 0.7, 0.9, 1.0],
        "alpha":     [0.05, 1.0, 5.0, 10.0, 20.0, 50.0],
        "prior":     [0.10, 0.20, 0.30, 0.40, 0.50],
    }

    results: dict = {"n_records": int(len(df)), "n_districts": len(base),
                     "defaults": DEFAULTS, "default_ranking": _ranking(base),
                     "sweeps": {}}

    for param, values in sweeps.items():
        print(f"\n{'-' * 78}")
        print(f"  SWEEP: {param}   (default {DEFAULTS[param]})")
        print(f"{'-' * 78}")
        print(f"  {'value':>12}{'tau':>9}{'p':>9}{'n':>5}   top-3 districts")
        rows = []
        for v in values:
            params = {**DEFAULTS, param: float(v)}
            s = score_districts(df, **params)
            t, p, n = _tau(base, s)
            label = "no decay" if (param == "half_life" and v >= 1e8) else f"{v:g}"
            top3 = ", ".join(_ranking(s)[:3])
            print(f"  {label:>12}{t:>9.3f}{p:>9.3f}{n:>5}   {top3}")
            rows.append({"value": label, "tau": t, "p": p, "n_shared": n,
                         "top3": _ranking(s)[:3]})
        worst = min((r["tau"] for r in rows if not math.isnan(r["tau"])), default=float("nan"))
        print(f"  -> min tau across sweep = {worst:.3f}  :: {_verdict(worst)}")
        results["sweeps"][param] = {"rows": rows, "min_tau": worst,
                                    "verdict": _verdict(worst)}

    # ── Demographic multiplier sensitivity (AUDIT B1) ────────────────────────
    print(f"\n{'-' * 78}")
    print("  SWEEP: demographic multipliers (+/- 25% perturbation, 200 draws)")
    print(f"{'-' * 78}")
    type_col = "scam_type_normalised" if "scam_type_normalised" in df.columns else "scam_type"
    types = [t for t in df[type_col].dropna().unique()]
    rng = np.random.default_rng(42)
    taus = []
    for _ in range(200):
        mult = {t: float(rng.uniform(0.75, 1.25)) for t in types}
        s = score_districts(df, **DEFAULTS, demographic_mult=mult)
        t, _, _ = _tau(base, s)
        if not math.isnan(t):
            taus.append(t)
    if taus:
        print(f"  Kendall tau vs unconditioned ranking over 200 random multiplier sets:")
        print(f"    mean {np.mean(taus):.3f}   min {np.min(taus):.3f}   "
              f"5th pct {np.percentile(taus, 5):.3f}")
        print(f"  -> {_verdict(float(np.min(taus)))}")
        print("\n  If tau stays near 1.0, the demographic multipliers do not change the")
        print("  district ordering at this corpus size. Report that as a finding and")
        print("  scope the demographic layer to incident SURFACING rather than scoring.")
        results["demographic_perturbation"] = {
            "mean_tau": float(np.mean(taus)), "min_tau": float(np.min(taus)),
            "p5_tau": float(np.percentile(taus, 5)), "n_draws": len(taus)}

    print(f"\n{'=' * 78}")
    print("  Put this table in the thesis. A parameter with no sensitivity table")
    print("  behind it is an unjustified researcher degree of freedom.")
    print(f"{'=' * 78}\n")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2, default=float)
        print(f"  Written to {args.json}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
