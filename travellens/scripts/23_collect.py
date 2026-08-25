"""Collection runner. Run: python scripts/23_collect.py --what reddit --limit 15

Sources:
  reddit   public JSON, no key
  news     RSS from whitelisted Sri Lankan outlets, no key
  youtube  YouTube Data API, needs YOUTUBE_API_KEY
  places   Google Places API, needs GOOGLE_MAPS_API_KEY  (BILLED per call)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from travellens import config as C  # noqa: E402
from travellens.collect import (Fetcher, collect_news, collect_places,  # noqa: E402
                                collect_reddit, collect_youtube, key_status,
                                load_env, write)


def top_destinations(n):
    df = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    top = (df.groupby(["destination", "district"]).size()
             .sort_values(ascending=False).head(n).reset_index())
    return top[["destination", "district"]].to_dict("records")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--what", required=True,
                    choices=["reddit", "news", "youtube", "places", "all"])
    ap.add_argument("--limit", type=int, default=10,
                    help="destinations (places) or results per query")
    ap.add_argument("--max-requests", type=int, default=60,
                    help="hard ceiling on HTTP requests this run")
    args = ap.parse_args()

    print("\nLostinSriLanka -- collection\n" + "=" * 60)
    env = load_env()
    ks = key_status(env)
    print("  credentials found (values never printed):")
    for k, present in ks.items():
        print("    {:<24} {}".format(k, "present" if present else "MISSING"))
    print("  request ceiling: {} | pause: 1.0s per host".format(args.max_requests))
    print()

    f = Fetcher(max_requests=args.max_requests)
    wanted = ["reddit", "news", "youtube", "places"] if args.what == "all" else [args.what]

    if "reddit" in wanted:
        print("  [reddit] public JSON, no key")
        items = collect_reddit(f, [
            "waterfall road condition", "entrance fee foreigners",
            "dangerous swimming", "worth visiting waterfall",
        ], limit=args.limit)
        write(items, "reddit")
        print()

    if "news" in wanted:
        print("  [news] RSS, whitelisted Sri Lankan outlets")
        write(collect_news(f), "news")
        print()

    if "youtube" in wanted:
        print("  [youtube] Data API")
        if not ks["YOUTUBE_API_KEY"]:
            print("    skipped -- YOUTUBE_API_KEY not set")
        else:
            dests = top_destinations(args.limit)
            queries = ["{} Sri Lanka".format(d["destination"]) for d in dests]
            write(collect_youtube(f, env["YOUTUBE_API_KEY"], queries,
                                  per_query=5), "youtube")
        print()

    if "places" in wanted:
        print("  [places] Google Places API -- BILLED, 2 calls per destination")
        if not ks["GOOGLE_MAPS_API_KEY"]:
            print("    skipped -- GOOGLE_MAPS_API_KEY not set")
        else:
            dests = top_destinations(args.limit)
            print("    {} destinations -> about {} billed calls".format(
                len(dests), 2 * len(dests)))
            write(collect_places(f, env["GOOGLE_MAPS_API_KEY"], dests), "places")
        print()

    print("=" * 60)
    print("  HTTP requests made this run: {}".format(f.n))
    print("\n  next:")
    print("    reviews : python scripts/09_ingest.py data/incoming/places_*.json")
    print("    media   : python scripts/21_ingest_media.py data/incoming/<file>.json --kind <kind>")


if __name__ == "__main__":
    main()
