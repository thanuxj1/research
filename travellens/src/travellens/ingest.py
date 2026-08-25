"""
LostinSriLanka -- Stage 8: ingestion of newly collected reviews.

Takes freshly scraped reviews, normalises them into the corpus schema, and
merges them without ever double-counting.

The safety property that matters
--------------------------------
Merging is IDEMPOTENT. Re-scraping the same destination returns mostly reviews
we already hold; each one hashes to the same review_id it did the first time,
so it is recognised and skipped. Running the same refresh five times produces
exactly the same corpus as running it once.

Without this, every refresh would inflate the complaint counts and the
published numbers would drift upward for no real reason.

Adapters
--------
Two input shapes are supported out of the box, matching the two ways Google
Maps reviews can be collected:

  from_apify_items()      compass/crawler-google-places actor output
  from_places_api()       Google Places API Place Details `reviews` array

Both produce the same normalised records, so everything downstream is
indifferent to which collector was used.

Run with:  python scripts/09_ingest.py <new_reviews.json|csv> --district Matale
"""
import json
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from . import config as C
from .clean import make_review_id, normalise_text, parse_timespan, recency_bucket, word_count

CORPUS_COLUMNS = [
    "review_id", "destination", "district", "district_raw",
    "text", "n_words", "is_truncated", "months_ago", "recency",
    "source", "collected_at", "rating", "source_url",
]


# --------------------------------------------------------------------------
# Adapters: collector output -> normalised records
# --------------------------------------------------------------------------
def from_apify_items(items: List[Dict], district: Optional[str] = None) -> List[Dict]:
    """compass/crawler-google-places actor output.

    Each item is a place with a nested `reviews` list. Star ratings ARE present
    here (`stars`), unlike the Kaggle corpus -- we keep them, because they give
    an independent check on the model in Stage 6.
    """
    out = []
    for item in items:
        place = item.get("title") or item.get("name") or item.get("placeName")
        for rev in item.get("reviews", []) or []:
            out.append({
                "destination": place,
                "district": district or item.get("city") or item.get("neighborhood"),
                "text": rev.get("text") or rev.get("textTranslated") or "",
                "timespan": rev.get("publishedAtDate") or rev.get("publishAt") or "",
                "rating": rev.get("stars") or rev.get("rating"),
                "source": "apify_google_places",
                "source_url": rev.get("reviewUrl") or rev.get("url"),
            })
    return out


def from_places_api(results: List[Dict], district: Optional[str] = None) -> List[Dict]:
    """Google Places API Place Details output (the `reviews` array, max ~5)."""
    out = []
    for res in results:
        place = res.get("name")
        for rev in res.get("reviews", []) or []:
            out.append({
                "destination": place,
                "district": district,
                "text": rev.get("text") or "",
                "timespan": rev.get("relative_time_description") or "",
                "rating": rev.get("rating"),
                "source": "google_places_api",
                "source_url": rev.get("reviewUrl") or rev.get("url"),
            })
    return out


def from_records(records: List[Dict], district: Optional[str] = None) -> List[Dict]:
    """Already-flat records: destination / district / text / timespan / rating."""
    out = []
    for r in records:
        out.append({
            "destination": r.get("destination") or r.get("Destination"),
            "district": r.get("district") or r.get("District") or district,
            "text": r.get("text") or r.get("Review") or "",
            "timespan": r.get("timespan") or r.get("Timespan") or "",
            "rating": r.get("rating"),
            "source": r.get("source") or "manual",
        })
    return out


