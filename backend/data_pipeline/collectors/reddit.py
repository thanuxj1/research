"""
Reddit Collector — Tourism Safety & Scam Analytics Engine
IT22629180

Uses Reddit's public JSON API — NO API KEY REQUIRED.
Covers 25+ subreddits, 15 keyword groups, 2-year lookback.
Expected yield: 300–600+ unique posts per run.
"""

import requests
from typing import List, Dict
import time
from datetime import datetime, timezone


def _utc_to_dt(utc_ts):
    """Convert a Unix timestamp (Reddit created_utc) to a UTC-aware datetime."""
    if utc_ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(utc_ts), tz=timezone.utc)
    except Exception:
        return None


class RedditCollector:

    BASE_URL = "https://www.reddit.com"

    # --- Subreddits ---
    # Group A: Sri Lanka specific (all queries run unmodified)
    SRILANKA_SUBS = [
        "srilanka",
        "SriLankaTravel",
        "colombo",
        "kandy",
        "galle",
        "ella",
    ]

    # Group B: General travel (queries prefixed with "Sri Lanka")
    TRAVEL_SUBS = [
        "travel",
        "solotravel",
        "backpacking",
        "shoestring",
        "TravelHacks",
        "lonelyplanet",
        "digitalnomad",
        "AskTravel",
        "onebag",
        "Ultralight",
        "femaletravel",
        "solotravel",
        "budget_travel",
        "TravelNoPics",
        "travelnews",
        "travelpartners",
        "Traveladvice",
        "TrueOffMyChest",   # tourists share scam experiences
        "Scams",            # cross-platform scam reports
        "Fraud",
        "personalfinance",  # tourists reporting lost money / scams
        "LegalAdvice",      # tourists seeking advice after incidents
    ]

    # --- Keyword groups (short to stay within Reddit search limits) ---
    QUERIES = [
        "scam scammed fraud trick tricking",
        "gem shop fake gemstone sapphire jewelry",
        "tuk tuk overcharged ripped off meter scam",
        "fake guide commission shop temple scam",
        "tourist trap Sri Lanka avoid",
        "tour operator scam agency fake",
        "money exchange scam currency black market",
        "accommodation hotel scam booking bait switch",
        "beach boy harassment sexual catcall",
        "taxi overcharge airport highway",
        "temple dress code scam shoe flower",
        "astrologer fortune teller scam spiritual",
        "elephant ride ethical scam animal abuse",
        "train ticket tout scam platform",
        "street food poisoning sick stomach bug",
        "assault attacked physically hit pushed",
        "threatened intimidated scary aggressive",
        "overprice overpriced double price foreigner tax",
        "Ella scam Nine Arch Rock guide",
        "Sigiriya scam Lion Rock guide",
        "Mirissa scam whale watching harassment",
        "Galle Fort scam restaurant overcharge",
        "Kandy scam temple flower guide",
        "Pettah scam market pickpocket",
        "Bentota scam beach boy water sports",
        "Arugam Bay scam drugs theft",
        "Nuwara Eliya scam tea factory",
        "Jaffna tourist safety safety",
        "Trincomalee tourist safety scam",
        # Safety & danger
        "unsafe dangerous warning avoid alert",
        "harassment threatened attacked assault",
        "theft pickpocket robbery stolen bag",
        "solo female unsafe harassment follow",
        "drug drugged spiked drink needle",
        "ATM skimming card cloned pin",
        "flood landslide natural disaster weather",
        "road accident motorbike rent license",
        "wildlife dangerous animal monkey elephant",
        # General negative travel
        "disappointed worst experience nightmare",
        "avoid Sri Lanka never again horrible",
        "travel advisory Sri Lanka warning",
        "police corruption bribe Sri Lanka extortion",
        "visa overstay fine Sri Lanka agent",
        "tourist police sri lanka help",
        "complain to police sri lanka safety report",
    ]

    # Broader context queries just for r/srilanka + r/SriLankaTravel
    DEEP_QUERIES = [
        "scam",
        "fraud",
        "tourist",
        "safety",
        "robbery",
        "overcharge",
        "warning",
        "fake",
        "dangerous",
        "harassment",
        "theft",
        "cheat",
        "rip off",
        "corrupt",
        "problem",
    ]

    def __init__(self):
        self.headers = {
            "User-Agent": "python:lk.safetravel.research:v3.0 (IT22629180 - Sri Lanka tourism safety research)"
        }

    def _search(self, subreddit: str, query: str, limit: int = 25, time_filter: str = "year") -> List[Dict]:
        """Search a subreddit for a query. Returns normalized post dicts."""
        url = f"{self.BASE_URL}/r/{subreddit}/search.json"
        params = {
            "q":           query,
            "sort":        "relevance",
            "limit":       min(limit, 100),
            "restrict_sr": "true",
            "t":           time_filter,  # "year", "all"
        }
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=self.headers, params=params, timeout=20)
                if resp.status_code == 429:
                    wait = 15 + attempt * 10
                    print(f"  [Reddit] Rate-limited on r/{subreddit}. Waiting {wait}s...")
                    time.sleep(wait)
                    continue
                if resp.status_code != 200:
                    return []

                posts = []
                for child in resp.json().get("data", {}).get("children", []):
                    d = child.get("data", {})
                    content = d.get("selftext", "").strip()
                    title   = d.get("title", "").strip()

                    # Skip deleted / removed
                    if content in ("[deleted]", "[removed]", ""):
                        content = ""
                    combined = f"{title}\n{content}".strip()
                    if not combined or combined == title and len(title) < 15:
                        continue

                    # Skip low-relevance posts (score < 2 and no comments)
                    score = d.get("score", 0)
                    num_comments = d.get("num_comments", 0)
                    if score < 1 and num_comments == 0:
                        continue

                    posts.append({
                        "source":      "reddit",
                        "id":          d.get("id", ""),
                        "title":       title,
                        "content":     combined,
                        "created_utc": d.get("created_utc"),
                        "published_at": _utc_to_dt(d.get("created_utc")),  # ISO datetime for published_at
                        "url":         f"{self.BASE_URL}{d.get('permalink', '')}",
                        "subreddit":   subreddit,
                        "score":       score,
                        "helpful_votes": score,  # Reddit score = upvotes proxy for credibility
                        "num_comments": num_comments,
                    })
                return posts
            except Exception as e:
                print(f"  [Reddit] Error r/{subreddit} '{query}' (attempt {attempt+1}): {e}")
                time.sleep(3)
        return []

    def _fetch_comments(self, permalink: str, max_comments: int = 10) -> str:
        """Fetch top-level comments from a post to enrich content."""
        url = f"{self.BASE_URL}{permalink}.json"
        try:
            resp = requests.get(url, headers=self.headers, timeout=20)
            if resp.status_code != 200:
                return ""
            data = resp.json()
            if len(data) < 2:
                return ""
            comments = []
            for child in data[1].get("data", {}).get("children", [])[:max_comments]:
                body = child.get("data", {}).get("body", "").strip()
                if body and body not in ("[deleted]", "[removed]") and len(body) > 20:
                    comments.append(body)
            return " | ".join(comments)
        except Exception:
            return ""

    def fetch_recent_posts(self, subreddit_name: str = "srilanka", limit: int = 50) -> List[Dict]:
        """Backward-compatible single-subreddit method."""
        posts, seen = [], set()
        for q in self.QUERIES:
            for p in self._search(subreddit_name, q, limit=max(5, limit // len(self.QUERIES) + 1)):
                if p["id"] not in seen:
                    seen.add(p["id"])
                    posts.append(p)
            time.sleep(0.8)
        return posts

    def collect_all(self) -> List[Dict]:
        """
        Full collection across all subreddits and keyword groups.
        Expected yield: 300-600+ posts.
        """
        all_posts, seen_ids = [], set()

        # --- Deep-search Sri Lanka specific subs ---
        print(f"  [Reddit] Deep-searching Sri Lanka subreddits...")
        for sub in self.SRILANKA_SUBS:
            # Both recent (year) and all-time for these
            for time_filter in ["year", "all"]:
                for q in self.QUERIES + self.DEEP_QUERIES:
                    results = self._search(sub, q, limit=100, time_filter=time_filter)
                    for p in results:
                        if p["id"] not in seen_ids:
                            seen_ids.add(p["id"])
                            all_posts.append(p)
                    time.sleep(0.5)
            count = len([p for p in all_posts if p["subreddit"] == sub])
            print(f"    r/{sub}: {count} posts collected")

        # --- Broad search on general travel subs with Sri Lanka prefix ---
        print(f"  [Reddit] Searching general travel subreddits...")
        for sub in self.TRAVEL_SUBS:
            for q in self.QUERIES:
                query = f"Sri Lanka {q}"
                results = self._search(sub, query, limit=50)
                for p in results:
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_posts.append(p)
                time.sleep(0.6)
            count = len([p for p in all_posts if p["subreddit"] == sub])
            print(f"  [Reddit] r/{sub}: {len([p for p in all_posts if p['subreddit']==sub])} posts so far")
        print(f"  [Reddit] Total: {len(all_posts)} unique posts")
        return all_posts

    def fast_collect_all(self) -> List[Dict]:
        """
        Fast mode — 3 core subs + key travel subs, year timeframe only, top 15 queries.
        Completes in ~2-3 minutes. Use for regular scheduled runs.
        """
        all_posts, seen_ids = [], set()

        FAST_SUBS_DIRECT = ["srilanka", "SriLankaTravel"]
        FAST_SUBS_PREFIXED = ["travel", "solotravel", "backpacking", "Scams", "femaletravel", "AskTravel"]
        FAST_QUERIES = self.QUERIES[:15]  # Top 15 most relevant keyword groups

        print(f"  [Reddit Fast] Sri Lanka subreddits...")
        for sub in FAST_SUBS_DIRECT:
            for q in FAST_QUERIES + self.DEEP_QUERIES[:8]:
                for p in self._search(sub, q, limit=25, time_filter="year"):
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_posts.append(p)
                time.sleep(0.5)
            print(f"    r/{sub}: {len([p for p in all_posts if p['subreddit']==sub])} posts")

        print(f"  [Reddit Fast] General travel subreddits...")
        for sub in FAST_SUBS_PREFIXED:
            for q in FAST_QUERIES[:10]:
                for p in self._search(sub, f"Sri Lanka {q}", limit=15, time_filter="year"):
                    if p["id"] not in seen_ids:
                        seen_ids.add(p["id"])
                        all_posts.append(p)
                time.sleep(0.6)
            print(f"    r/{sub}: {len([p for p in all_posts if p['subreddit']==sub])} posts")

        print(f"  [Reddit Fast] Total: {len(all_posts)} posts")
        return all_posts
