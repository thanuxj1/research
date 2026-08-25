"""
TravelLens LK -- TripAdvisor corpus adapter.

Brings dataset/Reviews.csv (16,156 TripAdvisor reviews) into the same corpus
schema as the Google Maps data, so both can be processed by one pipeline and
compared against each other.

Why this dataset matters -- it fixes four separate limitations at once
---------------------------------------------------------------------
1. STAR RATINGS. Every review carries one. These are the weak-supervision
   labels the Google corpus could not provide, available immediately and
   without scraping anything.

2. REAL DATES. Published_Date is an absolute timestamp spanning 2011-2023, not
   a relative string. Genuine temporal analysis becomes possible -- including
   the visible collapse in arrivals (4,034 reviews in 2019, 114 in 2021).

3. GEOGRAPHIC COVERAGE. It covers Kandy, Anuradhapura, Jaffna, Trincomalee,
   Polonnaruwa, Batticaloa and Kegalle -- precisely the districts the Google
   corpus is missing and which the choropleth currently renders as hatched.

4. A DIFFERENT AUDIENCE. Of 16,156 reviewers, exactly ONE lists Sri Lanka as
   their home. The rest are overwhelmingly UK (4,446), Australia (1,990) and
   India (1,621). Google Maps reviews of the same country skew local. So the
   two corpora capture different populations, and the difference between what
   each complains about is a finding in itself -- not noise to be averaged away.

Because of (4) the two sources must stay separable. They are, via the `source`
column, and the aggregator can build the tree from either or both.

Run with:  python scripts/14_ingest_tripadvisor.py
"""
import json
import re
from typing import Dict, Optional

import pandas as pd

from . import config as C
from .clean import make_review_id, normalise_text, recency_bucket, word_count
from .ingest import CORPUS_COLUMNS

SOURCE_CSV = C.DATA_RAW / "tripadvisor_reviews.csv"
SOURCE_TAG = "tripadvisor"

# Reference point for converting absolute dates into the "months ago" field the
# Google corpus uses. Fixed to the dataset's own last observation so the value
# is stable across re-runs -- using "today" would silently change every row's
# recency bucket each time the pipeline ran.
REFERENCE_DATE = pd.Timestamp("2023-05-20", tz="UTC")

# City -> administrative district. Resolved from the dataset's own `Location`
# field, which names the district or province for most rows.
CITY_TO_DISTRICT: Dict[str, str] = {
    "Nuwara Eliya": "Nuwara Eliya",
    "Pussellawa": "Kandy",           # dataset says "Kandy District"
    "Katukitula": "Kandy",           # dataset says "Kandy District"
    "Kandy": "Kandy",
    "Peradeniya": "Kandy",
    "Anuradhapura": "Anuradhapura",
    "Saliyapura": "Anuradhapura",
    "Habarana": "Anuradhapura",      # town sits in Anuradhapura District
    "Polonnaruwa": "Polonnaruwa",
    "Sigiriya": "Matale",
    "Colombo": "Colombo",
    "Negombo": "Gampaha",
    "Kalutara": "Kalutara",
    "Beruwala": "Kalutara",
    "Bentota": "Galle",
    "Hikkaduwa": "Galle",
    "Ambalangoda": "Galle",
    "Galle": "Galle",
    "Unawatuna": "Galle",
    "Ahangama": "Galle",
    "Mirissa": "Matara",
    "Deniyaya": "Matara",
    "Tissamaharama": "Hambantota",
    "Weligatta": "Hambantota",
    "Kalametiya": "Hambantota",
    "Ella": "Badulla",
    "Haputale": "Badulla",
    "Koslanda": "Badulla",
    "Embilipitiya": "Ratnapura",
    "Pinnawala": "Kegalle",
    "Jaffna": "Jaffna",
    "Trincomalee": "Trincomalee",
    "Nilaveli": "Trincomalee",
    "Kalkudah": "Batticaloa",
    "Arugam Bay": "Ampara",
    "Ampara": "Ampara",
}

_DISTRICT_IN_LOCATION = re.compile(r"([A-Za-z ]+?)\s+District", re.IGNORECASE)


def resolve_district(city: str, location: str) -> Optional[str]:
    """Prefer the explicit district in `Location`; fall back to the city map."""
    if isinstance(location, str):
        m = _DISTRICT_IN_LOCATION.search(location)
        if m:
            name = m.group(1).strip()
            if name:
                return name
    return CITY_TO_DISTRICT.get(str(city).strip())


