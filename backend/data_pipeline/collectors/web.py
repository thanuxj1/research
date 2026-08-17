import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser


def _parse_publish_date(soup: "BeautifulSoup") -> Optional[datetime]:
    """
    Extracts the article publish date from common HTML meta patterns.
    Returns a UTC-aware datetime or None if no date found.

    Checked patterns (in priority order):
      1. <meta property="article:published_time">
      2. <meta name="datePublished">
      3. <time datetime="...">  (HTML5 element)
      4. <meta property="og:article:published_time">
      5. JSON-LD @type Article datePublished
    """
    # Meta property patterns
    for attr, name in [
        ("property", "article:published_time"),
        ("name",     "datePublished"),
        ("property", "og:article:published_time"),
        ("name",     "article.published"),
        ("itemprop", "datePublished"),
    ]:
        tag = soup.find("meta", {attr: name})
        if tag and tag.get("content"):
            try:
                return dateutil_parser.parse(tag["content"]).replace(tzinfo=timezone.utc)
            except Exception:
                pass

    # <time> element
    time_el = soup.find("time", {"datetime": True})
    if time_el:
        try:
            return dateutil_parser.parse(time_el["datetime"]).replace(tzinfo=timezone.utc)
        except Exception:
            pass

    return None

class WebCollector:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })


    # ------------------------------------------------------------------ #
    #  Daily Mirror Sri Lanka                                             #
    # ------------------------------------------------------------------ #
    def scrape_daily_mirror(self, keyword: str = "scam") -> List[Dict]:
        """
        Scrapes Daily Mirror Sri Lanka category/search listings for articles
        containing safety/scam keywords.

        Confirmed selectors (2026-05):
          - Article cards   : .cat-list-row
          - Title inside    : h3 > a  (or just a within the card)
          - Content wrapper : .inner-content  (on the individual article page)
        """
        url = f"https://www.dailymirror.lk/search-news/{keyword.replace(' ', '+')}"
        results = []

        try:
            response = self.session.get(url, timeout=15)
            if response.status_code != 200:
                print(f"Daily Mirror returned status {response.status_code} for '{keyword}'")
                return results

            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.select('.cat-list-row')

            if not cards:
                print(f"No article cards found on Daily Mirror for '{keyword}'")
                return results

            for card in cards[:8]:  # limit per query
                title_tag = card.select_one('h3 a') or card.select_one('a')
                if not title_tag:
                    continue

                title = title_tag.get_text(strip=True)
                link  = title_tag.get('href', '')
                if link and not link.startswith('http'):
                    link = 'https://www.dailymirror.lk' + link

                content, pub_date = self._fetch_article(link) if link else ('', None)

                results.append({
                    "source":       "daily_mirror",
                    "title":        title,
                    "content":      content or title,   # fallback to title
                    "url":          link,
                    "published_at": pub_date,
                })
                time.sleep(0.5)  # be polite

        except Exception as e:
            print(f"Error scraping Daily Mirror for '{keyword}': {e}")

        return results

    def _fetch_article(self, url: str):
        """Fetches the main text body AND publish date from a Daily Mirror article.
        Returns (content_str, published_at_dt)."""
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                body = soup.select_one('.inner-content')
                text = body.get_text(separator=' ', strip=True) if body else ''
                pub_date = _parse_publish_date(soup)
                return text, pub_date
        except Exception as e:
            print(f"Error fetching article content from {url}: {e}")
        return '', None



    # ------------------------------------------------------------------ #
    #  Ada Derana — Sri Lanka's leading English news site                 #
    # ------------------------------------------------------------------ #
    def scrape_adaderana(self, keyword: str = "tourist scam") -> List[Dict]:
        url = f"https://www.adaderana.lk/search.php?mode=0&q={keyword.replace(' ', '+')}"
        results = []
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                print(f"  Ada Derana returned {resp.status_code} for '{keyword}'")
                return results
            soup = BeautifulSoup(resp.text, "html.parser")
            stories = soup.select(".story, .news-item, article")
            for story in stories[:10]:
                title_el = story.select_one("h4 a, h3 a, h2 a, a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                if href and not href.startswith("http"):
                    href = "https://www.adaderana.lk" + href
                snippet_el = story.select_one("p, .story-text")
                content = snippet_el.get_text(strip=True) if snippet_el else title
                pub_date = _parse_publish_date(story)
                results.append({
                    "source":       "adaderana",
                    "title":        title,
                    "content":      content if len(content) > 20 else title,
                    "url":          href,
                    "published_at": pub_date,
                })
        except Exception as e:
            print(f"  Ada Derana error for '{keyword}': {e}")
        return results

    # ------------------------------------------------------------------ #
    #  Sunday Times Sri Lanka                                             #
    # ------------------------------------------------------------------ #
    def scrape_sundaytimes(self, keyword: str = "tourist fraud") -> List[Dict]:
        url = f"https://www.sundaytimes.lk/search/?query={keyword.replace(' ', '+')}"
        results = []
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code != 200:
                return results
            soup = BeautifulSoup(resp.text, "html.parser")
            articles = soup.select("article, .search-result, h2 a, h3 a")
            for a in articles[:10]:
                title_el = a if a.name == "a" else a.select_one("a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                href = title_el.get("href", "")
                pub_date = _parse_publish_date(a)
                if title and len(title) > 15:
                    results.append({
                        "source":       "sundaytimes",
                        "title":        title,
                        "content":      title,
                        "url":          href,
                        "published_at": pub_date,
                    })
        except Exception as e:
            print(f"  Sunday Times error for '{keyword}': {e}")
        return results

    # ------------------------------------------------------------------ #
    #  Main entry point                                                   #
    # ------------------------------------------------------------------ #
    def collect_all(self) -> List[Dict]:
        print("--- Web Scraping Collection ---")
        all_results: List[Dict] = []

        # Ada Derana — most reliable Sri Lanka news source
        for kw in ["tourist scam", "tourist fraud", "travel safety Sri Lanka", "tourist harassment"]:
            print(f"  [Ada Derana] '{kw}'")
            all_results.extend(self.scrape_adaderana(kw))
            time.sleep(0.8)

        # Sunday Times
        for kw in ["tourist scam", "tourist fraud", "travel warning"]:
            print(f"  [Sunday Times] '{kw}'")
            all_results.extend(self.scrape_sundaytimes(kw))
            time.sleep(0.8)

        # Try Daily Mirror (may 403)
        for query in ["scam", "tourist fraud", "travel safety"]:
            print(f"  [Daily Mirror] '{query}'")
            all_results.extend(self.scrape_daily_mirror(query))
            time.sleep(0.8)



        print(f"  Web scraping complete: {len(all_results)} items collected.")
        return all_results
