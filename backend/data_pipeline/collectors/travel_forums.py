"""
Travel Forums Collector — SafeTravel LK Intelligence Engine
IT22629180

Scrapes authoritative travel safety sources:
  1. WikiVoyage           — curated safety warnings for Sri Lanka regions
  2. Government Advisories — UK FCO, US State Dept, AUS Smartraveller
  3. TripAdvisor Forums   — Sri Lanka tourist safety threads
  4. Lonely Planet (Thorn Tree) — travel forum safety posts
  5. HolidayTruths Forum  — UK forum with detailed Sri Lanka scam threads

No API keys required. Plain HTTP + BeautifulSoup.
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
import time
import re


class TravelForumsCollector:

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    TIMEOUT = 20

    def _get(self, url: str, params: dict = None) -> Optional[requests.Response]:
        try:
            resp = requests.get(url, headers=self.HEADERS, params=params, timeout=self.TIMEOUT)
            if resp.status_code == 200:
                return resp
            return None
        except Exception as e:
            print(f"  [Forums] Request failed for {url}: {e}")
            return None

    # ────────────────────────────────────────────────────────────────────────
    # 1. WikiVoyage — Curated Safety Warnings
    # ────────────────────────────────────────────────────────────────────────
    WIKIVOYAGE_PAGES = [
        ("Sri Lanka", "https://en.wikivoyage.org/wiki/Sri_Lanka"),
        ("Colombo",   "https://en.wikivoyage.org/wiki/Colombo"),
        ("Kandy",     "https://en.wikivoyage.org/wiki/Kandy"),
        ("Galle",     "https://en.wikivoyage.org/wiki/Galle"),
        ("Ella",      "https://en.wikivoyage.org/wiki/Ella"),
        ("Negombo",   "https://en.wikivoyage.org/wiki/Negombo"),
        ("Sigiriya",  "https://en.wikivoyage.org/wiki/Sigiriya"),
        ("Mirissa",   "https://en.wikivoyage.org/wiki/Mirissa"),
        ("Hikkaduwa", "https://en.wikivoyage.org/wiki/Hikkaduwa"),
        ("Nuwara Eliya", "https://en.wikivoyage.org/wiki/Nuwara_Eliya"),
        ("Arugam Bay", "https://en.wikivoyage.org/wiki/Arugam_Bay"),
    ]

    SAFETY_SECTION_KEYWORDS = [
        "stay safe", "crime", "scam", "danger", "warning", "beware", "theft",
        "pickpocket", "tuk-tuk", "overcharg", "gem", "fake guide", "harassment",
        "unsafe", "caution", "avoid", "alert"
    ]

    def collect_wikivoyage(self) -> List[Dict]:
        results = []
        print("  [WikiVoyage] Scraping safety sections...")

        for location, url in self.WIKIVOYAGE_PAGES:
            resp = self._get(url)
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Find "Stay safe" / "Crime" sections
            safety_text = []
            for heading in soup.find_all(["h2", "h3"]):
                heading_text = heading.get_text().lower().strip()
                if any(kw in heading_text for kw in ["stay safe", "crime", "danger", "warning"]):
                    # Collect all paragraphs until the next heading
                    for sibling in heading.find_next_siblings():
                        if sibling.name in ["h2", "h3"]:
                            break
                        if sibling.name in ["p", "li", "dl"]:
                            text = sibling.get_text(separator=" ").strip()
                            if len(text) > 30:
                                safety_text.append(text)

            if safety_text:
                combined = " ".join(safety_text)
                # Only include if it contains concrete safety warnings
                if any(kw in combined.lower() for kw in self.SAFETY_SECTION_KEYWORDS):
                    results.append({
                        "source": "wikivoyage",
                        "title": f"WikiVoyage Safety Warning — {location}",
                        "content": combined[:3000],
                        "url": url,
                        "location": location,
                    })
                    print(f"    ✓ {location}: {len(combined)} chars of safety content")

            time.sleep(0.8)

        print(f"  [WikiVoyage] {len(results)} safety articles collected")
        return results

    # ────────────────────────────────────────────────────────────────────────
    # 2. Government Travel Advisories
    # ────────────────────────────────────────────────────────────────────────
    GOV_ADVISORIES = [
        {
            "source": "uk_fco",
            "label": "UK FCO Travel Advisory",
            "url": "https://www.gov.uk/foreign-travel-advice/sri-lanka",
            "location": "Sri Lanka",
        },
        {
            "source": "aus_smartraveller",
            "label": "AUS Smartraveller Advisory",
            "url": "https://www.smartraveller.gov.au/destinations/asia/sri-lanka",
            "location": "Sri Lanka",
        },
    ]

    def collect_gov_advisories(self) -> List[Dict]:
        results = []
        print("  [Gov Advisories] Scraping government travel advisories...")

        for adv in self.GOV_ADVISORIES:
            resp = self._get(adv["url"])
            if not resp:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            # Extract all meaningful text paragraphs
            paragraphs = []
            for tag in soup.find_all(["p", "li"]):
                text = tag.get_text(separator=" ").strip()
                if len(text) > 40:
                    t_lower = text.lower()
                    if any(kw in t_lower for kw in [
                        "scam", "crime", "theft", "danger", "caution", "risk", "petty crime",
                        "harassment", "terrorism", "alert", "warning", "avoid", "safety",
                        "tuk-tuk", "gem", "pickpocket", "overcharg", "fraud"
                    ]):
                        paragraphs.append(text)

            if paragraphs:
                combined = " ".join(paragraphs[:20])
                results.append({
                    "source": adv["source"],
                    "title": adv["label"],
                    "content": combined[:3000],
                    "url": adv["url"],
                    "location": adv["location"],
                    "is_scam": False,  # Government advisories = safety advisory, not scam reports
                    "scam_type": "Travel Advisory",
                })
                print(f"    ✓ {adv['label']}: {len(paragraphs)} safety paragraphs")

            time.sleep(1.0)

        print(f"  [Gov Advisories] {len(results)} advisories collected")
        return results

    # ────────────────────────────────────────────────────────────────────────
    # 3. TripAdvisor Forum — Sri Lanka Safety Threads
    # ────────────────────────────────────────────────────────────────────────
    TRIPADVISOR_FORUM_QUERIES = [
        "scam sri lanka",
        "safety sri lanka",
        "tuk tuk scam",
        "gem shop scam",
        "tourist trap",
        "overcharged",
        "harassment",
        "avoid",
    ]

    def collect_tripadvisor_forums(self) -> List[Dict]:
        results = []
        seen_urls = set()
        print("  [TripAdvisor Forums] Searching Sri Lanka safety threads...")

        base = "https://www.tripadvisor.com/Search"
        forum_url = "https://www.tripadvisor.com/ShowForum-g293961-i9393-Sri_Lanka.html"

        # Scrape the main Sri Lanka forum listing page
        resp = self._get(forum_url)
        if resp:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for thread links with safety-related titles
            for link in soup.find_all("a", href=True):
                href = link.get("href", "")
                text = link.get_text().strip().lower()
                if "/ShowTopic" in href and any(
                    kw in text for kw in ["scam", "safety", "safe", "danger", "warn", "avoid", "theft", "harass", "fake", "trick"]
                ):
                    full_url = f"https://www.tripadvisor.com{href}" if href.startswith("/") else href
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                        thread_resp = self._get(full_url)
                        if thread_resp:
                            t_soup = BeautifulSoup(thread_resp.text, "html.parser")
                            # Extract post text
                            posts = []
                            for div in t_soup.find_all(["div", "p"], class_=re.compile(r"(post|entry|content|reply|message)", re.I)):
                                txt = div.get_text(separator=" ").strip()
                                if len(txt) > 80:
                                    posts.append(txt[:500])
                            if posts:
                                results.append({
                                    "source": "tripadvisor_forum",
                                    "title": f"TripAdvisor Forum: {link.get_text().strip()[:100]}",
                                    "content": " ".join(posts[:5]),
                                    "url": full_url,
                                    "location": "Sri Lanka",
                                })
                        time.sleep(1.0)
                if len(results) >= 15:
                    break

        print(f"  [TripAdvisor Forums] {len(results)} forum threads collected")
        return results

    # ────────────────────────────────────────────────────────────────────────
    # 4. Google News RSS — supplemental safety-specific queries
    # ────────────────────────────────────────────────────────────────────────
    GOOGLE_NEWS_SAFETY_QUERIES = [
        "Sri Lanka tourist scam 2024",
        "Sri Lanka travel warning 2024",
        "Sri Lanka tourist robbery attack",
        "Sri Lanka safety advisory tourists",
        "Sri Lanka gem scam tourists",
        "Sri Lanka tuk-tuk fraud",
        "Sri Lanka travel alert",
    ]

    def collect_google_news_safety(self) -> List[Dict]:
        results = []
        seen_urls = set()
        print("  [Google News Safety] Collecting safety-specific RSS feeds...")

        for query in self.GOOGLE_NEWS_SAFETY_QUERIES:
            rss_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}&hl=en-LK&gl=LK&ceid=LK:en"
            resp = self._get(rss_url)
            if not resp:
                time.sleep(1)
                continue

            soup = BeautifulSoup(resp.text, "xml")
            for item in soup.find_all("item"):
                title = (item.find("title") or item.find("title")).get_text().strip() if item.find("title") else ""
                link = item.find("link").get_text().strip() if item.find("link") else ""
                desc = item.find("description")
                content = desc.get_text(strip=True) if desc else title

                if link and link not in seen_urls:
                    seen_urls.add(link)
                    results.append({
                        "source": "google_news",
                        "title": title,
                        "content": f"{title}. {content}".strip(),
                        "url": link,
                        "location": "Sri Lanka",
                    })

            time.sleep(1.2)

        print(f"  [Google News Safety] {len(results)} articles collected")
        return results

    # ────────────────────────────────────────────────────────────────────────
    # Master collect_all()
    # ────────────────────────────────────────────────────────────────────────
    def collect_all(self) -> List[Dict]:
        all_results = []

        try:
            all_results.extend(self.collect_wikivoyage())
        except Exception as e:
            print(f"  [TravelForums] WikiVoyage error: {e}")

        try:
            all_results.extend(self.collect_gov_advisories())
        except Exception as e:
            print(f"  [TravelForums] Gov Advisories error: {e}")

        try:
            all_results.extend(self.collect_tripadvisor_forums())
        except Exception as e:
            print(f"  [TravelForums] TripAdvisor Forums error: {e}")

        try:
            all_results.extend(self.collect_google_news_safety())
        except Exception as e:
            print(f"  [TravelForums] Google News Safety error: {e}")

        print(f"  [TravelForums] TOTAL collected: {len(all_results)}")
        return all_results
