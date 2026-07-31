"""
Source Credibility Weight System — SafeTravel LK (PhD-Level Methodology)
IT22629180

Assigns a credibility weight (0.0 – 1.0) to every data record.
Higher weight = more influence on the weighted risk score formula.

TIER STRUCTURE:
  Tier 0  (1.00)        — Official Government Travel Advisories (validation anchors)
  Tier 1  (0.79–0.88)   — Sri Lanka Press-Council registered / TRCSL-licensed news
  Tier 2a (0.65–0.72)   — Verified journalism & CC-licensed open sources
  Tier 2b (0.58–0.64)   — Semi-verified platforms (Google News, Maps, TripAdvisor)
  Tier 3  (0.35–0.52)   — Community-moderated UGC (Reddit, travel forums, Quora)

EXCLUDED (not collected — methodology decision):
  TikTok   — entertainment-first, ToS violation via scraping, weight too low to justify
  Instagram — lifestyle platform, caption text insufficient, ToS violation via scraping
  Facebook  — ethics concern (no user consent for research), ToS violation via scraping
  Nitter    — unofficial Twitter mirror, legally grey provenance, replaced by official API

METHODOLOGY NOTE:
  A future extension of this work would add primary survey data (tourist interviews
  at BIA/major hotels) as a Tier 0 ground-truth source. This is documented as the
  primary limitation in the paper's Limitations section.
"""

from typing import Optional


# ─── Tier 0: Official Government Travel Advisories ───────────────────────────
# These are the VALIDATION ANCHORS — not dynamically collected, but cited as the
# authoritative baseline that confirms the system's scam taxonomy is real.
# Weight: 1.00 — highest possible. Crown Copyright / US Federal / Australian Govt.
#
# UK FCDO:       gov.uk/foreign-travel-advice/sri-lanka/safety-and-security
# US State Dept: travel.state.gov → Sri Lanka
# Australia DFAT: smartraveller.gov.au/destinations/asia/sri-lanka
# Canada:        travel.gc.ca/destinations/sri-lanka

GOVERNMENT_SOURCES = {
    "fcdo_gov_uk":        1.00,   # UK Foreign, Commonwealth & Development Office
    "us_state_dept":      1.00,   # US Department of State travel advisory
    "australia_dfat":     1.00,   # Australian Dept. of Foreign Affairs & Trade
    "canada_travel":      1.00,   # Global Affairs Canada travel advisory
    "sltda_official":     0.97,   # Sri Lanka Tourism Development Authority (SLTDA)
    "tourist_police_lk":  0.97,   # Sri Lanka Tourist Police incident records
}


# ─── Tier 1: Sri Lanka Press-Council Registered / TRCSL-Licensed News ─────────
# Justification:
#   - TRCSL broadcast licence (TV channels) or Sri Lanka Press Council membership
#   - Named editorial team with legal accountability for published content
#   - .lk TLD registered through LK Domain Registry (Government-regulated)
#   - Multi-decade track record of Sri Lanka-specific reporting

SL_CERTIFIED_NEWS_SOURCES = {
    "adaderana":       0.88,   # Ada Derana — TRCSL broadcast licence, largest 24hr news network
    "newsfirst":       0.86,   # Newsfirst — TRCSL broadcast licence, major TV news
    "daily_mirror_lk": 0.85,   # Daily Mirror — est. 1923, Press Council member
    "sundaytimes_lk":  0.85,   # Sunday Times — established national weekly
    "themorning_lk":   0.83,   # The Morning — independent editorial, .lk domain
    "theisland_lk":    0.83,   # The Island — long-running broadsheet, .lk domain
    "colombo_gazette": 0.82,   # Colombo Gazette — English online news, named editors
    "ceylon_today":    0.81,   # Ceylon Today — national daily, .lk domain
    "hirunews_lk":     0.80,   # Hiru News — TRCSL TV licence, Sinhala coverage
    "economynext_lk":  0.80,   # Economy Next — business reporting, journalist bylines
    "newswire_lk":     0.79,   # Newswire.lk — .lk wire service
}


# ─── Tier 2a: Verified Journalism & CC-Licensed Open Sources ─────────────────
# Justification: Official API access (YouTube), editorial board oversight (Google News),
# or formal open content licence (WikiVoyage CC BY-SA 3.0).

TIER_2A_SOURCES = {
    # YouTube — only Sri Lanka certified news channels are collected (see youtube.py)
    # The collector restricts to: Ada Derana English, Newsfirst, Daily Mirror, Hiru News, Newswire
    "youtube":          0.72,   # YouTube transcript from verified SL news channel

    # WikiVoyage — CC BY-SA 3.0 licence, Wikimedia Foundation editorial standards
    "wikivoyage":       0.70,   # Formally licensed, community-curated, permanently citable

    # TripAdvisor moderated forum (thread replies = cross-validation by multiple users)
    "tripadvisor_forum": 0.68,
}


# ─── Tier 2b: Semi-Verified Platforms ────────────────────────────────────────
# Justification: Google Publisher Policies (News), location-linking (Maps),
# or peer-vote system (TripAdvisor reviews).

TIER_2B_SOURCES = {
    "google_news":   0.65,   # Google Publisher Policies require editorial standards
    "google_maps":   0.62,   # Location-linked to registered physical place; Google-moderated
    "tripadvisor":   0.60,   # Helpful_Votes peer validation (base; boosted below)
    "reviews_csv":   0.60,   # Same dataset as TripAdvisor (structured CSV version)
}


# ─── Tier 3: Community-Moderated UGC ─────────────────────────────────────────
# Justification for INCLUSION: Community upvoting / moderation provides weak
# but non-zero credibility signal. Only contribute to risk scores when
# corroborated by Tier 1–2 sources.
#
# IMPORTANT: Reddit collected via public JSON API (not RFR programme).
# Disclosed as a methodology limitation in the paper.

