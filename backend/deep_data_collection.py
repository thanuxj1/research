"""
Deep Data Collection — SafeTravel LK Research Engine
IT22629180

Covers ALL sources:
  1. Reddit (25+ subreddits, full search)
  2. Facebook (public travel groups via Apify)
  3. YouTube (video transcripts via YouTube Data API)
  4. Google Maps (negative reviews via Apify)
  5. TikTok (hashtag search via Apify)
  6. Instagram (hashtag/location search via Apify)
  7. Twitter/X (via Nitter public mirror)
  8. Google News RSS
  9. TripAdvisor Forums
  10. WikiVoyage Safety Sections
  11. Sri Lanka News Sites (10+ local outlets)

Strict Filter: ONLY negative tourist experiences in Sri Lanka are stored.
"""

import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from apify_client import ApifyClient
from data_pipeline.collectors.reddit import RedditCollector
from data_pipeline.collectors.youtube import YouTubeCollector
from data_pipeline.collectors.facebook import FacebookCollector
from data_pipeline.collectors.google_maps import GoogleMapsCollector
from data_pipeline.collectors.social import SocialCollector
from data_pipeline.strict_filter import passes_strict_filter
from app.core.config import settings
from app.db.session import SessionLocal
from app.db.models import Report
from app.ml.nlp_pipeline import NLPPipeline
from app.ml.source_weights import get_source_weight


def save_items(db, nlp, items: list, label: str) -> int:
    """Save items to DB after passing strict relevance filter and NLP analysis."""
    saved = skipped = filtered = 0
    for item in items:
        title = (item.get("title") or "").strip()
        content = (item.get("content") or "").strip()
        if not content or len(content) < 15:
            skipped += 1
            continue

        # Strict relevance gate — must be negative tourist experience
        if not passes_strict_filter(title, content):
            filtered += 1
            continue

        # Deduplication
        url = (item.get("url") or "").strip()
        if url and db.query(Report).filter(Report.url == url).first():
            skipped += 1
            continue

        # AI Analysis
        try:
            analysis = nlp.analyze_text(content)
        except Exception:
            analysis = {}

        lat = item.get("latitude") or analysis.get("latitude")
        lon = item.get("longitude") or analysis.get("longitude")
        loc_name = item.get("location") or analysis.get("location_name")

        # MUST have a specific location
        if not lat or not lon or not loc_name or loc_name.lower() in ("sri lanka", "ceylon"):
            skipped += 1
            continue

        # Source credibility weight
        sw = get_source_weight(
            source=item.get("source", "unknown"),
            helpful_votes=int(item.get("helpful_votes", 0) or 0),
            user_contributions=int(item.get("user_contributions", 0) or 0),
            reddit_score=int(item.get("score", 0) or 0),
            num_comments=int(item.get("num_comments", 0) or 0),
        )

        report = Report(
            source=item.get("source", "unknown"),
            url=url or None,
            title=title or analysis.get("scam_type") or "Safety Report",
            content=content,
            latitude=lat,
            longitude=lon,
            is_scam=analysis.get("is_scam", False),
            scam_type=item.get("scam_type") or analysis.get("scam_type"),
            risk_level=analysis.get("risk_level", 1),
            sentiment_score=analysis.get("sentiment_score", 0.0),
            location_name=item.get("location") or analysis.get("location_name"),
            demographic_target=item.get("demographic"),
            source_weight=sw,
        )
        db.add(report)
        saved += 1

    db.commit()
    print(f"  [{label}] Saved: {saved} | Filtered (irrelevant): {filtered} | Skipped (dup/short): {skipped}")
    return saved


# ── EXCLUDED SOURCES ─────────────────────────────────────────────────────────
# The following sources were evaluated and excluded from the research methodology.
# Reasons are documented in source_weights.py and the paper's Methodology section.
#
# TikTok   — entertainment-first platform; Apify scraping violates ToS;
#             strong creator incentive to exaggerate; insufficient textual signal.
# Instagram — lifestyle captions too short for NLP; Apify scraping violates ToS.
# Facebook  — ethics concern (no user consent to research); ToS violation.
# Nitter    — unofficial Twitter mirror; legally grey provenance.
#
# To re-evaluate any of these, see the EXCLUDED_SOURCES dict in source_weights.py.


