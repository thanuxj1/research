"""
LostinSriLanka -- Reddit collection via the official API.

Why not scrape
--------------
Reddit's public JSON endpoint began returning 403 to unauthenticated clients in
2023. Scraping the HTML instead would work technically and would breach their
terms, so this project does not do it. Reddit's API is free for research use at
this volume; it simply requires registering an application, which takes about
two minutes and is the sanctioned route.

Setup (once)
------------
1. Sign in at https://www.reddit.com/prefs/apps
2. "create another app..." -> type: **script**
3. name: anything;  redirect uri: http://localhost:8080
4. Copy the two values into travellens/.env:

       REDDIT_CLIENT_ID=<the string under the app name>
       REDDIT_CLIENT_SECRET=<the "secret" field>

Nothing else is needed -- a script app authenticates as itself, so no Reddit
account password is involved and no user data is accessed.

Rate limits
-----------
60 requests per minute for authenticated clients. The shared Fetcher already
pauses one second between requests to a host, which stays well inside that.

Run with:  python scripts/26_collect_reddit.py --limit 20
"""
from typing import Dict, List, Optional

from .collect import USER_AGENT, Fetcher

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"

SUBREDDITS = ["srilanka", "travel", "solotravel", "backpacking", "IndiaTravel"]

# Queries aimed at the aspects this project measures, so the storyboard items
# sit beside a relevant complaint rather than being generic travel chat.
DEFAULT_QUERIES = [
    "Sri Lanka waterfall road",
    "Sri Lanka entrance fee foreigners",
    "Sri Lanka swimming dangerous",
    "Sri Lanka national park worth it",
    "Sri Lanka tuk tuk overcharge",
]


def get_token(client_id: str, client_secret: str,
              verbose: bool = True) -> Optional[str]:
    """Application-only OAuth. Returns None if the credentials are absent."""
    import requests
    if not client_id or not client_secret:
        return None
    try:
        r = requests.post(
            TOKEN_URL,
            auth=(client_id, client_secret),
            data={"grant_type": "client_credentials"},
            headers={"User-Agent": USER_AGENT},
            timeout=20)
        if r.status_code != 200:
            if verbose:
                print("    token request -> HTTP {}".format(r.status_code))
            return None
        return r.json().get("access_token")
    except Exception as exc:
        if verbose:
            print("    token request failed: {}".format(type(exc).__name__))
        return None


def collect(fetcher: Fetcher, token: str, queries: Optional[List[str]] = None,
            subreddits: Optional[List[str]] = None, limit: int = 25,
            verbose: bool = True) -> List[Dict]:
    import requests
    queries = queries or DEFAULT_QUERIES
    subreddits = subreddits or SUBREDDITS
    headers = {"Authorization": "bearer " + token, "User-Agent": USER_AGENT}
    out, seen = [], set()

    for sub in subreddits:
        for q in queries:
            if fetcher.n >= fetcher.max:
                if verbose:
                    print("    request ceiling reached")
                return out
            fetcher.n += 1
            try:
                r = requests.get(
                    "{}/r/{}/search".format(API_BASE, sub),
                    params={"q": q, "restrict_sr": "true", "limit": limit,
                            "sort": "relevance", "t": "all", "raw_json": 1},
                    headers=headers, timeout=20)
                if r.status_code != 200:
                    if verbose:
                        print("    r/{:<12} HTTP {}".format(sub, r.status_code))
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
                        "created": d.get("created_utc"),
                        "selftext": (d.get("selftext") or "")[:600],
                        "score": d.get("score", 0),
                    })
            except Exception as exc:
                if verbose:
                    print("    r/{:<12} failed: {}".format(sub, type(exc).__name__))
        if verbose:
            print("    r/{:<14} cumulative {}".format(sub, len(out)))
    return out
