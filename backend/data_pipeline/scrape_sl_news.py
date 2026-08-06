"""
Sri Lanka News Scraper v2 — via Google News RSS site-targeting
IT22629180

Problem: Daily Mirror, Daily News, Sunday Times, The Island, Ada Derana, NewsFirst, 
         Hiru News all return 403/404 on direct search requests.

Solution: Use Google News RSS with site: operator to get real article URLs from each 
          news outlet, then fetch the actual article pages directly (no search page involved).

  RSS URL: https://news.google.com/rss/search?q=tourist+scam+site:dailymirror.lk&hl=en

This bypasses the search page entirely — we get article canonical URLs from Google's index,
then hit the article pages directly which are publicly accessible.
"""

import sys
import os
import re
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin

from data_pipeline.strict_filter import score_relevance
from app.db.session import SessionLocal
from app.db.models import Report

# ── HTTP config ────────────────────────────────────────────────────────────────
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
    "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

SEARCH_TIMEOUT  = 18
ARTICLE_TIMEOUT = 20
DELAY_RSS       = 1.0
DELAY_ARTICLE   = 0.8

# ── Sri Lanka destination → (lat, lon) ─────────────────────────────────────────
SL_GEO = {
    "colombo":       (6.9271,  79.8612),
    "kandy":         (7.2906,  80.6337),
    "galle":         (6.0535,  80.2210),
    "ella":          (6.8728,  81.0464),
    "sigiriya":      (7.9573,  80.7600),
    "negombo":       (7.2083,  79.8358),
    "mirissa":       (5.9483,  80.4716),
    "arugam":        (6.8399,  81.8325),
    "arugam bay":    (6.8399,  81.8325),
    "nuwara eliya":  (6.9497,  80.7891),
    "trincomalee":   (8.5874,  81.2152),
    "hikkaduwa":     (6.1395,  80.1061),
    "unawatuna":     (5.9997,  80.2489),
    "bentota":       (6.4221,  80.0009),
    "matara":        (5.9549,  80.5550),
    "jaffna":        (9.6615,  80.0255),
    "dambulla":      (7.8675,  80.6517),
    "anuradhapura":  (8.3114,  80.4037),
    "polonnaruwa":   (7.9403,  81.0188),
    "badulla":       (6.9934,  81.0550),
    "tangalle":      (6.0233,  80.7992),
    "weligama":      (5.9751,  80.4295),
    "yala":          (6.3744,  81.5219),
    "pinnawala":     (7.2994,  80.3478),
    "haputale":      (6.7699,  80.9606),
    "mount lavinia": (6.8389,  79.8670),
    "katunayake":    (7.1699,  79.8838),
    "pettah":        (6.9367,  79.8502),
}


def extract_geo(text: str):
    t = text.lower()
    for loc, (lat, lon) in SL_GEO.items():
        if loc in t:
            return loc.title(), lat, lon
    return "Sri Lanka", 6.9271, 79.8612


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ══════════════════════════════════════════════════════════════════════════════
#  SITE DEFINITIONS
#  Each entry: (slug, display_name, site_domain, body_css_selectors, source_weight)
# ══════════════════════════════════════════════════════════════════════════════

NEWS_SITES = [
    {
        "slug":   "daily_mirror",
        "label":  "Daily Mirror",
        "domain": "dailymirror.lk",
        "body":   [".article-content", ".entry-content", "#content-body", ".news-body", "article .body", ".dm-article"],
        "weight": 0.72,
    },
    {
        "slug":   "daily_news",
        "label":  "Daily News",
        "domain": "dailynews.lk",
        "body":   [".article-body", ".field-items", ".content-area", "article .content", ".node-body"],
        "weight": 0.65,
    },
    {
        "slug":   "sunday_times",
        "label":  "Sunday Times",
        "domain": "sundaytimes.lk",
        "body":   [".article-content", ".story-body", ".news-content", ".entry-content", "article .body"],
        "weight": 0.75,
    },
    {
        "slug":   "the_island",
        "label":  "The Island",
        "domain": "island.lk",
        "body":   [".article-body", ".entry-content", ".td-post-content", ".post-content", "article .content"],
        "weight": 0.68,
    },
    {
        "slug":   "ada_derana",
        "label":  "Ada Derana",
        "domain": "adaderana.lk",
        "body":   [".article-content", "#newsContent", ".AdaText", ".news-content", ".story-text"],
        "weight": 0.70,
    },
    {
        "slug":   "newsfirst",
        "label":  "NewsFirst / Sirasa",
        "domain": "newsfirst.lk",
        "body":   [".entry-content", ".article-body", ".post-content", ".td-post-content", "article p"],
        "weight": 0.65,
    },
    {
        "slug":   "hiru_news",
        "label":  "Hiru News",
        "domain": "hirunews.lk",
        "body":   [".news-body", ".article-body", ".entry-content", ".content-body", "article p"],
        "weight": 0.60,
    },
    {
        "slug":   "newswire",
        "label":  "Newswire.lk",
        "domain": "newswire.lk",
        "body":   [".entry-content", ".article-body", ".post-content", ".article-text", "article p"],
        "weight": 0.63,
    },
]

