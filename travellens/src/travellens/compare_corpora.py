"""
TravelLens LK -- cross-corpus comparison.

Asks whether the two corpora complain about different things, and then tests
whether any difference survives the obvious confound.

The question
------------
Google Maps reviews of Sri Lankan sites and TripAdvisor reviews of Sri Lankan
sites are written by different populations. Of 16,156 TripAdvisor reviewers,
exactly one lists Sri Lanka as home; the rest are predominantly UK, Australian
and Indian. So a difference between the corpora may reflect a difference
between domestic and international visitors.

The confound that must be tested first
--------------------------------------
The corpora do not cover the same places. The Google corpus is dominated by
waterfalls, pools and viewpoints -- inherently hazardous outdoor sites. The
TripAdvisor corpus is dominated by religious sites, museums, historic sites and
gardens. A raw comparison of safety complaints would therefore measure WHERE
each platform's users went, not what they cared about.

This module reports the raw comparison AND the same comparison stratified by
place type. Only differences that survive stratification are reported as
findings.

An honest limit that stratification cannot fix
----------------------------------------------
The Google corpus carries NO reviewer-origin field. "Domestic" is inferred from
the platform, not observed. The defensible claim is therefore about a
PLATFORM difference; the audience interpretation is a hypothesis supported by
TripAdvisor's own user data and unverifiable on the Google side. The thesis
must say so in those words.

Run with:  python scripts/15_compare_corpora.py
"""
import json
from typing import Dict

import pandas as pd

from . import config as C

TRIPADVISOR_CSV = C.ROOT.parent / "dataset" / "Reviews.csv"

# Place-type strata present in both corpora. The Google corpus has no type
# field, so its membership is matched on destination name.
STRATA = {
    "Waterfalls": {
        "ta_type": "Waterfalls",
        "name_pattern": r"\bella\b|falls?|waterfall",
    },
    "Religious sites": {
        "ta_type": "Religious Sites",
        "name_pattern": r"temple|vihara|kovil|mosque|dagoba|stupa",
    },
    "Beaches": {
        "ta_type": "Beaches",
        "name_pattern": r"beach|bay\b",
    },
    "Parks & gardens": {
        "ta_type": "Gardens",
        "name_pattern": r"\bpark\b|garden",
    },
}

MIN_CELL = 15   # below this the stratum is reported but not tested


def _rate(sub: pd.DataFrame, pol_col: str):
    n = int((sub[pol_col] == "N").sum())
    p = int((sub[pol_col] == "P").sum())
    return n, p, (round(100 * n / (n + p), 1) if (n + p) else None)


def load(pol_col: str = "pol_final") -> pd.DataFrame:
    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv")
    rev = pd.read_csv(C.CLEAN_REVIEWS_CSV)[["review_id", "source"]]
    d = seg[(seg["n_aspects"] > 0) & seg[pol_col].notna()].merge(
        rev, on="review_id", how="left")

    if TRIPADVISOR_CSV.exists():
        ta = pd.read_csv(TRIPADVISOR_CSV, encoding="utf-8",
                         encoding_errors="replace", low_memory=False)
        type_map = (ta.drop_duplicates("Location_Name")
                      .set_index("Location_Name")["Location_Type"].to_dict())
        d["ta_type"] = d["destination"].map(type_map)
    else:
        d["ta_type"] = None
    return d


def raw_comparison(d: pd.DataFrame, pol_col: str = "pol_final") -> pd.DataFrame:
    rows = []
    for key, aspect in C.ASPECTS.items():
        sub = d[d["asp_" + key]]
        row = {"aspect": aspect.label}
        for src, name in (("kaggle_2024_03", "google"), ("tripadvisor", "tripadvisor")):
            n, p, rate = _rate(sub[sub["source"] == src], pol_col)
            row[name + "_n"] = n
            row[name + "_rate"] = rate
        if row["google_rate"] is not None and row["tripadvisor_rate"] is not None:
            row["gap_pp"] = round(row["tripadvisor_rate"] - row["google_rate"], 1)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("gap_pp", ascending=False)


