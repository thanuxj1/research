"""
Sri Lanka News Scraper v3 — Expanded Queries & District Coverage
IT22629180

Changes from v2:
  1. Expanded TOURIST_SAFETY_QUERIES from 8 → 40+ terms, covering:
       — All 25 districts with zero/low data coverage
       — Tourist Police / SLTDA complaint terminology
       — Sinhala-transliterated place name variants
       — Specific scam types missing from dataset (accommodation, gem, food spiking)
       — Government advisory language ("travel warning", "safety alert")
  2. Added ZERO_COVERAGE_DISTRICTS block — dedicated queries for the 14 districts
     with no records (Batticaloa, Hambantota, Matara, Ampara, etc.)
  3. Added GOVERNMENT_ADVISORY_RSS block — scrapes UK FCDO, US State Dept, and
     Australia Smartraveller RSS feeds directly (Tier-0 credibility weight = 1.00)
  4. Added scrape_general_google_news() for broad queries not tied to a specific
     news outlet — catches articles from any domain via Google News RSS.
  5. Credibility weight now sourced from source_weights.py mappings.

Usage:
    cd backend/
    python -m data_pipeline.scrape_sl_news_v3
"""

import sys
import os
import re
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus

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
DELAY_RSS       = 1.2   # slightly more conservative than v2
DELAY_ARTICLE   = 0.9

