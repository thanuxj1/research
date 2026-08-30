"""
LostinSriLanka -- Reddit collection via public RSS feeds.

Why RSS
-------
Three routes to Reddit were tested:

  /r/<sub>/search.json    403  -- unauthenticated JSON access closed in 2023
  /r/<sub>/search.rss     429  -- search over RSS is rate-limited to nothing
  /r/<sub>/.rss           200  -- the plain subreddit feed still serves

So the plain feed is the only route that works without credentials, and it is a
published feed rather than a scrape: Reddit serves it as Atom, at a documented
URL, for exactly this kind of consumption.

What that costs
---------------
No search. The feed returns roughly the 25 most recent posts in a subreddit and
nothing older, so this cannot go looking for "Sembuwatta Lake" -- it can only
read what is currently on the front page of each subreddit and keep whatever
happens to mention a destination.

Yield is therefore low and lumpy, and it will differ every time it runs. That is
a real limitation, not a bug, and it is the reason the OAuth path in
collect_reddit_oauth.py is still worth setting up: an authenticated app can
search the full history and would turn this from opportunistic into systematic.

Politeness
----------
Reddit returned 429 quickly under one-per-second, so this waits several seconds
between feeds and sends a descriptive User-Agent. If a feed 429s it is skipped
rather than retried in a loop.

Run with:  python scripts/27_collect_reddit_rss.py
"""
import re
import time
from typing import Dict, List, Optional

# Travel subreddits where Sri Lankan destinations plausibly come up. Ordered by
# how specific they are: r/srilanka first, general travel subs after.
SUBREDDITS = [
    "srilanka",
    "SriLankaTravel",
    "travel",
    "solotravel",
    "backpacking",
    "IndiaTravel",
    "TravelNoPics",
]

FEED = "https://www.reddit.com/r/{}/.rss"
PAUSE_SECONDS = 5.0          # Reddit 429s aggressively; be generous

_ENTRY = re.compile(r"<entry>(.*?)</entry>", re.S | re.I)
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
_LINK = re.compile(r'<link[^>]*href="([^"]+)"', re.I)
_UPDATED = re.compile(r"<updated>(.*?)</updated>", re.S | re.I)
_CONTENT = re.compile(r"<content[^>]*>(.*?)</content>", re.S | re.I)
_AUTHOR = re.compile(r"<author>.*?<name>(.*?)</name>.*?</author>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"',
             "&#39;": "'", "&apos;": "'", "&nbsp;": " "}


def _clean(v: str) -> str:
    v = _TAGS.sub(" ", v or "")
    for ent, ch in _ENTITIES.items():
        v = v.replace(ent, ch)
    return re.sub(r"\s+", " ", v).strip()


def collect(subreddits: Optional[List[str]] = None,
            verbose: bool = True) -> List[Dict]:
    import requests
    from .collect import USER_AGENT

    subs = subreddits or SUBREDDITS
    out, seen = [], set()
    for i, sub in enumerate(subs):
        if i:
            time.sleep(PAUSE_SECONDS)
        try:
            r = requests.get(FEED.format(sub), timeout=20,
                             headers={"User-Agent": USER_AGENT})
            if r.status_code != 200:
                if verbose:
                    print("    r/{:<16} HTTP {}".format(sub, r.status_code))
                continue
            entries = _ENTRY.findall(r.text)
            added = 0
            for raw in entries:
                link = _LINK.search(raw)
                if not link:
                    continue
                url = link.group(1)
                if url in seen:
                    continue
                seen.add(url)
                title = _clean(_TITLE.search(raw).group(1)) if _TITLE.search(raw) else ""
                content = _clean(_CONTENT.search(raw).group(1)) if _CONTENT.search(raw) else ""
                author = _clean(_AUTHOR.search(raw).group(1)) if _AUTHOR.search(raw) else ""
                updated = (_UPDATED.search(raw).group(1)[:10]
                           if _UPDATED.search(raw) else "")
                out.append({
                    "title": title,
                    "url": url,
                    "subreddit": sub,
                    "created": updated,
                    "selftext": content[:600],
                    "author": author,
                })
                added += 1
            if verbose:
                print("    r/{:<16} {} entries, {} new".format(sub, len(entries), added))
        except Exception as exc:
            if verbose:
                print("    r/{:<16} failed: {}".format(sub, type(exc).__name__))
    return out
