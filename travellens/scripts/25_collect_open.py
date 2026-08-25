"""Collect from openly licensed sources. No API key required.

  python scripts/25_collect_open.py --what wikivoyage --limit 25
  python scripts/25_collect_open.py --what osm --limit 60

Sources: Wikivoyage (CC BY-SA), Wikipedia (CC BY-SA), OpenStreetMap (ODbL).
All three permit automated access; all three require attribution, which is
carried through into the output.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402
from travellens.collect import Fetcher, write  # noqa: E402
from travellens.collect_open import collect_osm, collect_wiki  # noqa: E402


def destinations(n):
    df = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    top = (df.groupby(["destination", "district"]).size()
             .sort_values(ascending=False).head(n).reset_index())
    return top[["destination", "district"]].to_dict("records")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", required=True,
                    choices=["wikivoyage", "wikipedia", "osm", "all"])
    ap.add_argument("--limit", type=int, default=25)
    ap.add_argument("--max-requests", type=int, default=140)
    args = ap.parse_args()

    print("\nTravelLens LK -- openly licensed collection\n" + "=" * 60)
    print("  No API key needed. One request per second per host.")
    print("  Wikivoyage/Wikipedia CC BY-SA 4.0 | OpenStreetMap ODbL\n")

    f = Fetcher(max_requests=args.max_requests)
    dests = destinations(args.limit)
    wanted = (["wikivoyage", "wikipedia", "osm"] if args.what == "all"
              else [args.what])

    for site in ("wikivoyage", "wikipedia"):
        if site in wanted:
            print("  [{}] {} destinations".format(site, len(dests)))
            items = collect_wiki(f, dests, site=site)
            write(items, site)
            print()

    if "osm" in wanted:
        print("  [osm] geocoding {} destinations via Nominatim".format(len(dests)))
        rows = collect_osm(f, dests)
        out = C.DATA_PROCESSED / "destination_coordinates.csv"
        if rows:
            existing = (pd.read_csv(out) if out.exists()
                        else pd.DataFrame(columns=list(rows[0].keys())))
            merged = (pd.concat([existing, pd.DataFrame(rows)], ignore_index=True)
                        .drop_duplicates(subset=["destination"], keep="last"))
            merged.to_csv(out, index=False, encoding="utf-8")
            print("\n  coordinates: {} destinations -> {}".format(len(merged), out))
        print()

    print("=" * 60)
    print("  HTTP requests made: {}".format(f.n))
    print("\n  next: python scripts/21_ingest_media.py "
          "data/incoming/wikivoyage_*.json --kind news")


if __name__ == "__main__":
    main()
