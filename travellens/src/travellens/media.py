"""
TravelLens LK -- the storyboard layer (YouTube, Reddit, Sri Lankan news).

What this is
------------
Context shown ALONGSIDE a destination: videos people made, threads travellers
wrote, and news articles about the place. It is reading material, not evidence.

THE HARD RULE: this data never enters a calculation
---------------------------------------------------
Nothing here is counted, scored, aggregated, or allowed to move a complaint
rate. The reasons are not stylistic:

  * A YouTube title is written to attract clicks, not to describe a visit.
  * A Reddit thread is one person plus a comment section, not a sample.
  * A news article covers the unusual by definition -- reporting on a drowning
    says nothing about how dangerous a place is on an ordinary day.

Counting any of it would corrupt every number the dashboard publishes. So the
separation is structural, not a promise:

  * media items live in data/processed/media.csv, a different file from the
    review corpus
  * they carry `media_id`, never `review_id` or `segment_id`
  * aggregate.build_tree() reads segments only; it has no code path that opens
    this file
  * the dashboard renders them in a separate panel labelled as context

What the NLP does here
----------------------
Two jobs, both about ROUTING, neither about measurement:

  1. Which destination is this item about? -- name and alias matching against
     the corpus destination list, so an item appears under the right place.
  2. What is it about? -- the same aspect tagger used elsewhere, so a video
     about a road can be labelled "roads & access". A display label only; it
     is never counted toward the roads complaint rate.

Sentiment is deliberately NOT run on these items. A model score on a headline
would look like a measurement, and someone would eventually treat it as one.

Run with:  python scripts/21_ingest_media.py <collector_output.json>
"""
import hashlib
import json
import re
from datetime import date
from typing import Dict, List, Optional

import pandas as pd

from . import config as C

MEDIA_CSV = C.DATA_PROCESSED / "media.csv"

MEDIA_COLUMNS = [
    "media_id", "kind", "title", "url", "source_name", "published",
    "snippet", "destination", "district", "aspects", "match_method",
    "collected_at",
]

# Sri Lankan outlets treated as credible, taken from the collector already in
# the parent project (backend/data_pipeline/scrape_sl_news_v3.py). Anything from
# a domain not on this list is rejected rather than shown -- an unsourced claim
# next to a destination is worse than no claim.
CREDIBLE_NEWS_DOMAINS = {
    "dailymirror.lk": "Daily Mirror",
    "dailynews.lk": "Daily News",
    "sundaytimes.lk": "The Sunday Times",
    "island.lk": "The Island",
    "adaderana.lk": "Ada Derana",
    "newsfirst.lk": "News First",
    "hirunews.lk": "Hiru News",
    "newswire.lk": "Newswire",
    "ceylontoday.lk": "Ceylon Today",
    "economynext.com": "EconomyNext",
    "ft.lk": "Daily FT",
}

KINDS = {"youtube", "reddit", "news"}

_NON_ALNUM = re.compile(r"[^a-z0-9 ]")
_WS = re.compile(r"\s+")

# Tokens too generic to identify a place on their own. Matching on "beach" or
# "temple" alone would attach an item to dozens of unrelated destinations.
STOPWORD_TOKENS = {
    # geographic / feature nouns
    "beach", "temple", "falls", "fall", "waterfall", "lake", "park", "rock",
    "hill", "hills", "point", "view", "viewpoint", "national", "bay", "island",
    "garden", "gardens", "museum", "fort", "tower", "cave", "caves", "river",
    "mountain", "peak", "forest", "reserve", "sanctuary", "estate", "valley",
    "pool", "pond", "springs", "spring", "bridge", "road", "street", "city",
    "town", "village", "area", "place", "site", "land", "sea", "water",
    # tourism / institutional vocabulary -- "tourism" alone matched a headline
    # about national arrival figures to a park with "Tourism" in its name
    "tourism", "tourist", "tourists", "travel", "resort", "hotel", "centre",
    "center", "complex", "agro", "technology", "heritage", "ancient", "old",
    "new", "great", "royal", "sacred", "holy",
    # country / language
    "sri", "lanka", "srilanka", "ceylon", "the", "of", "and", "maha", "raja",
}


def _norm(text: str) -> str:
    return _WS.sub(" ", _NON_ALNUM.sub(" ", str(text).lower())).strip()


def make_media_id(url: str) -> str:
    """Stable id from the URL, so re-collecting cannot duplicate an item."""
    return "m_" + hashlib.sha1(str(url).strip().lower().encode("utf-8")).hexdigest()[:14]


def domain_of(url: str) -> str:
    m = re.match(r"https?://(?:www\.)?([^/]+)", str(url))
    return m.group(1).lower() if m else ""


