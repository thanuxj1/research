"""
TravelLens LK -- targeted news collection.

Why this replaces the RSS-feed approach
---------------------------------------
The first attempt pulled the front-page RSS of eight Sri Lankan outlets: 55
articles, none about any destination. Those feeds carry national news --
politics, business, cricket -- and a waterfall appears in them roughly never.

This searches *for each destination by name* instead. Two consequences:

  1. Relevance. An article only appears if it matched a query naming the place.
  2. No matching ambiguity. The old approach had to guess which destination an
     article concerned, and guessed wrong three times out of four -- matching
     "community" to the Community Tsunami Museum and "parliament" to the Old
     Parliament Building. Here the destination is the query, so attribution is
     known rather than inferred.

Source
------
Google News RSS: a published feed at a documented URL, consumed as a feed. It
aggregates publishers rather than hosting articles, so every item is attributed
to its original outlet and links there.

Outlet filtering
----------------
Two modes. `sri_lankan_only` keeps the established local outlets already
whitelisted for this project. `any_named` keeps anything, on the grounds that a
named international outlet reporting on a Sri Lankan site is legitimate context
-- but the outlet name is always shown, so a reader judges the source.

Anonymous or unattributable items are dropped either way.

Run with:  python scripts/28_collect_news_targeted.py --limit 40
"""
import re
import time
from typing import Dict, List, Optional
from urllib.parse import quote_plus

FEED = ("https://news.google.com/rss/search?q={q}"
        "&hl=en-LK&gl=LK&ceid=LK:en")

PAUSE_SECONDS = 1.5

_ITEM = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_TAG = {t: re.compile(r"<{0}[^>]*>(.*?)</{0}>".format(t), re.S | re.I)
        for t in ("title", "link", "pubDate", "source", "description")}
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_HTML = re.compile(r"<[^>]+>")
_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
             "&#39;": "'", "&apos;": "'", "&nbsp;": " "}

# Google News appends " - Outlet Name" to headlines. Split it off so the
# outlet can be shown separately and the headline reads cleanly.
_TRAILING_SOURCE = re.compile(r"\s+-\s+([^-]{2,40})$")


def _clean(v: str) -> str:
    v = _CDATA.sub(r"\1", v or "")
    v = _HTML.sub(" ", v)
    for ent, ch in _ENTITIES.items():
        v = v.replace(ent, ch)
    return re.sub(r"\s+", " ", v).strip()


def _parse_items(xml: str) -> List[Dict]:
    out = []
    for raw in _ITEM.findall(xml):
        def get(tag):
            m = _TAG[tag].search(raw)
            return _clean(m.group(1)) if m else ""
        title, link = get("title"), get("link")
        if not title or not link:
            continue
        outlet = get("source")
        if not outlet:
            m = _TRAILING_SOURCE.search(title)
            if m:
                outlet = m.group(1).strip()
                title = title[:m.start()].strip()
        out.append({"title": title, "url": link,
                    "outlet": outlet, "published": get("pubDate")[:16]})
    return out


def collect(destinations: List[Dict], mode: str = "any_named",
            per_destination: int = 3, verbose: bool = True) -> List[Dict]:
    """One search per destination. `mode` is 'any_named' or 'sri_lankan_only'."""
    import requests

    from .collect import USER_AGENT
    from .media import CREDIBLE_NEWS_DOMAINS

    local_names = {v.lower() for v in CREDIBLE_NEWS_DOMAINS.values()}
    out, seen = [], set()

    for i, d in enumerate(destinations):
        if i:
            time.sleep(PAUSE_SECONDS)
        name = d["destination"]
        # Quote the name so the search treats it as a phrase; add the country
        # so "Moon plains" does not return astronomy articles.
        q = quote_plus('"{}" Sri Lanka'.format(name))
        try:
            r = requests.get(FEED.format(q=q), timeout=20,
                             headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                if verbose:
                    print("    {:<32} HTTP {}".format(name[:30], r.status_code))
                continue
            items = _parse_items(r.text)
            kept = 0
            for it in items:
                if kept >= per_destination or it["url"] in seen:
                    continue
                outlet = it["outlet"]
                if not outlet:
                    continue                       # unattributable -- drop
                if mode == "sri_lankan_only" and outlet.lower() not in local_names:
                    continue
                seen.add(it["url"])
                out.append({
                    "title": it["title"],
                    "url": it["url"],
                    # Carried through so ingestion does not have to guess which
                    # destination this concerns -- it was the search term.
                    "destination_hint": name,
                    "district_hint": d.get("district", ""),
                    "outlet": outlet,
                    "published": it["published"],
                })
                kept += 1
            if verbose and kept:
                print("    {:<32} {} articles".format(name[:30], kept))
        except Exception as exc:
            if verbose:
                print("    {:<32} failed: {}".format(name[:30], type(exc).__name__))
    return out
