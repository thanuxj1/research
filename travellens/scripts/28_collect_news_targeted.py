"""Targeted per-destination news search. Free, no key.
Run: python scripts/28_collect_news_targeted.py --limit 40
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pandas as pd
from travellens import config as C
from travellens.collect import write
from travellens.collect_news_targeted import collect

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--mode", default="any_named", choices=["any_named","sri_lankan_only"])
    ap.add_argument("--per-destination", type=int, default=3)
    args = ap.parse_args()
    print("\nTravelLens LK -- targeted news search\n" + "=" * 60)
    print("  Google News RSS. One search per destination, so the article's")
    print("  destination is known rather than inferred.\n")
    df = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    dests = (df.groupby(["destination","district"]).size().sort_values(ascending=False)
               .head(args.limit).reset_index()[["destination","district"]].to_dict("records"))
    items = collect(dests, mode=args.mode, per_destination=args.per_destination)
    write(items, "news_targeted")
    print("\n  next: python scripts/21_ingest_media.py data/incoming/news_targeted_*.json --kind news")

if __name__ == "__main__":
    main()