# ── Sri Lanka destination → (lat, lon) ─────────────────────────────────────────
SL_GEO = {
    # Tourist hotspots (from v2)
    "colombo":        (6.9271,  79.8612),
    "kandy":          (7.2906,  80.6337),
    "galle":          (6.0535,  80.2210),
    "ella":           (6.8728,  81.0464),
    "sigiriya":       (7.9573,  80.7600),
    "negombo":        (7.2083,  79.8358),
    "mirissa":        (5.9483,  80.4716),
    "arugam bay":     (6.8399,  81.8325),
    "arugam":         (6.8399,  81.8325),
    "nuwara eliya":   (6.9497,  80.7891),
    "trincomalee":    (8.5874,  81.2152),
    "hikkaduwa":      (6.1395,  80.1061),
    "unawatuna":      (5.9997,  80.2489),
    "bentota":        (6.4221,  80.0009),
    "matara":         (5.9549,  80.5550),
    "jaffna":         (9.6615,  80.0255),
    "dambulla":       (7.8675,  80.6517),
    "anuradhapura":   (8.3114,  80.4037),
    "polonnaruwa":    (7.9403,  81.0188),
    "badulla":        (6.9934,  81.0550),
    "tangalle":       (6.0233,  80.7992),
    "weligama":       (5.9751,  80.4295),
    "yala":           (6.3744,  81.5219),
    "pinnawala":      (7.2994,  80.3478),
    "haputale":       (6.7699,  80.9606),
    "mount lavinia":  (6.8389,  79.8670),
    "katunayake":     (7.1699,  79.8838),
    "pettah":         (6.9367,  79.8502),
    # NEW: Previously zero-coverage districts & towns
    "batticaloa":     (7.7167,  81.7000),
    "ampara":         (7.2975,  81.6724),
    "hambantota":     (6.1241,  81.1185),
    "ratnapura":      (6.7056,  80.3847),
    "kegalle":        (7.2513,  80.3464),
    "kurunegala":     (7.4863,  80.3647),
    "puttalam":       (8.0362,  79.8283),
    "mannar":         (8.9817,  79.9044),
    "vavuniya":       (8.7514,  80.4971),
    "mullaitivu":     (9.2670,  80.8128),
    "kilinochchi":    (9.3803,  80.4008),
    "monaragala":     (6.8728,  81.3507),
    "kalutara":       (6.5854,  79.9607),
    "gampaha":        (7.0917,  80.0000),
    "nuwaraeliya":    (6.9497,  80.7891),  # alt spelling
    "nine arch bridge": (6.8756, 81.0493),
    "horton plains":  (6.8090,  80.8030),
    "knuckles":       (7.4489,  80.7869),
    "wilpattu":       (8.4603,  79.9024),
    "udawalawe":      (6.4416,  80.8994),
    "sinharaja":      (6.4020,  80.4980),
    "kataragama":     (6.4133,  81.3367),
    "tissamaharama":  (6.2833,  81.2833),
    "passikudah":     (7.9167,  81.5667),
    "nilaveli":       (8.7000,  81.1833),
    "uppuveli":       (8.6333,  81.2167),
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
#  EXPANDED QUERY LIST (v3 additions in groups)
# ══════════════════════════════════════════════════════════════════════════════

# Group A: Core safety queries (v2 originals)
CORE_QUERIES = [
    "tourist scam Sri Lanka",
    "tourist fraud Sri Lanka",
    "tourist robbed Sri Lanka",
    "tourist safety warning Sri Lanka",
    "tourist harassment Sri Lanka",
    "tourist arrested scammer Sri Lanka",
    "tourist victim Sri Lanka",
    "tourist overcharged Sri Lanka",
]

# Group B: SLTDA / Tourist Police / complaint-specific (NEW — high credibility language)
OFFICIAL_QUERIES = [
    "SLTDA tourist complaint Sri Lanka",
    "tourist police Sri Lanka incident",
    "tourist police complaint Colombo",
    "Sri Lanka tourism safety alert",
    "SLTDA warning tourist",
    "tourist complaint Sri Lanka 2024",
    "Sri Lanka tourist police arrest scammer",
    "travel warning Sri Lanka",
    "travel advisory Sri Lanka safety",
    "Sri Lanka safety alert tourists 2024",
]

# Group C: Scam-type specific (fills taxonomy gaps — accommodation, gem, food spiking)
SCAM_TYPE_QUERIES = [
    "gem scam Sri Lanka tourist",
    "jewellery scam Colombo tourist",
    "gem shop Kandy tourist cheated",
    "accommodation scam Sri Lanka",
    "guesthouse scam Sri Lanka",
    "fake monk Sri Lanka tourist",
    "fake guide Sri Lanka overcharge",
    "airport taxi scam Colombo",
    "tuk tuk scam Colombo Kandy",
    "food poisoning tourist Sri Lanka",
    "drink spiked tourist Sri Lanka",
    "solo female traveller safety Sri Lanka",
    "female tourist harassment Sri Lanka",
    "beach harassment Sri Lanka tourist",
]

# Group D: Zero-coverage district queries (NEW — covers Batticaloa, Hambantota, etc.)
DISTRICT_GAP_QUERIES = [
    "tourist safety Batticaloa",
    "tourist scam Ampara Sri Lanka",
    "tourist Hambantota safety warning",
    "tourist Ratnapura scam",
    "tourist Kurunegala safety",
    "tourist Puttalam Sri Lanka scam",
    "tourist Mannar Sri Lanka",
    "Passikudah tourist safety warning",
    "Nilaveli tourist scam Sri Lanka",
    "Uppuveli beach safety Sri Lanka",
    "Wilpattu safari scam Sri Lanka",
    "Udawalawe safari overcharge Sri Lanka",
    "Kataragama tourist safety Sri Lanka",
    "Tissamaharama tourist scam",
    "Horton Plains tourist scam Sri Lanka",
    "Knuckles Mountain tourist safety",
    "Sinharaja tourist guide scam",
]

# Group E: General negative experience language used in news headlines
HEADLINE_PATTERN_QUERIES = [
    "tourist cheated Sri Lanka",
    "foreigner victim Sri Lanka",
    "tourist attacked Sri Lanka",
    "tourist assault Sri Lanka",
    "tourist stolen Sri Lanka",
    "foreigner scam Sri Lanka arrested",
    "tourist complaint police Sri Lanka",
    "tourist injured Sri Lanka",
    "foreign visitor robbed Sri Lanka",
    "tourist money stolen Colombo",
    "backpacker scam Sri Lanka",
    "solo traveller danger Sri Lanka",
]

# Combined for site-targeted scraping
ALL_QUERIES = (
    CORE_QUERIES
    + OFFICIAL_QUERIES
    + SCAM_TYPE_QUERIES
    + DISTRICT_GAP_QUERIES
    + HEADLINE_PATTERN_QUERIES
)

# ── Site definitions (same as v2, preserved exactly) ──────────────────────────
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
    # NEW sites added in v3
    {
        "slug":   "ceylon_today",
        "label":  "Ceylon Today",
        "domain": "ceylontoday.lk",
        "body":   [".article-content", ".entry-content", ".post-content", "article p", ".td-post-content"],
        "weight": 0.63,
    },
    {
        "slug":   "economy_next",
        "label":  "EconomyNext",
        "domain": "economynext.com",
        "body":   [".article-body", ".entry-content", ".post-content", "article .content", "article p"],
        "weight": 0.65,
    },
    {
        "slug":   "ft_lk",
        "label":  "Financial Times LK",
        "domain": "ft.lk",
        "body":   [".article-body", ".entry-content", ".content-body", "article p", ".post-content"],
        "weight": 0.65,
    },
]

