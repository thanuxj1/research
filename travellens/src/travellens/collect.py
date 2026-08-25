"""
LostinSriLanka -- collection runner.

Collects fresh material through sanctioned interfaces only. Nothing here
scrapes a page that asks not to be scraped.

  reviews  Google Places API      needs GOOGLE_MAPS_API_KEY   ~5 reviews/place
  video    YouTube Data API       needs YOUTUBE_API_KEY
  reddit   Reddit public JSON     no key, rate-limited to 1 request/second
  news     RSS from 11 whitelisted Sri Lankan outlets   no key

Credentials are read from travellens/.env and never printed. The runner reports
which keys it found, never their values.

Cost note
---------
The Places API is billed per request beyond Google's monthly free credit. Every
run prints the number of API calls it made so the spend is visible rather than
discovered on a statement. YouTube, Reddit and RSS are free at this volume.

Politeness
----------
One request per second to Reddit and to each RSS host, a descriptive
User-Agent, and a hard cap on requests per run. A research project has no
business hammering anyone's servers.

Run with:  python scripts/23_collect.py --what reddit --limit 20
"""
import json
import os
import re
import time
from datetime import date, datetime
from typing import Dict, List, Optional
from urllib.parse import quote_plus

from . import config as C

# Credentials live inside the project so it is self-contained. Falls back
# to the parent project's file if this one is absent.
ENV_PATH = C.ROOT / ".env"
ENV_FALLBACK = C.ROOT.parent / "backend" / ".env"
OUT_DIR = C.ROOT / "data" / "incoming"

USER_AGENT = ("LostinSriLanka/1.0 (final-year research project; "
              "tourism review analysis; contact via project repository)")

REQUEST_PAUSE = 1.0          # seconds between requests to the same host
MAX_REQUESTS_PER_RUN = 200   # hard ceiling, whatever the caller asks for

NEWS_RSS = {
    "Ada Derana": "https://www.adaderana.lk/rss.php",
    "Daily Mirror": "https://www.dailymirror.lk/RSS_Feeds/breaking-news",
    "News First": "https://www.newsfirst.lk/feed",
    "The Island": "https://island.lk/feed/",
    "Newswire": "https://www.newswire.lk/feed/",
    "EconomyNext": "https://economynext.com/feed",
    "Ceylon Today": "https://ceylontoday.lk/feed/",
    "Daily FT": "https://www.ft.lk/rss/all",
}


# --------------------------------------------------------------------------
# Credentials
# --------------------------------------------------------------------------
def load_env(path=None) -> Dict[str, str]:
    """Read travellens/.env. Values are returned but never logged."""
    path = path or ENV_PATH
    if not path.exists() and ENV_FALLBACK.exists():
        path = ENV_FALLBACK
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def key_status(env: Dict[str, str]) -> Dict[str, bool]:
    return {k: bool(env.get(k)) for k in
            ("GOOGLE_MAPS_API_KEY", "YOUTUBE_API_KEY", "APIFY_API_TOKEN")}


# --------------------------------------------------------------------------
# HTTP with manners
# --------------------------------------------------------------------------
class Fetcher:
    def __init__(self, max_requests: int = MAX_REQUESTS_PER_RUN):
        self.max = max_requests
        self.n = 0
        self._last = {}

    def get(self, url: str, params: Optional[Dict] = None, timeout: int = 20):
        import requests
        if self.n >= self.max:
            raise RuntimeError("request ceiling reached ({})".format(self.max))
        host = re.sub(r"^https?://([^/]+).*", r"\1", url)
        wait = REQUEST_PAUSE - (time.time() - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self.n += 1
        self._last[host] = time.time()
        return requests.get(url, params=params, timeout=timeout,
                            headers={"User-Agent": USER_AGENT})


# --------------------------------------------------------------------------
# Reddit -- public JSON, no key
# --------------------------------------------------------------------------
def collect_reddit(fetcher: Fetcher, queries: List[str], limit: int = 25,
                   verbose: bool = True) -> List[Dict]:
    out, seen = [], set()
    for q in queries:
        url = "https://www.reddit.com/r/srilanka/search.json"
        try:
            r = fetcher.get(url, params={"q": q, "restrict_sr": 1, "limit": limit,
                                         "sort": "relevance", "t": "all"})
            if r.status_code != 200:
                if verbose:
                    print("    reddit '{}' -> HTTP {}".format(q[:34], r.status_code))
                continue
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                pid = d.get("id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                out.append({
                    "title": d.get("title", ""),
                    "permalink": d.get("permalink", ""),
                    "subreddit": d.get("subreddit", ""),
                    "created": datetime.utcfromtimestamp(
                        d.get("created_utc", 0)).date().isoformat()
                    if d.get("created_utc") else "",
                    "selftext": (d.get("selftext") or "")[:600],
                    "score": d.get("score", 0),
                })
            if verbose:
                print("    reddit '{}' -> {} cumulative".format(q[:34], len(out)))
        except Exception as exc:
            if verbose:
                print("    reddit '{}' failed: {}".format(q[:34], type(exc).__name__))
    return out