# Search queries to run per site
TOURIST_SAFETY_QUERIES = [
    "tourist scam Sri Lanka",
    "tourist fraud Sri Lanka",
    "tourist robbed Sri Lanka",
    "tourist safety warning Sri Lanka",
    "tourist harassment Sri Lanka",
    "tourist arrested scammer Sri Lanka",
    "tourist victim Sri Lanka",
    "tourist overcharged Sri Lanka",
]


def fetch_rss_articles_for_site(site: dict) -> list[dict]:
    """
    Queries Google News RSS with site: operator for a specific domain.
    Returns list of {title, url, description} dicts.
    """
    domain = site["domain"]
    slug   = site["slug"]
    found  = []
    seen   = set()

    for q in TOURIST_SAFETY_QUERIES:
        query = f"{q} site:{domain}"
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"

        try:
            resp = requests.get(rss_url, headers=RSS_HEADERS, timeout=SEARCH_TIMEOUT)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "lxml-xml")
            for item in soup.find_all("item")[:10]:
                title_el = item.find("title")
                link_el  = item.find("link")
                desc_el  = item.find("description")

                title = clean_text(title_el.get_text()) if title_el else ""
                # Google News RSS <link> is odd — next sibling text is the actual URL
                link = ""
                if link_el:
                    link = link_el.get_text(strip=True)
                    if not link:
                        ns = link_el.next_sibling
                        if ns:
                            link = str(ns).strip()

                desc = clean_text(re.sub(r"<[^>]+>", " ", desc_el.get_text())) if desc_el else ""

                if not title or not link or link in seen:
                    continue
                # Skip Google's own redirect URLs — we want the canonical article URL
                # Google RSS link is often the Google redirect; we use it as-is
                seen.add(link)
                found.append({
                    "source": slug,
                    "title": title,
                    "summary": desc,
                    "url": link,
                })

            time.sleep(DELAY_RSS)

        except Exception as e:
            print(f"    [RSS:{slug}] Error for '{q}': {e}")

    print(f"    [RSS:{domain}] Found {len(found)} article links via Google News RSS")
    return found