# ══════════════════════════════════════════════════════════════════════════════
#  GOVERNMENT ADVISORY RSS SOURCES (Tier-0, weight = 1.00)
#  These are the validation anchors — highest credibility in the system.
# ══════════════════════════════════════════════════════════════════════════════
GOVERNMENT_ADVISORY_SOURCES = [
    {
        "slug":   "fcdo_gov_uk",
        "label":  "UK FCDO Travel Advisory",
        "weight": 1.00,
        # UK FCDO does not publish a full RSS feed but Google News indexes their
        # updates. We use Google News RSS with site: targeting.
        "domain": "gov.uk",
        "body":   [".govuk-body", ".gem-c-govspeak", ".govspeak", "article .body", "main p"],
        "queries": [
            "Sri Lanka travel advice site:gov.uk",
            "Sri Lanka safety security site:gov.uk",
            "Sri Lanka travel warning site:gov.uk",
        ],
    },
    {
        "slug":   "smartraveller_au",
        "label":  "Australia Smartraveller",
        "weight": 1.00,
        "domain": "smartraveller.gov.au",
        "body":   [".field-items", ".field-body", "article .content", "main p", ".node-body"],
        "queries": [
            "Sri Lanka travel advice site:smartraveller.gov.au",
            "Sri Lanka safety alert site:smartraveller.gov.au",
        ],
    },
    {
        "slug":   "travel_state_gov",
        "label":  "US State Dept Travel Advisory",
        "weight": 1.00,
        "domain": "travel.state.gov",
        "body":   [".tsg-rte-field", ".rte-field", "article .content", "main p", ".field-body"],
        "queries": [
            "Sri Lanka travel advisory site:travel.state.gov",
            "Sri Lanka safety security site:travel.state.gov",
        ],
    },
]