# --------------------------------------------------------------------------
# News -- RSS from whitelisted outlets, no key
# --------------------------------------------------------------------------
_ITEM = re.compile(r"<item>(.*?)</item>", re.S | re.I)
_TAG = {t: re.compile(r"<{0}[^>]*>(.*?)</{0}>".format(t), re.S | re.I)
        for t in ("title", "link", "description", "pubDate")}
_CDATA = re.compile(r"<!\[CDATA\[(.*?)\]\]>", re.S)
_HTML = re.compile(r"<[^>]+>")


def _clean_rss(v: str) -> str:
    v = _CDATA.sub(r"\1", v or "")
    return _HTML.sub("", v).strip()


def collect_news(fetcher: Fetcher, verbose: bool = True) -> List[Dict]:
    out = []
    for outlet, feed in NEWS_RSS.items():
        try:
            r = fetcher.get(feed)
            if r.status_code != 200:
                if verbose:
                    print("    {:<14} HTTP {}".format(outlet, r.status_code))
                continue
            items = _ITEM.findall(r.text)
            for raw in items:
                get = lambda t: _clean_rss(
                    (_TAG[t].search(raw).group(1) if _TAG[t].search(raw) else ""))
                link = get("link")
                if not link:
                    continue
                out.append({"title": get("title"), "url": link,
                            "summary": get("description")[:500],
                            "published": get("pubDate")[:16]})
            if verbose:
                print("    {:<14} {} items".format(outlet, len(items)))
        except Exception as exc:
            if verbose:
                print("    {:<14} failed: {}".format(outlet, type(exc).__name__))
    return out


# --------------------------------------------------------------------------
# YouTube Data API
# --------------------------------------------------------------------------
def collect_youtube(fetcher: Fetcher, key: str, queries: List[str],
                    per_query: int = 10, verbose: bool = True) -> List[Dict]:
    out, seen = [], set()
    for q in queries:
        try:
            r = fetcher.get("https://www.googleapis.com/youtube/v3/search",
                            params={"part": "snippet", "q": q, "type": "video",
                                    "maxResults": per_query, "key": key,
                                    "relevanceLanguage": "en"})
            if r.status_code != 200:
                if verbose:
                    print("    youtube '{}' -> HTTP {}".format(q[:30], r.status_code))
                continue
            for it in r.json().get("items", []):
                vid = it.get("id", {}).get("videoId")
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                sn = it.get("snippet", {})
                out.append({
                    "title": sn.get("title", ""),
                    "url": "https://www.youtube.com/watch?v=" + vid,
                    "channel": sn.get("channelTitle", ""),
                    "publishedAt": (sn.get("publishedAt") or "")[:10],
                    "description": sn.get("description", ""),
                })
            if verbose:
                print("    youtube '{}' -> {} cumulative".format(q[:30], len(out)))
        except Exception as exc:
            if verbose:
                print("    youtube '{}' failed: {}".format(q[:30], type(exc).__name__))
    return out


# --------------------------------------------------------------------------
# Google Places API -- reviews WITH a source URL
# --------------------------------------------------------------------------
def collect_places(fetcher: Fetcher, key: str, destinations: List[Dict],
                   verbose: bool = True) -> List[Dict]:
    """Text Search then Place Details. Two billed calls per destination."""
    out = []
    for d in destinations:
        q = "{} {} Sri Lanka".format(d["destination"], d.get("district", "")).strip()
        try:
            r = fetcher.get("https://maps.googleapis.com/maps/api/place/textsearch/json",
                            params={"query": q, "key": key})
            payload = r.json()
            # Surface the API's own status. Reporting "no place found" when the
            # real answer is REQUEST_DENIED sends the reader hunting for a data
            # problem that is actually a credentials problem.
            status = payload.get("status", "")
            if status not in ("OK", "ZERO_RESULTS"):
                raise RuntimeError("Places API {}: {}".format(
                    status, payload.get("error_message", "no detail")))
            res = payload.get("results", [])
            if not res:
                if verbose:
                    print("    {:<34} no place found".format(d["destination"][:32]))
                continue
            pid = res[0].get("place_id")
            det = fetcher.get("https://maps.googleapis.com/maps/api/place/details/json",
                              params={"place_id": pid, "key": key,
                                      "fields": "name,url,reviews,rating"})
            data = det.json().get("result", {})
            revs = data.get("reviews", []) or []
            place_url = data.get("url", "")
            for rev in revs:
                out.append({
                    "destination": d["destination"],
                    "district": d.get("district", ""),
                    "text": rev.get("text", ""),
                    "timespan": rev.get("relative_time_description", ""),
                    "rating": rev.get("rating"),
                    "source": "google_places_api",
                    # Place URL, not a review permalink -- the API does not
                    # expose one. Still far better than the legacy corpora,
                    # which carry no link at all.
                    "source_url": rev.get("author_url") or place_url,
                })
            if verbose:
                print("    {:<34} {} reviews".format(d["destination"][:32], len(revs)))
        except Exception as exc:
            if verbose:
                print("    {:<34} failed: {}".format(d["destination"][:32],
                                                     type(exc).__name__))
    return out


def write(items: List[Dict], name: str, verbose: bool = True) -> str:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "{}_{}.json".format(name, date.today().isoformat())
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=1, ensure_ascii=False)
    if verbose:
        print("  wrote {} items -> {}".format(len(items), path))
    return str(path)