# --------------------------------------------------------------------------
# Destination matching
# --------------------------------------------------------------------------
class DestinationMatcher:
    """Links a title/snippet to a destination in the corpus.

    Matching is conservative. An item that cannot be tied to one place with
    reasonable confidence is dropped rather than guessed at -- showing a video
    about Ella under a waterfall in Matale is worse than showing nothing.
    """

    # A single-token match is only allowed when the token is genuinely rare in
    # the corpus. Measured: the unrestricted fallback matched "star" to Star
    # Fort, "kandy" to Kandy Lake and "community" to Community Tsunami Museum
    # -- 3 wrong out of 4 attempts. Full-name matching was 35 for 35.
    #
    # Rather than delete the fallback (which would also lose the one correct
    # case, "Yapahuwa"), rarity is derived from the data: a token qualifies only
    # if it appears in fewer than this share of reviews. A real place name like
    # "yapahuwa" is rare; "star", "kandy" and "community" are not.
    RARE_TOKEN_MAX_DF = 0.002      # 0.2% of reviews

    def __init__(self, destinations: pd.DataFrame, corpus_text=None):
        self.common = set()
        if corpus_text is not None and len(corpus_text):
            from collections import Counter
            n_docs = len(corpus_text)
            df = Counter()
            for txt in corpus_text:
                df.update(set(_norm(txt).split()))
            self.common = {t for t, c in df.items()
                           if c / n_docs > self.RARE_TOKEN_MAX_DF}

        self.rows = []
        for r in destinations.itertuples(index=False):
            norm = _norm(r.destination)
            toks = [t for t in norm.split()
                    if t not in STOPWORD_TOKENS and len(t) > 3
                    and t not in self.common]
            self.rows.append({
                "destination": r.destination,
                "district": r.district,
                "norm": norm,
                "distinctive": toks,
            })

    def match(self, text: str, strict: bool = False) -> Optional[Dict]:
        """strict=True disables the single-token fallback entirely.

        Used for news. Token rarity is measured against the REVIEW corpus, and
        a word can be rare there while being ordinary in journalism -- which is
        exactly how "community" matched a government-programme story to the
        Community Tsunami Museum. Reviews and news are different registers, so
        a rarity threshold learned from one does not transfer to the other.
        """
        t = " " + _norm(text) + " "
        # 1. full destination name present -- the strongest signal
        best = None
        for row in self.rows:
            if row["norm"] and (" " + row["norm"] + " ") in t:
                if best is None or len(row["norm"]) > len(best["norm"]):
                    best = row
        if best:
            return {"destination": best["destination"], "district": best["district"],
                    "match_method": "full_name"}
        # 2. a distinctive token ("sembuwatta", "yapahuwa") -- unique enough
        if strict:
            return None
        hits = []
        for row in self.rows:
            for tok in row["distinctive"]:
                if (" " + tok + " ") in t:
                    hits.append((tok, row))
        if len(hits) == 1:
            tok, row = hits[0]
            return {"destination": row["destination"], "district": row["district"],
                    "match_method": "distinctive_token:" + tok}
        return None


# --------------------------------------------------------------------------
# Normalisation of collector output
# --------------------------------------------------------------------------
def from_youtube(items: List[Dict]) -> List[Dict]:
    out = []
    for v in items:
        url = v.get("url") or ""
        if not url:
            continue
        out.append({
            "kind": "youtube",
            "title": v.get("title", ""),
            "url": url,
            "source_name": v.get("channel") or v.get("channelTitle") or "YouTube",
            "published": (v.get("published") or v.get("publishedAt") or "")[:10],
            "snippet": (v.get("description") or v.get("transcript") or "")[:400],
        })
    return out


def from_reddit(items: List[Dict]) -> List[Dict]:
    out = []
    for p in items:
        url = p.get("url") or p.get("permalink") or ""
        if not url:
            continue
        sub = p.get("subreddit") or ""
        out.append({
            "kind": "reddit",
            "title": p.get("title", ""),
            "url": url if url.startswith("http") else "https://reddit.com" + url,
            "source_name": ("r/" + sub) if sub else "Reddit",
            "published": str(p.get("created") or p.get("created_utc") or "")[:10],
            "snippet": (p.get("selftext") or p.get("content") or "")[:400],
        })
    return out


def from_news(items: List[Dict]) -> List[Dict]:
    """Only whitelisted Sri Lankan outlets survive this."""
    out = []
    for a in items:
        url = a.get("url") or a.get("link") or ""
        dom = domain_of(url)
        # Items from a targeted search carry the publisher stated by the feed;
        # those are kept with the outlet shown so a reader can judge it. Items
        # without one must match the domain whitelist -- an unattributable
        # claim beside a destination is worse than no claim.
        outlet = a.get("outlet")
        if not outlet:
            for known, name in CREDIBLE_NEWS_DOMAINS.items():
                if dom.endswith(known):
                    outlet = name
                    break
        if not outlet:
            continue
        out.append({
            "kind": "news",
            "title": a.get("title", ""),
            "url": url,
            "source_name": outlet,
            "published": str(a.get("published") or a.get("date") or "")[:10],
            "snippet": (a.get("summary") or a.get("content") or "")[:400],
            "destination_hint": a.get("destination_hint"),
            "district_hint": a.get("district_hint"),
        })
    return out