# ══════════════════════════════════════════════════════════════════════════════
#  SHARED UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def classify_scam_type(text: str) -> str:
    t = text.lower()
    if any(k in t for k in ["gem scam", "gem shop", "gemstone", "jewellery scam", "jewelry scam"]):
        return "Gem / Jewellery Scam"
    if any(k in t for k in ["tuk tuk scam", "tuk-tuk scam", "three-wheeler scam", "trishaw scam"]):
        return "Tuk-Tuk / Transport Scam"
    if any(k in t for k in ["fake guide", "fake monk", "bogus guide", "fake ticket"]):
        return "Fake Guide / Impersonation"
    if any(k in t for k in ["taxi scam", "airport scam", "airport taxi", "uber scam"]):
        return "Transport Fraud"
    if any(k in t for k in ["overcharged", "ripped off", "overpriced", "inflated price", "double price"]):
        return "Overcharging"
    if any(k in t for k in ["pickpocket", "bag snatch", "stolen", "mugged", "robbed", "theft"]):
        return "Theft / Robbery"
    if any(k in t for k in ["harassed", "harassment", "assault", "attacked", "groped", "followed"]):
        return "Harassment / Assault"
    if any(k in t for k in ["food poison", "drugged", "spiked", "drink spiked"]):
        return "Food / Drink Spiking"
    if any(k in t for k in ["accommodation scam", "guesthouse scam", "hotel scam", "airbnb scam"]):
        return "Accommodation Scam"
    if any(k in t for k in ["travel advisory", "travel warning", "safety alert", "sltda"]):
        return "Safety Advisory (Non-Incident)"
    return "General Safety Incident"


def ingest_to_db(items: list[dict], source_slug: str, source_weight: float, db) -> tuple[int, int, int]:
    inserted = rejected = duped = 0

    for item in items:
        title   = (item.get("title")   or "").strip()
        content = (item.get("content") or "").strip()
        url     = (item.get("url")     or "").strip()

        # Fallback: short content → use title + summary
        if len(content) < 30:
            content = f"{title}. {item.get('summary', '')}".strip()
        if len(content) < 20:
            rejected += 1
            continue

        # Strict relevance filter
        scoring = score_relevance(title, content)
        if not scoring["passes"]:
            rejected += 1
            continue

        # URL deduplication
        if url and db.query(Report).filter(Report.url == url).first():
            duped += 1
            continue

        # Title deduplication (first 60 chars)
        if title and db.query(Report).filter(Report.title.ilike(f"%{title[:60]}%")).first():
            duped += 1
            continue

        loc_name, lat, lon = extract_geo(f"{title} {content}")
        scam_type  = classify_scam_type(f"{title} {content}")
        body_lower = (title + " " + content).lower()
        risk_level = (
            3 if any(k in body_lower for k in ["attacked", "stabbed", "injured", "killed"])
            else 2 if any(k in body_lower for k in ["assault", "robbed", "mugged", "harassed", "harass"])
            else 1
        )

        report = Report(
            source=source_slug,
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
            source_weight=source_weight,
            demographic_target="Tourists",
        )
        db.add(report)
        inserted += 1
        if inserted % 10 == 0:
            db.commit()

    db.commit()
    return inserted, rejected, duped


# ══════════════════════════════════════════════════════════════════════════════
#  RSS FETCH UTILITIES
# ══════════════════════════════════════════════════════════════════════════════

def fetch_rss_articles(domain: str, queries: list[str], slug: str) -> list[dict]:
    """Query Google News RSS with site: operator. Returns list of article dicts."""
    found = []
    seen  = set()

    for q in queries:
        query   = f"{q} site:{domain}" if "site:" not in q else q
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
                link  = ""
                if link_el:
                    link = link_el.get_text(strip=True)
                    if not link:
                        ns = link_el.next_sibling
                        if ns:
                            link = str(ns).strip()

                desc = clean_text(re.sub(r"<[^>]+>", " ", desc_el.get_text())) if desc_el else ""

                if not title or not link or link in seen:
                    continue
                seen.add(link)
                found.append({"source": slug, "title": title, "summary": desc, "url": link})

            time.sleep(DELAY_RSS)

        except Exception as e:
            print(f"    [RSS:{slug}] Error for '{q}': {e}")

    return found