# --------------------------------------------------------------------------
# Normalisation -- identical rules to Stage 1, so old and new rows are
# processed the same way. Any divergence here would make the corpus internally
# inconsistent, which is worse than collecting nothing.
# --------------------------------------------------------------------------
def normalise(records: List[Dict], collected_at: Optional[str] = None) -> pd.DataFrame:
    collected_at = collected_at or date.today().isoformat()
    rows, rejected = [], {"no_text": 0, "too_short": 0, "no_place": 0}

    for r in records:
        dest = (r.get("destination") or "").strip()
        if not dest:
            rejected["no_place"] += 1
            continue
        text = normalise_text(r.get("text") or "")
        if not text:
            rejected["no_text"] += 1
            continue
        n_words = word_count(text)
        if n_words < C.MIN_WORDS:
            rejected["too_short"] += 1
            continue

        district_raw = (r.get("district") or "").strip()
        timespan = r.get("timespan") or ""
        months = parse_timespan(timespan)
        rows.append({
            "review_id": make_review_id(dest, text, timespan),
            "destination": dest,
            "district": C.DISTRICT_CANON.get(district_raw, district_raw),
            "district_raw": district_raw,
            "text": text,
            "n_words": n_words,
            "is_truncated": C.TRUNCATION_MARKER in (r.get("text") or ""),
            "months_ago": months,
            "recency": recency_bucket(months),
            "source": r.get("source") or "unknown",
            "collected_at": collected_at,
            "rating": r.get("rating"),
            # Captured at collection time; see clean.py for why legacy rows are empty.
            "source_url": r.get("source_url") or r.get("url") or r.get("permalink"),
        })

    df = pd.DataFrame(rows, columns=CORPUS_COLUMNS)
    df.attrs["rejected"] = rejected
    return df


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------
def merge_into_corpus(new_df: pd.DataFrame, corpus_path=None,
                      dry_run: bool = False, verbose: bool = True) -> Dict:
    """Append genuinely-new reviews to the corpus. Idempotent by review_id."""
    corpus_path = corpus_path or C.CLEAN_REVIEWS_CSV
    corpus = pd.read_csv(corpus_path)

    # Route incoming place names onto the destinations already in the corpus.
    # Without this, "Sembuwatta Lake" from a fresh scrape becomes a second
    # destination alongside the existing "Sembuwatta lake", splitting its
    # reviews across two entries and understating both. Done BEFORE the
    # review_id is recomputed, since the id is built from the destination name.
    from .canonical import build_loose_index, build_map, resolve
    mapping = build_map(corpus["destination"])
    loose = build_loose_index(mapping)

    routed = new_df["destination"].map(lambda d: resolve(d, mapping, loose))
    n_routed = int((routed != new_df["destination"]).sum())
    if n_routed and verbose:
        changed = new_df.loc[routed != new_df["destination"], "destination"]
        print("  routed {} reviews onto existing destinations:".format(n_routed))
        for old, new in list(dict(zip(changed, routed[routed != new_df["destination"]])).items())[:5]:
            print("      {!r} -> {!r}".format(old, new))
    new_df = new_df.copy()
    new_df["destination"] = routed
    new_df["review_id"] = [
        make_review_id(d, t) for d, t in zip(new_df["destination"], new_df["text"])
    ]

    # Older corpora predate the provenance columns; backfill rather than fail.
    for col, default in (("source", "kaggle_2024_03"),
                         ("collected_at", "2024-03-25"),
                         ("rating", pd.NA)):
        if col not in corpus.columns:
            corpus[col] = default

    existing = set(corpus["review_id"])
    incoming_total = len(new_df)

    new_df = new_df.drop_duplicates(subset=["review_id"])
    within_batch_dupes = incoming_total - len(new_df)

    fresh = new_df[~new_df["review_id"].isin(existing)]
    already_held = len(new_df) - len(fresh)

    report = {
        "incoming": incoming_total,
        "duplicates_within_batch": within_batch_dupes,
        "already_in_corpus": already_held,
        "added": int(len(fresh)),
        "corpus_before": int(len(corpus)),
        "corpus_after": int(len(corpus) + len(fresh)),
        "rejected": new_df.attrs.get("rejected", {}),
        "new_destinations": sorted(set(fresh["destination"]) - set(corpus["destination"])),
        "dry_run": dry_run,
    }

    if not dry_run and len(fresh):
        combined = pd.concat([corpus, fresh[CORPUS_COLUMNS]], ignore_index=True)
        combined.to_csv(corpus_path, index=False, encoding="utf-8")

    if verbose:
        print("  incoming reviews      : {}".format(report["incoming"]))
        print("  dupes within batch    : {}".format(report["duplicates_within_batch"]))
        print("  already in corpus     : {}  <- skipped, not double-counted".format(
            report["already_in_corpus"]))
        print("  ADDED                 : {}".format(report["added"]))
        print("  corpus {} -> {}".format(report["corpus_before"], report["corpus_after"]))
        if report["new_destinations"]:
            print("  new destinations      : {}".format(", ".join(report["new_destinations"][:8])))
        if dry_run:
            print("  (dry run -- nothing written)")
    return report


def load_input(path: str, district: Optional[str] = None) -> List[Dict]:
    """Read a collector dump. JSON list, JSON lines, or CSV."""
    p = str(path)
    if p.endswith(".csv"):
        return from_records(pd.read_csv(p).to_dict("records"), district)

    with open(p, encoding="utf-8") as fh:
        head = fh.read(2048)
        fh.seek(0)
        if head.lstrip().startswith("["):
            data = json.load(fh)
        else:
            data = [json.loads(line) for line in fh if line.strip()]

    # Detect which collector produced this file.
    if data and isinstance(data[0], dict) and "reviews" in data[0]:
        if "stars" in json.dumps(data[0].get("reviews", [])[:1]):
            return from_apify_items(data, district)
        return from_places_api(data, district)
    return from_records(data, district)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Ingest newly collected reviews.")
    ap.add_argument("input", help="collector output: .json, .jsonl or .csv")
    ap.add_argument("--district", help="district to assign when the file omits it")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    args = ap.parse_args(argv)

    print("\nLostinSriLanka -- Stage 8: ingestion\n" + "=" * 60)
    records = load_input(args.input, args.district)
    print("  parsed {} raw records from {}".format(len(records), args.input))

    df = normalise(records)
    rej = df.attrs["rejected"]
    print("  rejected: {} no text, {} too short, {} no place".format(
        rej["no_text"], rej["too_short"], rej["no_place"]))
    print("  normalised {} reviews".format(len(df)))
    print()
    merge_into_corpus(df, dry_run=args.dry_run)
    if not args.dry_run:
        print("\n  next: python scripts/10_refresh.py")


if __name__ == "__main__":
    main()