TIER_3_SOURCES = {
    "reddit":   0.42,   # 25+ subreddits; upvote score + comment count as credibility proxy
    "quora":    0.35,   # Q&A platform; answer upvotes provide weak peer signal
    "forum":    0.38,   # Moderated travel forums (HolidayTruths, Lonely Planet ThornTree)
}


# ─── EXCLUDED SOURCES (not collected) ────────────────────────────────────────
# These weight values are defined ONLY for logging/reporting purposes.
# The pipeline does NOT collect from these sources.

EXCLUDED_SOURCES = {
    # TikTok: entertainment-first, ToS violation via Apify scraping,
    # strong creator incentive to exaggerate, insufficient textual signal.
    "tiktok":     None,

    # Instagram: lifestyle platform, captions too short (<30 words avg),
    # ToS violation via Apify scraping, no credibility signals.
    "instagram":  None,

    # Facebook Groups: ethics concern — users post in communities without
    # consenting to research. ToS violation via Apify scraping.
    "facebook":   None,

    # Nitter / Twitter: Nitter is an unofficial mirror in legal dispute with X Corp.
    # Using it creates provenance problems. Replace with official X Academic API
    # if Twitter data is required in future work.
    "nitter":     None,
    "twitter":    None,
}

# Fallback for any unknown source not in the tables above
DEFAULT_WEIGHT = 0.30


# ─── Bonus Weight Modifiers (applied ON TOP of base weight) ──────────────────

def get_helpful_votes_bonus(helpful_votes: int) -> float:
    """TripAdvisor/Google Maps: bonus for peer-validated reviews."""
    if helpful_votes >= 20: return 0.15
    if helpful_votes >= 10: return 0.10
    if helpful_votes >= 5:  return 0.07
    if helpful_votes >= 1:  return 0.03
    return 0.0


def get_contributor_experience_bonus(contributions: int) -> float:
    """TripAdvisor: bonus for established reviewers (harder-to-fake accounts)."""
    if contributions >= 500: return 0.08
    if contributions >= 100: return 0.05
    if contributions >= 50:  return 0.02
    return 0.0


def get_reddit_engagement_bonus(score: int, num_comments: int) -> float:
    """Reddit: bonus for high community engagement."""
    if score >= 100 and num_comments >= 20: return 0.10
    if score >= 50 or num_comments >= 10:   return 0.06
    if score >= 10:                          return 0.02
    return 0.0


# ─── Main Public Function ─────────────────────────────────────────────────────

def get_source_weight(
    source: str,
    helpful_votes: int = 0,
    user_contributions: int = 0,
    reddit_score: int = 0,
    num_comments: int = 0,
) -> float:
    """
    Returns the final credibility weight (0.0 – 1.0) for a data record.
    Returns 0.0 for explicitly excluded sources (should never reach DB).
    """
    source_lower = (source or "").lower().strip()

    # Excluded sources — should never be saved, but guard defensively
    if source_lower in EXCLUDED_SOURCES:
        return 0.0

    base = (
        GOVERNMENT_SOURCES.get(source_lower)
        or SL_CERTIFIED_NEWS_SOURCES.get(source_lower)
        or TIER_2A_SOURCES.get(source_lower)
        or TIER_2B_SOURCES.get(source_lower)
        or TIER_3_SOURCES.get(source_lower)
        or DEFAULT_WEIGHT
    )

    bonus = (
        get_helpful_votes_bonus(helpful_votes)
        + get_contributor_experience_bonus(user_contributions)
        + get_reddit_engagement_bonus(reddit_score, num_comments)
    )

    # Cap at 0.97 — nothing collected automatically outranks a government document
    return round(min(base + bonus, 0.97), 4)


def is_excluded_source(source: str) -> bool:
    """Returns True if this source has been excluded from the research methodology."""
    return (source or "").lower().strip() in EXCLUDED_SOURCES


def get_user_friendly_source_label(weight: float) -> str:
    """User-understandable source credibility label for public UI display."""
    if weight >= 0.97: return "🏛️ Official Government Advisory"
    if weight >= 0.79: return "🏛️ Verified News Outlets"
    if weight >= 0.65: return "🟢 Verified Traveler Reviews"
    if weight >= 0.55: return "📍 Location-Verified Reviews"
    if weight >= 0.35: return "💬 Public Community Discussion"
    if weight == 0.0:  return "⚠️ Excluded / Unverified Source"
    return "💬 Public Community Discussion"


def get_weight_tier_label(weight: float) -> str:
    """Human-readable tier label for UI display and paper documentation."""
    if weight >= 0.97: return "🏛️ Official Government Advisory"
    if weight >= 0.79: return "🏛️ Verified News Outlets"
    if weight >= 0.65: return "🟢 Verified Traveler Reviews"
    if weight >= 0.55: return "📍 Location-Verified Reviews"
    if weight >= 0.35: return "💬 Public Community Discussion"
    if weight == 0.0:  return "⚠️ Excluded / Unverified Source"
    return "💬 Public Community Discussion"


def get_all_weights_table() -> list:
    """Sorted table of all active (non-excluded) sources for reporting."""
    all_sources = {}
    all_sources.update(GOVERNMENT_SOURCES)
    all_sources.update(SL_CERTIFIED_NEWS_SOURCES)
    all_sources.update(TIER_2A_SOURCES)
    all_sources.update(TIER_2B_SOURCES)
    all_sources.update(TIER_3_SOURCES)

    return sorted(
        [{"source": k, "weight": v, "tier": get_weight_tier_label(v)}
         for k, v in all_sources.items()],
        key=lambda x: x["weight"],
        reverse=True,
    )