def run_deep_collection():
    print("=" * 65)
    print("  SafeTravel LK — Full Source Deep Collection (PhD Methodology)")
    print("  Active:   Reddit | YouTube (SL News Channels) | Google Maps")
    print("            Google News | Sri Lanka News Sites | TripAdvisor")
    print("            WikiVoyage | Travel Forums")
    print("  Excluded: TikTok | Instagram | Facebook | Nitter")
    print("  Reason:   See source_weights.py — EXCLUDED_SOURCES")
    print("=" * 65)

    db = SessionLocal()
    nlp = NLPPipeline()
    total_new = 0

    apify = ApifyClient(settings.APIFY_API_TOKEN) if settings.APIFY_API_TOKEN else None
    if not apify:
        print("  WARNING: No APIFY_API_TOKEN — Google Maps will be skipped.")

    # ── 1. Reddit ──────────────────────────────────────────────────────────
    print("\n[1/6] Reddit (25+ subreddits)...")
    print("  NOTE: Collected via public JSON API. RFR programme not applied for.")
    print("        Disclosed as limitation in paper. Used as Tier 3 supplement only.")
    reddit = RedditCollector()
    total_new += save_items(db, nlp, reddit.collect_all(), "Reddit")

    # ── 2. YouTube (Sri Lanka certified news channels ONLY) ─────────────────
    print("\n[2/6] YouTube — Sri Lanka Certified News Channels only...")
    print("  Channels: Ada Derana, Newsfirst, Daily Mirror, Hiru News, Newswire")
    print("  Non-news channels are filtered out in youtube.py (allowed_keywords check)")
    youtube = YouTubeCollector()
    yt_queries = [
        "Sri Lanka tourist scam 2024", "Sri Lanka tuk tuk scam tourists",
        "Sri Lanka gem shop scam", "Sri Lanka tourist safety warning",
        "Sri Lanka tourist harassment", "Sri Lanka travel danger avoid",
        "Sri Lanka tourist robbed pickpocket", "Sri Lanka travel tips safety",
    ]
    for q in yt_queries:
        total_new += save_items(db, nlp, youtube.collect(query=q, limit=10), f"YouTube:{q[:30]}")

    # ── 3. Google Maps ─────────────────────────────────────────────────────
    print("\n[3/6] Google Maps Reviews (location-linked, via Apify)...")
    if apify:
        gmaps = GoogleMapsCollector()
        total_new += save_items(db, nlp, gmaps.collect_all(limit_per_query=5), "GoogleMaps")
    else:
        print("  [Google Maps] Skipped — no Apify token.")

    # ── 4. Google News + Sri Lanka News Sites ──────────────────────────────
    print("\n[4/6] Google News RSS + Sri Lanka News Sites (10+ outlets)...")
    social = SocialCollector()
    total_new += save_items(db, nlp, social.collect_all(), "News+Social")

    # ── 5. TripAdvisor CSV (structured dataset with credibility signals) ───
    print("\n[5/6] TripAdvisor Reviews.csv (Helpful_Votes + Contribution weighting)...")
    # Processed separately via import_reviews_csv.py — included here for logging
    print("  Reviews.csv is pre-loaded. Run import_reviews_csv.py to refresh.")

    # ── 6. Facebook — EXCLUDED ─────────────────────────────────────────────
    # Reason: ethics concern (no user consent), ToS violation via Apify scraping.
    # If required in future: apply for Facebook Graph API academic research access.
    print("\n[6/6] Facebook — EXCLUDED (ethics/ToS). Skipped.")

    db.close()
    print("\n" + "=" * 65)
    print(f"  DEEP COLLECTION COMPLETE")
    print(f"  Total new research records added: {total_new}")
    print(f"  Sources excluded: TikTok, Instagram, Facebook, Nitter")
    print(f"  All records passed strict tourist-negative-experience filter.")
    print("=" * 65)


if __name__ == "__main__":
    run_deep_collection()