def load(path=None, verbose: bool = True) -> pd.DataFrame:
    """Read the TripAdvisor CSV and normalise it into the corpus schema."""
    path = path or SOURCE_CSV
    raw = pd.read_csv(path, encoding="utf-8", encoding_errors="replace",
                      low_memory=False)
    report = {"source_file": str(path), "rows_in": int(len(raw))}

    df = raw.dropna(subset=["Text", "Location_Name"]).copy()
    report["dropped_missing"] = int(len(raw) - len(df))

    # The title is part of the review and is often its sharpest statement
    # ("Too expensive for what it is"). Prepending it as a sentence lets the
    # segmenter treat it as one more opinion unit rather than discarding it.
    title = df["Title"].fillna("").astype(str).str.strip()
    body = df["Text"].fillna("").astype(str).str.strip()
    combined = (title.where(title.str.endswith((".", "!", "?")), title + ".")
                + " " + body).str.strip()
    df["text"] = combined.map(normalise_text)
    df["n_words"] = df["text"].map(word_count)

    before = len(df)
    df = df[df["n_words"] >= C.MIN_WORDS]
    report["dropped_too_short"] = int(before - len(df))

    df["destination"] = df["Location_Name"].astype(str).str.strip()
    df["district_raw"] = df["Located_City"].astype(str).str.strip()
    df["district"] = [
        resolve_district(c, l) for c, l in zip(df["Located_City"], df["Location"])
    ]

    unmapped = df["district"].isna()
    report["unmapped_cities"] = sorted(
        set(df.loc[unmapped, "district_raw"])) if unmapped.any() else []
    report["dropped_unmapped"] = int(unmapped.sum())
    df = df[~unmapped]

    # Absolute date -> months before the fixed reference point.
    dt = pd.to_datetime(df["Published_Date"], errors="coerce", utc=True)
    df["review_date"] = dt.dt.date.astype(str)
    df["months_ago"] = ((REFERENCE_DATE - dt).dt.days / 30.44).round(1)
    df["recency"] = df["months_ago"].map(recency_bucket)

    df["is_truncated"] = False        # full text, not a "read more" excerpt
    df["source"] = SOURCE_TAG
    df["collected_at"] = "2023-05-20"
    df["rating"] = pd.to_numeric(df["Rating"], errors="coerce")
    # Empty: this export preserved no review permalink, and a TripAdvisor
    # review URL cannot be reconstructed without a listing id and a review id.
    # See provenance.py -- destination-level links are offered instead.
    df["source_url"] = pd.NA

    df["review_id"] = [
        make_review_id(d, t) for d, t in zip(df["destination"], df["text"])
    ]
    before = len(df)
    df = df.drop_duplicates(subset=["review_id"])
    report["dropped_duplicates"] = int(before - len(df))

    out = df[CORPUS_COLUMNS + ["review_date"]].reset_index(drop=True)
    report["rows_out"] = int(len(out))
    report["destinations"] = int(out["destination"].nunique())
    report["districts"] = sorted(out["district"].unique())
    report["rating_distribution"] = out["rating"].value_counts().sort_index().to_dict()
    report["median_words"] = float(out["n_words"].median())
    out.attrs["report"] = report

    if verbose:
        print("  rows in            : {}".format(report["rows_in"]))
        print("  dropped missing    : {}".format(report["dropped_missing"]))
        print("  dropped too short  : {}".format(report["dropped_too_short"]))
        print("  dropped unmapped   : {}".format(report["dropped_unmapped"]))
        print("  dropped duplicates : {}".format(report["dropped_duplicates"]))
        print("  ROWS OUT           : {}".format(report["rows_out"]))
        print("  destinations       : {}".format(report["destinations"]))
        print("  districts          : {}".format(len(report["districts"])))
        print("  median words       : {}  (Google corpus: 18)".format(
            int(report["median_words"])))
    return out


def main():
    print("\nTravelLens LK -- TripAdvisor ingestion\n" + "=" * 60)
    ta = load()

    corpus = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    if "review_date" not in corpus.columns:
        corpus["review_date"] = pd.NA

    existing = set(corpus["review_id"])
    fresh = ta[~ta["review_id"].isin(existing)]
    print("\n  already in corpus : {}".format(len(ta) - len(fresh)))
    print("  ADDING            : {}".format(len(fresh)))

    combined = pd.concat([corpus, fresh], ignore_index=True)
    combined.to_csv(C.CLEAN_REVIEWS_CSV, index=False, encoding="utf-8")

    print("\n  corpus {} -> {}".format(len(corpus), len(combined)))
    print("  by source:")
    for src, n in combined["source"].value_counts().items():
        print("    {:<22} {}".format(src, n))
    print("  districts now: {}".format(combined["district"].nunique()))
    new_districts = sorted(set(combined["district"]) - set(corpus["district"]))
    if new_districts:
        print("  NEW districts: {}".format(", ".join(new_districts)))

    with open(C.REPORTS / "tripadvisor_ingest.json", "w", encoding="utf-8") as fh:
        json.dump(ta.attrs["report"], fh, indent=2, ensure_ascii=False, default=str)
    print("\n  next: python scripts/10_refresh.py")


if __name__ == "__main__":
    main()
