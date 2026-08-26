"""Measure what the hand-written correction rules do to the published numbers.

  python scripts/33_ablate_rules.py

Rebuilds the tree with each rule switched off and reports the movement. This
is a SENSITIVITY analysis, not an accuracy one: it says how much of a finding
rests on a hand-written rule, not whether the rule is right. Accuracy needs
polarity ground truth, which this project does not have -- see open problem #1.

Reads the cached scored segments, so it makes no model calls and takes a few
seconds. Writes reports/rule_ablation.json.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from travellens import ablation  # noqa: E402
from travellens import config as C  # noqa: E402


def main():
    print("\nLostinSriLanka -- correction-rule sensitivity\n" + "=" * 60)
    print("  Impact, not accuracy: how far do the published numbers move")
    print("  when a hand-written rule is switched off?")

    seg = pd.read_csv(C.DATA_PROCESSED / "segments_scored.csv")
    reviews = None
    if C.CLEAN_REVIEWS_CSV.exists():
        reviews = pd.read_csv(C.CLEAN_REVIEWS_CSV, encoding="utf-8")

    results = ablation.run(seg, reviews=reviews)
    comparison = ablation.compare(results)

    print("\n" + "-" * 60)
    print("  {:<20} {:>10} {:>12} {:>12}".format(
        "variant", "largest", "move (pp)", "cards +/-"))
    for name, c in comparison.items():
        print("  {:<20} {:>10} {:>12} {:>12}".format(
            name, str(c["largest_move"]), c["largest_move_pp"],
            c["scorecards_delta"]))

    print("\n  per-aspect movement when a rule is removed:")
    for name, c in comparison.items():
        print("\n    [{}]".format(name))
        rows = sorted(c["aspects"].items(), key=lambda kv: -abs(kv[1]["delta_pp"]))
        for aspect, m in rows:
            if not m["delta_pp"]:
                continue
            print("      {:<18} {:>6.1f}% -> {:>6.1f}%  ({:+.2f} pp, "
                  "{:+d} complaints)".format(
                      aspect, m["deployed_rate"] * 100, m["variant_rate"] * 100,
                      m["delta_pp"], m["delta_negatives"]))

    print("\n  does the headline ranking survive?")
    base_rank = ablation._ranking(results["deployed"]["aspects"])
    print("    deployed          worst aspect: {}".format(base_rank[0]))
    for name, c in comparison.items():
        flag = "  <-- HEADLINE CHANGES" if c["top_aspect_changes"] else ""
        print("    {:<18} worst aspect: {}{}".format(
            name, c["ranking"][0], flag))

    path = ablation.save(results, comparison)
    print("\n  wrote {}".format(path))
    print("\n  Reminder: this shows DEPENDENCE, not correctness. Whether a")
    print("  flipped label is the right label needs the human gold set.")


if __name__ == "__main__":
    main()
