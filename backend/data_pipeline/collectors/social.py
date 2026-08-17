"""
Social & News Collector — Tourism Safety & Scam Analytics Engine
IT22629180

Sources covered (no API keys required):
  1. Nitter  — public Twitter/X mirror, scrapes tweets about Sri Lanka scams
  2. Google News RSS  — aggregates news about Sri Lanka tourist incidents
  3. TripAdvisor Forum — full thread scraping (listing + top post content)
  4. Quora — public Q&A posts about Sri Lanka safety
  5. WikiVoyage — curated safety warnings (authoritative source)
  6. Forum.HolidayTruths — UK-based travel forum with Sri Lanka scam threads
  7. ThornTree (Lonely Planet forums) — well-known travel community

All fetched via plain HTTP + BeautifulSoup. No JavaScript required.
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict
import time
import re
from urllib.parse import urlencode, quote_plus
from datetime import timezone
try:
    from dateutil import parser as dateutil_parser
except ImportError:
    dateutil_parser = None  # graceful degradation


def _parse_rss_date(item) -> None:
    """Extract pubDate from an RSS <item> and return a UTC-aware datetime, or None."""
    if not dateutil_parser:
        return None
    pub = item.find("pubDate")
    if pub and pub.get_text(strip=True):
        try:
            return dateutil_parser.parse(pub.get_text(strip=True)).replace(tzinfo=timezone.utc)
        except Exception:
            pass
    return None


class SocialCollector:

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    RSS_HEADERS = {
        "User-Agent": "Mozilla/5.0 (compatible; SafeTravelLK-Research-Bot/1.0)",
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }



    # ------------------------------------------------------------------ #
    #  2. Google News RSS                                                  #
    # ------------------------------------------------------------------ #
    NEWS_QUERIES = [
        "Sri Lanka tourist scam victims",
        "Sri Lanka traveller fraud complaint",
        "Sri Lanka travel safety incident warning",
        "Sri Lanka tourist robbery arrest",
        "Sri Lanka tourist injury accident report",
        "Sri Lanka gem shop scam tourist complaint",
        "Sri Lanka tourist harassment assault",
        "Sri Lanka travel advisory negative danger",
        "Colombo tourist scam report assault",
        "Kandy tourist fraud arrest trick",
        "Sri Lanka Tourist Police scam arrest",
        "Sri Lanka police arrest tourist scammer",
        "Sri Lanka tourist mugged robbed assault",
        "Sri Lanka tourist pickpocketed theft",
        "Sri Lanka tourist overcharged ripped off overprice",
        "Sri Lanka dangerous area tourist warning assault",
    ]

    def scrape_google_news_rss(self) -> List[Dict]:
        """
        Scrapes Google News RSS feed for Sri Lanka tourism safety stories.
        Each query returns up to 20 recent news articles.
        """
        # Negative signals to ensure the article is about negative experiences
        negative_signals = [
            "scam", "fraud", "robbery", "theft", "harassment", "assault",
            "injury", "accident", "warning", "danger", "unsafe", "avoid",
            "ripped off", "overcharged", "fake", "counterfeit", "arrest",
            "complaint", "victim", "mugged", "pickpocket", "threat",
        ]
        
        results = []
        seen_urls = set()

        for query in self.NEWS_QUERIES:
            rss_url = (
                f"https://news.google.com/rss/search?"
                f"q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            )
            try:
                resp = requests.get(rss_url, headers=self.RSS_HEADERS, timeout=15)
                if resp.status_code != 200:
                    time.sleep(1)
                    continue

                soup = BeautifulSoup(resp.text, "lxml-xml")
                items = soup.find_all("item")

                for item in items[:20]:
                    title = item.find("title")
                    link = item.find("link")
                    desc = item.find("description")

                    title_text = title.get_text(strip=True) if title else ""
                    link_text = link.get_text(strip=True) if link else (
                        link.next_sibling.strip() if link else ""
                    )
                    desc_text = desc.get_text(strip=True) if desc else ""

                    # Clean HTML from description
                    desc_text = re.sub(r"<[^>]+>", " ", desc_text).strip()

                    if not title_text or link_text in seen_urls:
                        continue
                    seen_urls.add(link_text)

                    content = f"{title_text}. {desc_text}".strip()
                    if len(content) < 20:
                        continue

                    # Pre-filter: ensure content has negative signals
                    content_lower = content.lower()
                    if not any(sig in content_lower for sig in negative_signals):
                        continue

                    results.append({
                        "source":       "google_news",
                        "title":        title_text,
                        "content":      content,
                        "url":          link_text,
                        "published_at": _parse_rss_date(item),
                    })

                time.sleep(0.8)

            except Exception as e:
                print(f"  [Google News RSS] Error for '{query}': {e}")
                time.sleep(2)

        print(f"  [Google News RSS] Collected {len(results)} news articles")
        return results



    # ------------------------------------------------------------------ #
    #  6. Sri Lanka News Sites (Expanded — 10+ local outlets)             #
    # ------------------------------------------------------------------ #
    def scrape_srilanka_newswire(self) -> List[Dict]:
        """
        Scrapes all major Sri Lankan news sites for tourist safety incidents,
        scams, crimes against tourists, and travel warnings.
        """
        results = []
        SEARCH_TERMS = ["tourist+scam", "tourist+fraud", "tourist+robbed", "tourist+safety", "tourist+arrested"]
        sources = [
            {"name": "colombo_gazette",  "base": "https://colombogazette.com/?s=",          "card": "article,.post",         "title": "h2 a,h3 a",            "body": ".entry-summary,p"},
            {"name": "adaderana",        "base": "https://www.adaderana.lk/search.php?mode=0&q=", "card": ".news-item,.story",   "title": "h4 a,h3 a,a",          "body": "p"},
            {"name": "newsfirst",        "base": "https://www.newsfirst.lk/?s=",            "card": "article,.post",         "title": "h2 a,h3 a",            "body": ".entry-summary,p"},
            {"name": "daily_mirror_lk",  "base": "https://www.dailymirror.lk/search?q=",   "card": "article,.news-post",    "title": "h2 a,h3 a,.title a",   "body": "p,.summary"},
            {"name": "ceylon_today",     "base": "https://ceylontoday.lk/?s=",              "card": "article,.post",         "title": "h2 a,h3 a",            "body": "p,.entry-summary"},
            {"name": "themorning_lk",    "base": "https://www.themorning.lk/?s=",           "card": "article,.post",         "title": "h2 a,h3 a",            "body": "p,.entry-summary"},
            {"name": "hirunews_lk",      "base": "https://www.hirunews.lk/search.php?query=", "card": ".news-item,article",  "title": "h2 a,h3 a,a.title",    "body": "p"},
            {"name": "sundaytimes_lk",   "base": "https://www.sundaytimes.lk/search/?q=",   "card": "article,.news",         "title": "h2 a,h3 a",            "body": "p,.content"},
            {"name": "theisland_lk",     "base": "https://island.lk/?s=",                   "card": "article,.post",         "title": "h2 a,h3 a",            "body": "p,.entry-summary"},
            {"name": "economynext_lk",   "base": "https://economynext.com/?s=",             "card": "article,.post",         "title": "h2 a,h3 a",            "body": "p,.entry-summary"},
            {"name": "newswire_lk",      "base": "https://www.newswire.lk/?s=",             "card": "article,.post",         "title": "h2 a,h3 a",            "body": "p,.entry-summary"},
        ]

        for src in sources:
            for term in SEARCH_TERMS[:3]:  # Limit to 3 terms per source to avoid overloading
                url = src["base"] + term
                try:
                    resp = requests.get(url, headers=self.HEADERS, timeout=15)
                    if resp.status_code != 200:
                        continue
                    soup = BeautifulSoup(resp.text, "html.parser")
                    cards = soup.select(src["card"])
                    for card in cards[:8]:
                        title_el = card.select_one(src["title"])
                        content_el = card.select_one(src["body"])
                        if not title_el:
                            continue
                        title_text = title_el.get_text(strip=True)
                        href = title_el.get("href", "")
                        content_text = content_el.get_text(strip=True) if content_el else title_text
                        if len(content_text) < 20:
                            content_text = title_text
                        results.append({
                            "source": src["name"],
                            "title": title_text,
                            "content": content_text,
                            "url": href,
                        })
                    time.sleep(0.8)
                except Exception as e:
                    print(f"  [News:{src['name']}] Error: {e}")

        print(f"  [Sri Lanka News Sites] Collected {len(results)} articles")
        return results


    # ------------------------------------------------------------------ #
    #  Main entry point                                                   #
    # ------------------------------------------------------------------ #
    def collect_all(self) -> List[Dict]:
        """Run all news collectors and return combined results."""
        print("\n--- News Collection ---")
        all_results: List[Dict] = []

        print("  [1/2] Google News RSS...")
        all_results.extend(self.scrape_google_news_rss())

        print("  [2/2] Sri Lanka News Sites (10+ outlets)...")
        all_results.extend(self.scrape_srilanka_newswire())

        print(f"\n  News Total: {len(all_results)} items collected")
        return all_results

    def fast_collect_all(self) -> List[Dict]:
        """
        Fast mode for high-frequency updates (every cycle).
        Focuses on Google News RSS only.
        """
        all_results = []
        print("  [News Fast] Fetching Google News RSS...")
        
        # Google News RSS is extremely fast and updates frequently
        all_results.extend(self.scrape_google_news_rss())
        
        return all_results