ADAPTERS = {"youtube": from_youtube, "reddit": from_reddit, "news": from_news}


def normalise(items: List[Dict], kind: str, matcher: DestinationMatcher,
              collected_at: Optional[str] = None, verbose: bool = True) -> pd.DataFrame:
    if kind not in ADAPTERS:
        raise ValueError("kind must be one of {}".format(sorted(KINDS)))
    collected_at = collected_at or date.today().isoformat()

    from .aspects import tag_segment

    raw = ADAPTERS[kind](items)
    rows, unmatched = [], 0
    for item in raw:
        text = "{} {}".format(item["title"], item["snippet"])

        # A destination_hint means the item came from a search FOR that
        # destination, so its subject is KNOWN rather than inferred. This is
        # what removes the false-match problem from targeted collection: the
        # earlier untargeted news pass guessed wrong three times out of four.
        hint = item.get("destination_hint")
        if hint:
            hit = {"destination": hint,
                   "district": item.get("district_hint") or "",
                   "match_method": "search_query"}
            rows.append({
                "media_id": make_media_id(item["url"]),
                "kind": item["kind"],
                "title": item["title"][:300],
                "url": item["url"],
                "source_name": item["source_name"],
                "published": item["published"],
                "snippet": item["snippet"],
                "destination": hit["destination"],
                "district": hit["district"],
                "aspects": "|".join(tag_segment(text)),
                "match_method": hit["match_method"],
                "collected_at": collected_at,
            })
            continue

        # News and Reddit are matched strictly: full destination name only.
        #
        # The single-token fallback only earns its place on YouTube, where a
        # title about a place names the place ("Yapahuwa Kingdom of Ancient Sri
        # Lanka"). General prose does not: a moderator update matched
        # "community" to the Community Tsunami Museum, and a political story
        # matched "parliament" to the Old Parliament Building. Rarity measured
        # on the review corpus does not transfer to those registers.
        hit = matcher.match(text, strict=(kind in ("news", "reddit")))
        if not hit:
            unmatched += 1
            continue
        rows.append({
            "media_id": make_media_id(item["url"]),
            "kind": item["kind"],
            "title": item["title"][:300],
            "url": item["url"],
            "source_name": item["source_name"],
            "published": item["published"],
            "snippet": item["snippet"],
            "destination": hit["destination"],
            "district": hit["district"],
            # Display label only. Never counted toward any aspect rate.
            "aspects": "|".join(tag_segment(text)),
            "match_method": hit["match_method"],
            "collected_at": collected_at,
        })
    df = pd.DataFrame(rows, columns=MEDIA_COLUMNS)
    if verbose:
        print("  {:<10} parsed {:>4} | matched to a place {:>4} | dropped {:>4}".format(
            kind, len(raw), len(df), unmatched))
    return df


def merge(new: pd.DataFrame, verbose: bool = True) -> Dict:
    existing = pd.read_csv(MEDIA_CSV) if MEDIA_CSV.exists() else pd.DataFrame(columns=MEDIA_COLUMNS)
    have = set(existing["media_id"]) if len(existing) else set()
    fresh = new[~new["media_id"].isin(have)].drop_duplicates(subset=["media_id"])
    combined = pd.concat([existing, fresh], ignore_index=True)
    C.DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    combined.to_csv(MEDIA_CSV, index=False, encoding="utf-8")
    if verbose:
        print("  media store: {} -> {}  (+{} new)".format(len(existing), len(combined), len(fresh)))
    return {"before": int(len(existing)), "after": int(len(combined)), "added": int(len(fresh))}


def load_matcher() -> DestinationMatcher:
    corpus = pd.read_csv(C.CLEAN_REVIEWS_CSV)
    dests = corpus[["destination", "district"]].drop_duplicates("destination")
    # Review text is passed in so token rarity is measured against how people
    # actually write, rather than guessed from a hand-written stoplist.
    return DestinationMatcher(dests, corpus_text=corpus["text"].astype(str).tolist())


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Ingest storyboard media (never counted).")
    ap.add_argument("input", help="collector output .json")
    ap.add_argument("--kind", required=True, choices=sorted(KINDS))
    args = ap.parse_args(argv)

    print("\nTravelLens LK -- storyboard media ingestion\n" + "=" * 60)
    print("  NOTE: these items are displayed only. They never enter any count.\n")
    with open(args.input, encoding="utf-8") as fh:
        data = json.load(fh)
    if isinstance(data, dict):
        data = data.get("items") or data.get("results") or []
    df = normalise(data, args.kind, load_matcher())
    merge(df)


if __name__ == "__main__":
    main()