def stratified(d: pd.DataFrame, aspect: str, pol_col: str = "pol_final") -> Dict:
    """Same comparison within matched place types."""
    try:
        from scipy.stats import chi2_contingency
    except ImportError:
        chi2_contingency = None

    name = d["destination"].str.lower()
    out = {}
    for label, spec in STRATA.items():
        g = d[(d["source"] == "kaggle_2024_03")
              & name.str.contains(spec["name_pattern"], regex=True, na=False)
              & d["asp_" + aspect]]
        t = d[(d["source"] == "tripadvisor")
              & (d["ta_type"] == spec["ta_type"])
              & d["asp_" + aspect]]

        gn, gp, grate = _rate(g, pol_col)
        tn, tp, trate = _rate(t, pol_col)
        entry = {
            "google": {"complaints": gn, "praise": gp, "rate": grate},
            "tripadvisor": {"complaints": tn, "praise": tp, "rate": trate},
        }
        if grate is not None and trate is not None:
            entry["gap_pp"] = round(trate - grate, 1)
            small = min(gn + gp, tn + tp) < MIN_CELL
            entry["underpowered"] = small
            if chi2_contingency and not small:
                chi2, p, _, _ = chi2_contingency([[gn, gp], [tn, tp]])
                entry["chi2"] = round(float(chi2), 2)
                entry["p_value"] = float(p)
                entry["significant_p05"] = bool(p < 0.05)
        out[label] = entry
    return out


def main():
    print("\nTravelLens LK -- cross-corpus comparison\n" + "=" * 66)
    d = load()
    print("  segments: {}".format(d["source"].value_counts().to_dict()))

    raw = raw_comparison(d)
    print("\nRAW comparison -- complaint rate by corpus")
    print("  {:<20} {:>9} {:>13} {:>8}".format("aspect", "google", "tripadvisor", "gap"))
    print("  " + "-" * 54)
    for r in raw.itertuples(index=False):
        print("  {:<20} {:>8}% {:>12}% {:>+8}".format(
            r.aspect, r.google_rate, r.tripadvisor_rate, r.gap_pp))
    print("\n  WARNING: the corpora cover different places. Google is dominated by")
    print("  waterfalls and viewpoints; TripAdvisor by religious and historic sites.")
    print("  Nothing above is a finding until it survives stratification.")

    results = {"raw": raw.to_dict("records"), "stratified": {}}
    for aspect in ("safety", "cleanliness", "crowd", "price_value"):
        strat = stratified(d, aspect)
        results["stratified"][aspect] = strat
        print("\n{} -- controlled for place type".format(C.ASPECTS[aspect].label.upper()))
        print("  {:<18} {:>9} {:>13} {:>8}  {}".format(
            "stratum", "google", "tripadvisor", "gap", "test"))
        print("  " + "-" * 62)
        for label, e in strat.items():
            if e.get("gap_pp") is None:
                continue
            verdict = ("underpowered (n<{})".format(MIN_CELL) if e.get("underpowered")
                       else ("p={:.4f} {}".format(e["p_value"],
                             "SIGNIFICANT" if e.get("significant_p05") else "n.s.")
                             if "p_value" in e else ""))
            print("  {:<18} {:>8}% {:>12}% {:>+8}  {}".format(
                label, e["google"]["rate"], e["tripadvisor"]["rate"],
                e["gap_pp"], verdict))

    with open(C.REPORTS / "corpus_comparison.json", "w", encoding="utf-8") as fh:
        json.dump(results, fh, indent=2)
    print("\nwrote {}".format(C.REPORTS / "corpus_comparison.json"))
    print("\nREPORTING RULE: describe results as a PLATFORM difference. The Google")
    print("corpus has no reviewer-origin field, so 'domestic' is inferred from the")
    print("platform, not observed. State that limitation explicitly.")


if __name__ == "__main__":
    main()
