"""
LostinSriLanka -- what the hand-written correction rules actually do.

Why this is a sensitivity analysis and not an accuracy measurement
------------------------------------------------------------------
Three hand-written rules survive into the published numbers, and none had
ever been measured. The honest measurement would be accuracy: label a sample
by hand and check whether each rule moves labels towards the truth or away
from it. That cannot be done here, because the project has no polarity ground
truth -- the gold sets are aspect-only and unlabelled -- and producing labels
with the same assistant that wrote the rules would be exactly the circularity
that makes open problem #1 the highest-value task in the repository.

So this measures IMPACT instead: switch each rule off, rebuild the published
tree, and report how far the numbers move. That does not say a rule is right.
It says how much of the finding depends on it, which is the question a reader
should ask about any hand-written correction, and it puts a number on the risk
rather than leaving it unquantified.

Which rules exist, and which are actually deployed
--------------------------------------------------
Three reach the dashboard; a fourth listed in the README does not:

  request rule    polarity.final_polarity -- a politely phrased complaint
                  ("but need to clean the pond area") read as neutral by the
                  model is flipped to negative when the lexicon agrees.
                  DEPLOYED: it is what makes pol_final differ from pol_roberta.

  safety recall   aggregate + polarity.safety_recall_rule -- a segment tagged
                  safety, called neutral by the model, containing an explicit
                  hazard word, is flipped to negative.
                  DEPLOYED: applied while the tree is built.

  site rule       polarity.site_rule_is_not_a_complaint -- a reported
                  regulation ("prohibited to take polythene inside the park")
                  is not a grievance. DEPLOYED: applied after the safety
                  recall, so a prohibition carrying a hazard keeps its
                  negative label.

  domain patch    polarity.hybrid_polarity -- NOT DEPLOYED. It produces
                  pol_hybrid (Method C), which exists only to be compared
                  against in the write-up. The tree is built from pol_final,
                  so this rule cannot move a published figure. Listing it as an
                  unmeasured risk overstated the exposure.

Run with:  python scripts/33_ablate_rules.py
"""
import json
from typing import Dict, List

import pandas as pd

from . import config as C
from .aggregate import build_tree

REPORT_JSON = C.REPORTS / "rule_ablation.json"

# pol_roberta is Method D: the model's own answer, before the request rule.
VARIANTS = [
    ("deployed", "pol_final", True, True,
     "all three rules on -- the published numbers"),
    ("no_request_rule", "pol_roberta", True, True,
     "the model's own label, politely phrased complaints left neutral"),
    ("no_safety_recall", "pol_final", False, True,
     "hedged hazard warnings left as the model read them"),
    ("no_site_rule", "pol_final", True, False,
     "reported regulations counted as complaints again"),
    ("no_rules_at_all", "pol_roberta", False, False,
     "no hand-written correction anywhere in the polarity path"),
]


def _aspect_rates(tree: Dict) -> Dict[str, Dict]:
    return {k: {"complaint_rate": v.get("complaint_rate"),
                "n_negative": v.get("n_negative"),
                "n_opinions": v.get("n_opinions")}
            for k, v in tree.get("aspects", {}).items()}


def _displayed_scorecards(tree: Dict) -> int:
    """How many destination-aspect cards clear the display threshold.

    A rule that only moves a rate by a fraction of a point can still push
    destinations over or under MIN_MENTIONS_DISPLAY, which changes what the
    dashboard shows at all. That is a bigger deal than the rate itself.
    """
    n = 0
    for d in tree.get("districts", {}).values():
        for dest in d.get("destinations", {}).values():
            n += len(dest.get("aspects", {}))
    return n


def run(seg: pd.DataFrame, reviews=None, verbose: bool = True) -> Dict:
    results = {}
    for name, pol_col, recall, site, note in VARIANTS:
        if verbose:
            print("\n  [{}] {}".format(name, note))
        tree = build_tree(seg, pol_col=pol_col, reviews=reviews,
                          safety_recall=recall, site_rule=site)
        results[name] = {
            "note": note,
            "polarity_column": pol_col,
            "safety_recall": recall,
            "site_rule": site,
            "aspects": _aspect_rates(tree),
            "displayed_scorecards": _displayed_scorecards(tree),
            "n_destinations": tree.get("coverage", {}).get("n_destinations"),
        }
    return results


def _ranking(aspects: Dict) -> List[str]:
    """Aspects by complaint rate, worst first.

    The order matters more than the rates. The dashboard's headline sentence
    names whichever aspect ranks first, so a rule that reorders the top of
    this list changes a claim the reader sees, not just a number.
    """
    rated = [(k, v["complaint_rate"]) for k, v in aspects.items()
             if v.get("complaint_rate") is not None]
    return [k for k, _ in sorted(rated, key=lambda kv: -kv[1])]


def compare(results: Dict) -> Dict:
    """Every variant against the deployed numbers."""
    base = results["deployed"]
    out = {}
    for name, r in results.items():
        if name == "deployed":
            continue
        moves = {}
        for aspect, stats in r["aspects"].items():
            b = base["aspects"].get(aspect, {})
            if b.get("complaint_rate") is None or stats["complaint_rate"] is None:
                continue
            moves[aspect] = {
                "deployed_rate": b["complaint_rate"],
                "variant_rate": stats["complaint_rate"],
                "delta_pp": round(
                    (stats["complaint_rate"] - b["complaint_rate"]) * 100, 2),
                "delta_negatives": stats["n_negative"] - b["n_negative"],
            }
        ranked = sorted(moves.items(),
                        key=lambda kv: -abs(kv[1]["delta_pp"]))
        out[name] = {
            "note": r["note"],
            "aspects": moves,
            "ranking": _ranking(r["aspects"]),
            "top_aspect_changes": _ranking(r["aspects"])[0] != _ranking(base["aspects"])[0],
            "largest_move": ranked[0][0] if ranked else None,
            "largest_move_pp": ranked[0][1]["delta_pp"] if ranked else 0,
            "scorecards_delta":
                r["displayed_scorecards"] - base["displayed_scorecards"],
        }
    return out


def save(results: Dict, comparison: Dict, path=None) -> str:
    path = path or REPORT_JSON
    payload = {
        "what_this_is": ("Sensitivity analysis, not accuracy. It reports how "
                         "far the published numbers move when each "
                         "hand-written rule is switched off. It does not show "
                         "that a rule is correct -- the project has no "
                         "polarity ground truth."),
        "domain_patch": ("Not deployed. hybrid_polarity feeds pol_hybrid "
                         "(Method C), a comparison column; the tree is built "
                         "from pol_final."),
        "variants": results,
        "vs_deployed": comparison,
    }
    C.REPORTS.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=1, ensure_ascii=False)
    return str(path)
