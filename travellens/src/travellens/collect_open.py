"""
TravelLens LK -- collection from openly licensed sources.

Why this module exists
----------------------
Google Maps and TripAdvisor both prohibit automated extraction in their terms.
There is no careful way to write a scraper for them that makes it permitted, so
this project does not have one. Reddit's public JSON endpoint now returns 403
without an authenticated app.

That left the storyboard thin. These three sources are openly licensed, expose
documented public APIs, and ask only that you identify yourself and go slowly:

  Wikivoyage    CC BY-SA 4.0   travel guide text -- "Get in", "Stay safe"
  Wikipedia     CC BY-SA 4.0   encyclopaedic description of the place
  OpenStreetMap ODbL           coordinates and tags, via the Nominatim service

None needs a key. All are attributed in the output, because their licences
require it and because an unattributed excerpt is worthless as evidence.

What this is for
----------------
Storyboard context only, exactly like the YouTube and news items: displayed
beside a destination, never counted. A Wikivoyage "Stay safe" note is written
by an editor, not by a visitor, and folding it into a complaint rate would mix
two completely different kinds of statement.

Nominatim's usage policy caps automated use at one request per second with a
real User-Agent. That is honoured here; the shared Fetcher already enforces it.

Run with:  python scripts/25_collect_open.py --limit 25
"""
import json
from typing import Dict, List, Optional

from .collect import Fetcher, write

WIKIVOYAGE_API = "https://en.wikivoyage.org/w/api.php"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"
NOMINATIM = "https://nominatim.openstreetmap.org/search"

# Sections of a Wikivoyage article that carry the kind of practical content
# this project is about. "History" and "Buy" are skipped -- interesting, but
# not what a complaint dashboard is for.
USEFUL_SECTIONS = ("get in", "get around", "stay safe", "see", "do", "sleep")


def _wiki_search(fetcher: Fetcher, api: str, query: str,
                 limit: int = 1) -> List[Dict]:
    r = fetcher.get(api, params={
        "action": "query", "list": "search", "srsearch": query,
        "srlimit": limit, "format": "json", "srnamespace": 0})
    if r.status_code != 200:
        return []
    return r.json().get("query", {}).get("search", []) or []


def _wiki_extract(fetcher: Fetcher, api: str, title: str) -> str:
    r = fetcher.get(api, params={
        "action": "query", "prop": "extracts", "titles": title,
        "explaintext": 1, "exsectionformat": "plain", "format": "json"})
    if r.status_code != 200:
        return ""
    pages = r.json().get("query", {}).get("pages", {})
    for p in pages.values():
        return p.get("extract", "") or ""
    return ""


def collect_wiki(fetcher: Fetcher, destinations: List[Dict], site: str = "wikivoyage",
                 verbose: bool = True) -> List[Dict]:
    """One article per destination, if a confident title match exists."""
    api = WIKIVOYAGE_API if site == "wikivoyage" else WIKIPEDIA_API
    base = ("https://en.wikivoyage.org/wiki/" if site == "wikivoyage"
            else "https://en.wikipedia.org/wiki/")
    label = "Wikivoyage" if site == "wikivoyage" else "Wikipedia"
    out = []
    for d in destinations:
        q = "{} Sri Lanka".format(d["destination"])
        try:
            hits = _wiki_search(fetcher, api, q, limit=1)
            if not hits:
                continue
            title = hits[0]["title"]
            # Require the destination's own words to appear in the article
            # title. Wiki search will happily return "Sri Lanka" for anything,
            # and a national article under a waterfall is worse than nothing.
            dest_words = {w.lower() for w in str(d["destination"]).split()
                          if len(w) > 3}
            title_words = {w.lower().strip(",()") for w in title.split()}
            if dest_words and not (dest_words & title_words):
                continue
            extract = _wiki_extract(fetcher, api, title)
            if not extract or len(extract) < 120:
                continue
            out.append({
                "title": "{} — {}".format(title, label),
                "url": base + title.replace(" ", "_"),
                "source_name": "{} (CC BY-SA 4.0)".format(label),
                "published": "",
                "description": extract[:600],
                "destination_hint": d["destination"],
            })
            if verbose:
                print("    {:<32} -> {}".format(d["destination"][:30], title[:38]))
        except Exception as exc:
            if verbose:
                print("    {:<32} failed: {}".format(d["destination"][:30],
                                                     type(exc).__name__))
    return out


def collect_osm(fetcher: Fetcher, destinations: List[Dict],
                verbose: bool = True) -> List[Dict]:
    """Coordinates from OpenStreetMap via Nominatim.

    This is the missing piece for a pin map: neither review corpus carries
    latitude or longitude. ODbL requires attribution, which is carried on every
    row. Nominatim asks for at most one request per second -- enforced by the
    shared Fetcher -- and a genuine User-Agent, which the runner sets.
    """
    out = []
    for d in destinations:
        # Query forms, tried in order. Comma-separated parts are parsed as a
        # STRUCTURED address, and our district is sometimes not the one OSM
        # records -- "Sembuwatta lake, Matale, Sri Lanka" returns nothing while
        # "Sembuwatta lake Sri Lanka" resolves, because OSM files that lake
        # under Kandy District. Free-text first, name alone as a last resort.
        forms = [
            "{} Sri Lanka".format(d["destination"]),
            str(d["destination"]),
        ]
        try:
            res = []
            for q in forms:
                r = fetcher.get(NOMINATIM, params={
                    "q": q, "format": "json", "limit": 1, "countrycodes": "lk"})
                if r.status_code != 200:
                    continue
                res = r.json()
                if res:
                    break
            if not res:
                if verbose:
                    print("    {:<32} not found".format(d["destination"][:30]))
                continue
            hit = res[0]
            out.append({
                "destination": d["destination"],
                "district": d.get("district", ""),
                "lat": float(hit["lat"]),
                "lon": float(hit["lon"]),
                "osm_type": hit.get("type", ""),
                "display_name": hit.get("display_name", ""),
                "licence": "OpenStreetMap contributors, ODbL",
            })
            if verbose:
                print("    {:<32} {:.4f}, {:.4f}".format(
                    d["destination"][:30], float(hit["lat"]), float(hit["lon"])))
        except Exception as exc:
            if verbose:
                print("    {:<32} failed: {}".format(d["destination"][:30],
                                                     type(exc).__name__))
    return out