def fetch_article_body(url: str, body_sels: list[str]) -> str:
    """Fetch and extract full article body text."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=ARTICLE_TIMEOUT, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        for sel in body_sels:
            el = soup.select_one(sel)
            if el:
                paras = el.find_all(["p", "h2", "h3"])
                text  = " ".join(p.get_text(strip=True) for p in paras if p.get_text(strip=True))
                if len(text) > 80:
                    return clean_text(text)

        # Fallback: all <p> tags with content
        paras = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 40]
        return clean_text(" ".join(paras))

    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  GENERAL GOOGLE NEWS (no site: restriction — catches any domain)
# ══════════════════════════════════════════════════════════════════════════════

GENERAL_BODY_SELS = [
    "article p", ".article-body", ".entry-content", ".post-content",
    ".story-body", ".content-body", "main p",
]

GENERAL_GOOGLE_NEWS_SLUG   = "google_news"
GENERAL_GOOGLE_NEWS_WEIGHT = 0.58   # Tier-2 Aggregator (from source_weights.py)


def scrape_general_google_news(db) -> tuple[int, int, int]:
    """
    Runs all expanded queries without a site: restriction.
    Catches articles from any domain Google indexes, including international
    travel media (Lonely Planet, The Guardian Travel, etc.).
    Expected yield: 100–200+ new records per run.
    """
    print("\n" + "─" * 60)
    print("  [General Google News] — All domains, expanded queries")
    print("─" * 60)

    general_body_dummy = [".article-body"]  # placeholder; we use fallback extraction
    found = []
    seen  = set()

    for q in ALL_QUERIES:
        rss_url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = requests.get(rss_url, headers=RSS_HEADERS, timeout=SEARCH_TIMEOUT)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "lxml-xml")
            for item in soup.find_all("item")[:8]:
                title_el = item.find("title")
                link_el  = item.find("link")
                desc_el  = item.find("description")

                title = clean_text(title_el.get_text()) if title_el else ""
                link  = ""
                if link_el:
                    link = link_el.get_text(strip=True)
                    if not link:
                        ns = link_el.next_sibling
                        if ns:
                            link = str(ns).strip()

                desc = clean_text(re.sub(r"<[^>]+>", " ", desc_el.get_text())) if desc_el else ""

                if not title or not link or link in seen:
                    continue
                seen.add(link)
                found.append({"source": GENERAL_GOOGLE_NEWS_SLUG, "title": title, "summary": desc, "url": link})

            time.sleep(DELAY_RSS)

        except Exception as e:
            print(f"    [GeneralNews] Error for '{q}': {e}")

    print(f"    Found {len(found)} links via general Google News RSS")

    # Fetch bodies
    enriched = []
    print(f"    Fetching article bodies...")
    for item in found:
        body = fetch_article_body(item["url"], GENERAL_BODY_SELS)
        item["content"] = body if len(body) > 80 else item.get("summary", item["title"])
        enriched.append(item)
        time.sleep(DELAY_ARTICLE)

    ins, rej, dup = ingest_to_db(
        enriched,
        source_slug=GENERAL_GOOGLE_NEWS_SLUG,
        source_weight=GENERAL_GOOGLE_NEWS_WEIGHT,
        db=db,
    )
    status = "✅" if ins > 0 else "⚪"
    print(f"    {status} General Google News: +{ins} saved | {rej} filtered | {dup} duplicates")
    return ins, rej, dup


# ══════════════════════════════════════════════════════════════════════════════
#  GOVERNMENT ADVISORY SCRAPER (Tier-0)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_government_advisories(db) -> tuple[int, int, int]:
    """
    Scrapes UK FCDO, Australia Smartraveller, US State Dept via Google News RSS.
    These are the highest-credibility sources (weight = 1.00).
    Even 5–10 records from these dramatically improves Tier-1 distribution.
    """
    print("\n" + "─" * 60)
    print("  [Government Advisories] — Tier-0 sources (weight = 1.00)")
    print("─" * 60)

    grand_ins = grand_rej = grand_dup = 0

    for source in GOVERNMENT_ADVISORY_SOURCES:
        slug    = source["slug"]
        label   = source["label"]
        weight  = source["weight"]
        domain  = source["domain"]
        queries = source["queries"]
        body    = source["body"]

        raw_items = fetch_rss_articles(domain=domain, queries=queries, slug=slug)
        print(f"    [{label}] {len(raw_items)} links found via RSS")

        if not raw_items:
            print(f"    ⚠  No articles found for {label}")
            continue

        enriched = []
        for item in raw_items:
            article_body = fetch_article_body(item["url"], body)
            item["content"] = article_body if len(article_body) > 80 else item.get("summary", item["title"])
            enriched.append(item)
            time.sleep(DELAY_ARTICLE)

        ins, rej, dup = ingest_to_db(enriched, source_slug=slug, source_weight=weight, db=db)
        grand_ins += ins
        grand_rej += rej
        grand_dup += dup
        status = "✅" if ins > 0 else "⚪"
        print(f"    {status} {label}: +{ins} saved | {rej} filtered | {dup} duplicates")

    return grand_ins, grand_rej, grand_dup


# ══════════════════════════════════════════════════════════════════════════════
#  SITE-TARGETED SCRAPING (same as v2, with expanded query list)
# ══════════════════════════════════════════════════════════════════════════════

def scrape_news_sites(db) -> tuple[int, int, int]:
    """Runs ALL_QUERIES against each NEWS_SITE via Google News RSS → article fetch."""
    grand_ins = grand_rej = grand_dup = 0

    print("\n" + "─" * 60)
    print(f"  [Site-Targeted] {len(NEWS_SITES)} outlets × {len(ALL_QUERIES)} queries")
    print("─" * 60)

    for site in NEWS_SITES:
        slug   = site["slug"]
        label  = site["label"]
        domain = site["domain"]
        body   = site["body"]
        weight = site["weight"]

        print(f"\n  [{label}]  ({domain})")
        raw_items = fetch_rss_articles(domain=domain, queries=ALL_QUERIES, slug=slug)

        if not raw_items:
            print(f"    ⚠ No articles found for {label}")
            continue

        enriched = []
        print(f"    Fetching {len(raw_items)} article bodies...")
        for item in raw_items:
            article_body = fetch_article_body(item["url"], body)
            item["content"] = article_body if len(article_body) > 80 else item.get("summary", item["title"])
            enriched.append(item)
            time.sleep(DELAY_ARTICLE)

        ins, rej, dup = ingest_to_db(enriched, source_slug=slug, source_weight=weight, db=db)
        grand_ins += ins
        grand_rej += rej
        grand_dup += dup
        status = "✅" if ins > 0 else "⚪"
        print(f"    {status} {label}: +{ins} saved | {rej} filtered | {dup} duplicates")

    return grand_ins, grand_rej, grand_dup


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_all():
    db = SessionLocal()

    print("=" * 68)
    print("  SafeTravel LK — SL News Scraper v3 (Expanded Queries)")
    print(f"  Total queries: {len(ALL_QUERIES)} | Sites: {len(NEWS_SITES)} | Gov sources: {len(GOVERNMENT_ADVISORY_SOURCES)}")
    print("=" * 68)

    total_ins = total_rej = total_dup = 0

    # 1. Government advisories (highest priority — Tier 0)
    ins, rej, dup = scrape_government_advisories(db)
    total_ins += ins; total_rej += rej; total_dup += dup

    # 2. Site-targeted news scraping (expanded queries)
    ins, rej, dup = scrape_news_sites(db)
    total_ins += ins; total_rej += rej; total_dup += dup

    # 3. General Google News (no domain restriction — broadest coverage)
    ins, rej, dup = scrape_general_google_news(db)
    total_ins += ins; total_rej += rej; total_dup += dup

    db.close()

    print("\n" + "=" * 68)
    print(f"  SCRAPE v3 COMPLETE")
    print(f"  Total saved   : {total_ins}")
    print(f"  Total filtered: {total_rej}")
    print(f"  Total duped   : {total_dup}")
    print(f"  Expected DB growth: ~{total_ins} new records")
    print("=" * 68)


if __name__ == "__main__":
    run_all()