def fetch_article_body(url: str, body_sels: list[str]) -> str:
    """Fetch and extract full article body text from the article page."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=ARTICLE_TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        for sel in body_sels:
            el = soup.select_one(sel)
            if el:
                paras = el.find_all(["p", "h2", "h3"])
                text = " ".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if len(text) > 80:
                    return clean_text(text)

        # Fallback: all <p> with enough content
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
        return clean_text(" ".join(paras))

    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  STRICT FILTER + DB INGEST
# ══════════════════════════════════════════════════════════════════════════════

def classify_scam_type(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["gem scam", "gem shop", "gemstone scam"]):
        return "Gem Scam"
    if any(k in t for k in ["tuk tuk scam", "tuk-tuk scam", "three-wheeler scam", "trishaw scam"]):
        return "Tuk-Tuk Scam"
    if any(k in t for k in ["fake guide", "fake monk", "bogus guide", "fake ticket"]):
        return "Fake Guide"
    if any(k in t for k in ["taxi scam", "airport scam", "airport taxi overcharge"]):
        return "Transport Fraud"
    if any(k in t for k in ["overcharged", "ripped off", "overpriced", "inflated price"]):
        return "Overcharging"
    if any(k in t for k in ["pickpocket", "bag snatch", "stolen", "mugged", "robbed", "theft"]):
        return "Theft / Robbery"
    if any(k in t for k in ["harassed", "harassment", "assault", "attacked", "groped"]):
        return "Harassment / Assault"
    if any(k in t for k in ["food poison", "drugged", "spiked"]):
        return "Food / Drink Spiking"
    return "Tourist Safety Incident"


def ingest_to_db(items: list[dict], site: dict, db) -> tuple[int, int, int]:
    inserted = rejected = duped = 0

    for item in items:
        title   = (item.get("title")   or "").strip()
        content = (item.get("content") or "").strip()
        url     = (item.get("url")     or "").strip()

        if len(content) < 30:
            # Content too short — use title + summary as content
            content = f"{title}. {item.get('summary', '')}".strip()
        if len(content) < 20:
            rejected += 1
            continue

        # Strict filter
        scoring = score_relevance(title, content)
        if not scoring["passes"]:
            rejected += 1
            continue

        # URL dedup against DB
        if url and db.query(Report).filter(Report.url == url).first():
            duped += 1
            continue

        # Title dedup
        if title and db.query(Report).filter(Report.title.ilike(f"%{title[:50]}%")).first():
            duped += 1
            continue

        loc_name, lat, lon = extract_geo(f"{title} {content}")
        scam_type  = classify_scam_type(f"{title} {content}")
        body_lower = (title + " " + content).lower()
        risk_level = 2 if any(k in body_lower for k in ["attacked", "assault", "robbed", "mugged", "stabbed", "injured"]) else 1

        report = Report(
            source=site["slug"],
            url=url or None,
            title=title or "Safety Report",
            content=content[:3000],
            latitude=lat,
            longitude=lon,
            is_scam=True,
            scam_type=scam_type,
            risk_level=risk_level,
            sentiment_score=-0.65,
            location_name=loc_name,
            source_weight=site["weight"],
            demographic_target="Tourists",
        )
        db.add(report)
        inserted += 1
        if inserted % 10 == 0:
            db.commit()

    db.commit()
    return inserted, rejected, duped


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_all():
    db = SessionLocal()

    grand_inserted = 0
    grand_rejected = 0
    grand_duped    = 0

    print("=" * 68)
    print("  SafeTravel LK — SL News Scraper v2 (Google RSS → Article Fetch)")
    print(f"  Outlets: {len(NEWS_SITES)} | Queries per site: {len(TOURIST_SAFETY_QUERIES)}")
    print("=" * 68)

    for site in NEWS_SITES:
        print(f"\n{'─'*60}")
        print(f"  [{site['label']}]  ({site['domain']})")
        print(f"{'─'*60}")

        try:
            # Step 1: Get article URLs via Google News RSS
            raw_items = fetch_rss_articles_for_site(site)

            if not raw_items:
                print(f"  ⚠ No articles found via RSS for {site['label']}")
                continue

            # Step 2: Fetch full body for each article
            enriched = []
            print(f"  Fetching {len(raw_items)} article bodies...")
            for item in raw_items:
                body = fetch_article_body(item["url"], site["body"])
                item["content"] = body if len(body) > 80 else item.get("summary", item["title"])
                enriched.append(item)
                time.sleep(DELAY_ARTICLE)

            # Step 3: Strict filter + DB write
            ins, rej, dup = ingest_to_db(enriched, site, db)
            grand_inserted += ins
            grand_rejected += rej
            grand_duped    += dup

            status = "✅" if ins > 0 else "⚪"
            print(f"  {status} {site['label']}: +{ins} saved | {rej} filtered | {dup} duplicates")

        except Exception as e:
            print(f"  ❌ {site['label']} FAILED: {e}")

    db.close()

    print("\n" + "=" * 68)
    print(f"  SCRAPE COMPLETE")
    print(f"  Total saved   : {grand_inserted}")
    print(f"  Total filtered: {grand_rejected}")
    print(f"  Total duped   : {grand_duped}")
    print("=" * 68)


if __name__ == "__main__":
    run_all()
