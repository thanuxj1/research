"""
TravelLens LK -- source links for quoted material.

The problem
-----------
Neither source dataset preserved a URL. The Kaggle Google Maps export carries
only (Destination, District, Timespan, Review); the TripAdvisor export carries
user and rating fields but no permalink, no review id and no listing id. So an
individual quoted sentence cannot be traced back to the review it came from.

This matters. Every complaint quote shown on the dashboard is, as things stand,
unverifiable: a reader has no way to confirm the sentence was ever written.

What can and cannot be fixed
----------------------------
CANNOT: per-review links. A Google Maps review URL requires a place id and a
review id. Neither exists in the data and neither can be reconstructed from it.
Any URL invented here would be a fabrication.

CAN: per-DESTINATION links. A deterministic search URL takes a reader to the
place's own review page, where the quoted text can be searched for. That is
weaker than a permalink and is labelled as such -- "find this place", not
"open this review".

These links are built from the destination name alone. No API, no key, no
network call, nothing collected. They are constructed, not retrieved, so they
cannot go stale in the corpus and cost nothing to generate.

For anything collected in future
--------------------------------
The corpus schema now carries `source_url`. It is empty for the two legacy
datasets and populated at collection time for everything after, because a URL
captured during scraping is free and a URL reconstructed later is impossible.

Run with:  python scripts/22_build_provenance.py
"""
import json
import re
from typing import Dict
from urllib.parse import quote_plus

import pandas as pd

from . import config as C

PROVENANCE_JSON = C.DATA_PROCESSED / "destination_links.json"

# How each source's search interface is addressed. Documented URL patterns,
# constructed locally; nothing is fetched.
SEARCH_TEMPLATES = {
    "google_maps": ("Google Maps",
                    "https://www.google.com/maps/search/?api=1&query={q}"),
    "tripadvisor": ("TripAdvisor",
                    "https://www.tripadvisor.com/Search?q={q}"),
}

_WS = re.compile(r"\s+")


def _query(destination: str, district: str) -> str:
    """Destination plus district plus country, to disambiguate common names."""
    parts = [str(destination).strip()]
    d = str(district).strip()
    if d and d.lower() not in str(destination).lower():
        parts.append(d)
    parts.append("Sri Lanka")
    return _WS.sub(" ", " ".join(parts)).strip()


def links_for(destination: str, district: str) -> Dict[str, Dict[str, str]]:
    q = quote_plus(_query(destination, district))
    return {
        key: {"label": label, "url": tmpl.format(q=q)}
        for key, (label, tmpl) in SEARCH_TEMPLATES.items()
    }


def build(corpus_path=None, verbose: bool = True) -> Dict:
    corpus_path = corpus_path or C.CLEAN_REVIEWS_CSV
    df = pd.read_csv(corpus_path)

    # Which platforms actually contributed reviews for this destination -- only
    # offer a link to a source that plausibly holds the quoted text.
    src_map = {"kaggle_2024_03": "google_maps", "tripadvisor": "tripadvisor",
               "apify_google_places": "google_maps", "google_places_api": "google_maps"}
    out = {}
    for (dest, dist), g in df.groupby(["destination", "district"]):
        platforms = {src_map.get(s) for s in g["source"].unique()}
        platforms.discard(None)
        all_links = links_for(dest, dist)
        out[dest] = {
            "district": dist,
            "n_reviews": int(len(g)),
            "links": {k: v for k, v in all_links.items() if k in platforms},
            # Stated on the page so the weaker guarantee is never mistaken for
            # a permalink.
            "note": ("Links to the destination's page on the platform, not to "
                     "the individual review. The source datasets did not "
                     "preserve review URLs."),
        }

    C.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    with open(PROVENANCE_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    if verbose:
        both = sum(1 for v in out.values() if len(v["links"]) > 1)
        print("  destinations       : {}".format(len(out)))
        print("  with 2 platforms   : {}".format(both))
        print("  wrote {}".format(PROVENANCE_JSON))
    return out


def main():
    print("\nTravelLens LK -- destination source links\n" + "=" * 60)
    print("  NOTE: per-review links do not exist in either source dataset and")
    print("        cannot be reconstructed. These are destination-level search")
    print("        links, constructed locally -- nothing is fetched.\n")
    build()


if __name__ == "__main__":
    main()
