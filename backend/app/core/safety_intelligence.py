"""
Safety Intelligence Engine — IDW Spatial Interpolation + Composite Scoring
IT22629180

Core PhD-level differentiator: computes safety decisions for ANY point
in Sri Lanka using Inverse Distance Weighted interpolation across
120K+ cross-referenced, source-weighted, temporally-decayed reports.

No human can replicate this manually.
"""
import math
import sqlite3
import os
import re
from datetime import datetime, timezone
from collections import Counter
from urllib.parse import quote_plus

DOMAIN_MAP = {
    "dailymirror": "dailymirror.lk",
    "daily_mirror": "dailymirror.lk",
    "daily mirror": "dailymirror.lk",
    "newsfirst": "newsfirst.lk",
    "news_first": "newsfirst.lk",
    "adaderana": "adaderana.lk",
    "derana": "adaderana.lk",
    "sundaytimes": "sundaytimes.lk",
    "sunday_times": "sundaytimes.lk",
    "hirunews": "hirunews.lk",
    "hiru": "hirunews.lk",
    "newswire": "newswire.lk",
    "ceylon": "ceylontoday.lk",
    "theisland": "island.lk",
    "island": "island.lk",
    "tamilguardian": "tamilguardian.com",
    "tripadvisor": "tripadvisor.com",
}

# ── Scam-specific safety tips ─────────────────────────────────────────────────
SCAM_SAFETY_TIPS = {
    "Overcharging": [
        "Always agree on the price BEFORE getting into a tuk-tuk or taxi.",
        "Use metered taxis or ride-hailing apps (PickMe, Uber) for fair pricing.",
        "Ask your hotel for approximate costs to common destinations.",
        "Carry small denominations to avoid 'no change' overcharging tricks.",
    ],
    "Price Gouging": [
        "Confirm item prices or fare rates before accepting services.",
        "Use official ride-hailing apps (PickMe/Uber) to avoid inflated rates.",
        "Verify menu prices and bill breakdowns carefully at tourist spots.",
    ],
    "General Scam": [
        "Be cautious of unsolicited help from strangers at tourist attractions.",
        "Verify any claims by checking with your hotel or official tourism offices.",
        "If a deal sounds too good to be true, it probably is.",
        "Report suspicious activity to the Tourist Police hotline: 1912.",
    ],
    "General Tourist Safety": [
        "Stay alert in busy tourist hubs and maintain awareness of belongings.",
        "Keep emergency contacts saved offline (Tourist Police: 1912).",
        "Use accredited tour operators and official transport options.",
    ],
    "Fake Guide": [
        "Only hire guides through your hotel or SLTDA-certified agencies.",
        "Ask to see the guide's official SLTDA accreditation card.",
        "Avoid 'free' guides who approach you at attraction entrances — they often lead to commission-based shops.",
    ],
    "Unlicensed Guide Scam": [
        "Verify official credentials before hiring any tour guide.",
        "Refuse unrequested guided walk-throughs at historical sites.",
    ],
    "Theft": [
        "Keep valuables in your hotel safe, not on your person.",
        "Use a money belt or front pocket for cash and cards.",
        "Be extra vigilant on crowded beaches, buses, and markets.",
    ],
    "Theft & Robbery": [
        "Keep bags zipped and held closely in crowded tourist zones.",
        "Do not display expensive electronics or large amounts of cash.",
    ],
    "Harassment": [
        "Travel in groups when possible, especially after dark.",
        "Stay in well-lit, populated areas at night.",
        "Download the local emergency number: 119 (Police) or 1912 (Tourist Police).",
    ],
    "Tourist Harassment": [
        "Avoid isolated streets late at night and stay in well-lit areas.",
        "Report persistent harassment immediately to local authorities or hotel staff.",
    ],
    "Physical Assault": [
        "Avoid isolated areas, especially at night.",
        "Stay in well-known tourist zones with good lighting.",
        "Report any incidents immediately to 119 (Police) or 1912 (Tourist Police).",
    ],
    "Safety Hazard / Assault": [
        "Exercise heightened caution in this area and avoid traveling alone after dark.",
        "Ensure emergency contacts (1912 Tourist Police / 119 Emergency) are readily accessible.",
    ],
    "Unsafe Area": [
        "Check government travel advisories before visiting remote areas.",
        "Inform your hotel when visiting off-the-beaten-path locations.",
        "Avoid areas with no mobile phone coverage without a local guide.",
    ],
    "Tuk-Tuk Overcharging": [
        "Insist on using a metered tuk-tuk or book via PickMe / Uber.",
        "Agree on exact fare before starting the trip if meters are unavailable.",
    ],
    "Commission Shop Trap": [
        "Decline unsolicited detour stops to spice gardens, gem shops, or tea factories.",
        "Purchase souvenirs directly from verified municipal markets or certified stores.",
    ],
    "Gem & Jewelry Scam": [
        "Never purchase gemstones from unverified street vendors or recommended 'discount' shops.",
        "Demand official gemology certification for high-value purchases.",
    ],
    "safe": [
        "This location has low recorded incident density.",
        "Standard travel precautions are still recommended.",
        "Keep emergency contacts accessible: Tourist Police 1912, Ambulance 1990.",
    ],
    "high_risk": [
        "Exercise heightened vigilance — multiple safety incidents documented nearby.",
        "Avoid poorly lit or secluded areas, especially after sunset.",
        "Rely strictly on verified ride-hailing apps (PickMe / Uber) for local transit.",
    ],
    "moderate_risk": [
        "Maintain normal safety awareness and secure personal belongings.",
        "Verify rates for transport and tours before agreeing to services.",
    ],
}

GENERAL_TIPS = [
    "Save the Tourist Police number: 1912 (available 24/7).",
    "Use official taxi meters or ride-hailing apps for transport.",
    "Keep photocopies of your passport separate from the original.",
    "Register your trip with your country's embassy in Colombo.",
]


# Global Scam Display Name Mapping
SCAM_DISPLAY_NAMES = {
    "gem_scam": "Gem & Jewelry Scam",
    "Gem Scam": "Gem & Jewelry Scam",
    "commission_shop": "Commission Shop Trap",
    "tuk_tuk_scam": "Tuk-Tuk Overcharging",
    "Tuk Tuk Scam": "Tuk-Tuk Overcharging",
    "Tuk-Tuk Scam": "Tuk-Tuk Overcharging",
    "fake_guide": "Unlicensed Guide Scam",
    "Fake Guide": "Unlicensed Guide Scam",
    "harassment": "Tourist Harassment",
    "Harassment": "Tourist Harassment",
    "theft": "Theft & Robbery",
    "Theft": "Theft & Robbery",
    "Theft / Robbery": "Theft & Robbery",
    "overcharging": "Price Gouging",
    "Overcharging": "Price Gouging",
    "General Scam": "General Tourist Safety",
    "Physical Assault": "Safety Hazard / Assault",
    "Unsafe Area": "General Tourist Safety",
    "Accommodation Scam": "Accommodation Fraud",
    "accommodation_scam": "Accommodation Fraud",
    "currency_scam": "Currency Exchange Scam",
    "wildlife_exploit": "Wildlife & Tour Exploitation",
    "Accident / Hazard": "Road & Physical Hazard",
    "Health / Hygiene": "Health & Sanitation Warning",
    "Transport Fraud": "Transport & Taxi Fraud",
    "safe": "Verified Safe Area",
}

# ── Non-Tourism Noise Filter ──────────────────────────────────────────
NON_TOURISM_NOISE = {
    # Politics & governance
    "ballot paper", "electorate", "polling booth", "elections department",
    "parliament election", "presidential election", "cabinet minister",
    "political party", "parliamentary election", "nomination paper",
    "provincial council", "booth in", "annulled as a group",
    "elections commissioner", "elections commission", "election law", "election propaganda",
    "haj pilgrimage", "mecca", "governor", "mp ", "minister of", "prime minister",
    "election official", "district secretary", "local council",
    "high commissioner", "deputy high commissioner", "land reforms commission",
    "presidential commission", "bribery commission", "human rights commission",
    "police commission", "cabinet sub committee", "french embassy",
    "un high commissioner", "charity commission", "commission to investigate",
    "commissioner of", "lrc director", "port agreement",
    "new constitution", "constitutional reform",
    # Migrant labor & foreign employment (NOT tourism)
    "migrant worker", "foreign employment bureau", "foreign employment",
    "housemaid", "housemaids", "domestic worker", "domestic workers",
    "saudi employer", "kuwait employer", "safe houses provided by the embassies",
    "expired contracts", "non- payment of wages", "non-payment of wages",
    "plantation worker", "garment factory", "garment worker",
    "labor bureau", "labour bureau", "slbfe",
    # Domestic crime & financial crime unrelated to tourists
    "underworld", "underworld figure", "gang leader", "drug lord",
    "finance company", "finance co", "microfinance", "bank robbery", "pawn shop",
    "drug trafficking", "heroin", "cocaine", "methamphetamine", "ice",
    "narcotics bureau", "drug haul", "contraband", "illegal timber",
    "smuggling ring", "murder suspect", "murder charge", "murder accused",
    "child abuse", "domestic violence", "custody battle",
    "faked his own", "fake abduction",
    # Animal rights, temple elephants, zoo & religious disputes (NOT tourist safety)
    "bellanwila", "myan kumara", "chief incumbent", "tusker",
    "beaten or harassed", "zoological department", "animal rights",
    "captive elephant", "elephant bath", "thera", "monk", "buddhist monk",
    "temple premises", "animal cruelty", "stray dogs", "rabies vaccination",
    "archaeological department", "excavation",
    # Military / Police internal affairs & student protests
    "police woman", "army lieutenant", "navy officer", "air force officer",
    "university vice chancellor", "student union", "lecturers involved",
    "student protest", "higher education", "pradeshiya sabha", "uc chairman",
    # Court / legal proceedings (domestic)
    "remanded till", "remanded until", "remanded to", "further remanded",
    "magistrate court", "high court", "supreme court ruling",
    "plaintiff", "defendant", "bail application", "court order",
    "no-confidence motion", "impeachment",
    # More political party / governance noise
    "state minister", "state ministry", "opposition leader", "opposition party",
    "tnpf", "calls for immediate arrest", "calls on the government",
    "remove state min", "allegedly threatening",
    "political solution", "political crisis", "political reform",
    "ceasefire", "peace talk", "peace process", "ltte", "ex-ltte", "ex-ltteers",
    "jhu", "jathika hela urumaya", "jayalalithaa", "ranjan", "lawyers urge", "catholic lawyers",
    "frontline socialist party", "fsp",
    "tamil national", "sri lanka freedom party", "united national party",
    # Labor & trade unions
    "trade union", "wage dispute", "salary arrears", "pension",
    "salary increase", "bus fare hike", "fuel price",
    # Weather & disaster (not safety intelligence)
    "disaster management", "affected by floods", "heavy showers",
    "met dept", "meteorology", "sluice gates", "evacuation drills",
    "river levels", "dmc reported", "disaster management center",
    "disaster management centre",
    # Wildlife / environmental enforcement (not tourist-facing)
    "poaching ring", "illegal logging", "wildlife trafficking",
    "excise department", "excise raid",
    # Prison / inmate (not tourist-relevant)
    "prison riot", "inmate", "prisoner escape", "correctional",
}

# Tourism-positive keywords: if ANY of these appear alongside a noise keyword,
# the report may still be relevant (e.g., "tourist arrested" is relevant)
TOURISM_OVERRIDE = {
    "tourist", "traveler", "traveller", "backpack", "hotel guest",
    "tuk tuk", "tuk-tuk", "gem scam", "guide scam", "safari scam",
    "overcharg", "rip off", "rip-off", "ripoff",
}

def refine_scam_type(title: str, content: str, raw_scam_type: str = None) -> str:
    """
    Refines raw scam classification using contextual keyword analysis to prevent
    false positive tags (e.g., positive reviews, over-commercialization complaints, or incidental transit mentions).
    """
    text = f"{title or ''} {content or ''}".lower()
    st_str = str(raw_scam_type or '').strip()

    # 1. Positive Reviews -> General Tourist Safety (do NOT tag positive reviews as scams!)
    positive_review_phrases = ["a must", "amazing", "wonderful", "fantastic", "loved it", "great place", "highly recommend", "beautiful view", "stunning", "perfect day", "best experience", "must visit", "highlight of our trip"]
    scam_negation_keywords = ["scam", "cheat", "fraud", "theft", "harass", "overcharg", "robbed", "stole", "ripped off", "fake", "extort", "danger", "warning", "unsafe"]
    is_positive = any(p in text for p in positive_review_phrases)
    has_scam_words = any(k in text for k in scam_negation_keywords)
    if is_positive and not has_scam_words:
        return "general_safety"

    # 2. Direct Harassment / Assault
    if any(w in text for w in ["sexually harassed", "sexual harassment", "groped", "molested", "assaulted", "attacked", "followed at night"]):
        return "harassment"

    # 3. Disambiguate Gem & Jewelry Scam
    if st_str in ["gem_scam", "Gem Scam", "Gem & Jewelry Scam"]:
        gem_signals = ["fake gem", "gem scam", "fake gems", "gem shop scam", "gem store scam", "overpriced gem", "ruby scam", "sapphire scam", "moonstone scam", "pushed into a gem shop", "forced into a gem shop", "fake jewel", "fake stones", "gem fraud"]
        if not any(sig in text for sig in gem_signals):
            if any(k in text for k in ["overpriced", "commercial", "greedy", "not worth", "ripoff"]):
                return "Price Gouging"
            return "general_safety"

    # 4. Disambiguate Tuk-Tuk Overcharging
    if st_str in ["tuk_tuk_scam", "Tuk-Tuk Overcharging", "Tuk Tuk Scam", "overcharging", "Price Gouging"]:
        fare_signals = [
            "overcharg", "fare", "meter", "no meter", "charged", "exorbitant", "extort",
            "demanded more", "price for ride", "driver lied", "driver scammed", "refused to turn on",
            "metered", "double price", "triple price", "rip off", "ripoff", "took long route",
            "detour to shop", "tuk tuk driver", "tuktuk driver", "trishaw driver", "overpriced tuk"
        ]
        has_fare_signal = any(sig in text for sig in fare_signals)
        if not has_fare_signal:
            if any(k in text for k in ["free guide", "holy men", "panhandle", "donation", "snake-charmer", "shoe storage", "shoe keeper", "temple guide", "ticket office", "ticket gate", "grifter", "con", "hustling"]):
                return "fake_guide"
            elif any(k in text for k in ["commission", "spice garden", "herb garden", "tea factory", "shop", "bought"]):
                return "commission_shop"
            elif any(k in text for k in ["theft", "stole", "pickpocket", "snatch", "robbery"]):
                return "theft"
            elif any(k in text for k in ["over-commercialized", "overpriced", "greedy", "not worth"]):
                return "Price Gouging"
            else:
                return "general_safety"

    # 5. Disambiguate Fake / Unlicensed Guide Scam
    if st_str in ["fake_guide", "Unlicensed Guide Scam", "Fake Guide", "unlicensed_guide"]:
        guide_signals = [
            "fake guide", "unlicensed guide", "touts", "tout", "pose as guide", "posing as official",
            "demanded donation", "holy men", "panhandle", "snake-charmer", "shoe keeper scam",
            "temple hustle", "ticket hustle", "scam guide", "grifter", "con", "hustling"
        ]
        has_guide_signal = any(sig in text for sig in guide_signals)
        if not has_guide_signal:
            if any(k in text for k in ["over-commercialized", "overpriced", "commercial", "greedy", "expensive", "pricey", "not worth", "rip off", "ripoff"]):
                return "Price Gouging"
            elif any(k in text for k in ["theft", "stole", "pickpocket", "snatch"]):
                return "theft"
            else:
                return "general_safety"

    # 6. Disambiguate Commission Shop Trap
    if st_str in ["commission_shop", "Commission Shop Trap"]:
        if not any(k in text for k in ["commission", "spice", "herb garden", "tea factory", "shop", "store", "bought", "purchase", "force stop", "brought us to"]):
            return "general_safety"

    return st_str or "general_safety"

def is_irrelevant_noise(r):
    text = f"{r.get('title', '')} {r.get('content', '')}".lower()
    if not any(k in text for k in NON_TOURISM_NOISE):
        return False
    # Check if there's a tourism override — the article mentions tourists directly
    if any(k in text for k in TOURISM_OVERRIDE):
        return False
    return True

def clean_text_formatting(text: str) -> str:
    if not text:
        return ""
    txt = text.replace("&nbsp;", " ").replace("\xa0", " ").strip()
    for noise in [" - Tamil Guardian", " - Daily Mirror", " - Ada Derana", " - Sri Lanka", " - News First", " - Global Times", " - Print Edition"]:
        txt = txt.replace(noise, "")
    txt = txt.rstrip(" (").strip()
    return txt

def build_full_summary(title: str, content: str) -> str:
    c = clean_text_formatting(content)
    t = clean_text_formatting(title)
    if c and len(c) >= len(t):
        full = c
    else:
        full = t or "Incident report documented by local safety monitoring."
    
    if full and full[-1] not in ".!?":
        last_space = full.rfind(" ")
        if last_space > 80:
            full = full[:last_space] + "."
        else:
            full += "."
    return full

def build_snippet(full_text: str, max_chars: int = 240) -> str:
    if len(full_text) <= max_chars:
        return full_text
    cut = full_text[:max_chars]
    last_end = max(cut.rfind('.'), cut.rfind('!'), cut.rfind('?'))
    if last_end > 90:
        return cut[:last_end + 1]
    last_space = cut.rfind(' ')
    if last_space > 0:
        return cut[:last_space] + "..."
    return cut + "..."

# ── User-friendly source mapper (fuzzy matcher) ──────────────────────────
def get_human_source_info(raw_src: str):
    s = (raw_src or "").lower()
    if "fcdo" in s or "state_dept" in s or "dfat" in s or "sltda" in s or "official" in s:
        return ("Official Gov Advisory", "🏛️ Official Government Advisory", 1.00)
    if "derana" in s:
        return ("Ada Derana News", "🏛️ Tier 1 Verified News", 0.95)
    if "dailymirror" in s or "daily_mirror" in s or "daily mirror" in s:
        return ("Daily Mirror LK", "🏛️ Tier 1 Verified News", 0.95)
    if "newsfirst" in s or "news_first" in s or "news first" in s:
        return ("News First LK", "🏛️ Tier 1 Verified News", 0.95)
    if "google_news" in s or "google news" in s or "db_google_news" in s:
        return ("Google News", "🏛️ Tier 1 Verified News", 0.90)
    if "newswire" in s:
        return ("NewsWire LK", "🏛️ Tier 1 Verified News", 0.90)
    if "sundaytimes" in s or "sunday times" in s:
        return ("Sunday Times LK", "🏛️ Tier 1 Verified News", 0.95)
    if "ceylon" in s:
        return ("Ceylon Today", "🏛️ Tier 1 Verified News", 0.90)
    if "hirunews" in s or "hiru" in s:
        return ("Hiru News", "🏛️ Tier 1 Verified News", 0.90)
    if "theisland" in s or "island" in s:
        return ("The Island LK", "🏛️ Tier 1 Verified News", 0.90)
    if "themorning" in s or "morning" in s:
        return ("The Morning LK", "🏛️ Tier 1 Verified News", 0.90)
    if "news" in s:
        return ("Verified News Outlet", "🏛️ Tier 1 Verified News", 0.88)
    if "tripadvisor" in s:
        return ("TripAdvisor Reviews", "🟢 Verified Traveler Reviews", 0.70)
    if "google_maps" in s or "google maps" in s:
        return ("Google Maps Reviews", "📍 Location-Verified Reviews", 0.65)
    if "destination" in s or "canonical" in s or "reviews.csv" in s:
        return ("Verified Destination Registry", "📍 Location-Verified Reviews", 0.75)
    if "youtube" in s or "youtu.be" in s:
        return ("YouTube Travel Vlogs", "🎥 Verified Video Evidence", 0.65)
    if "reddit" in s:
        return ("Reddit Travel Community", "💬 Public Community Discussion", 0.40)
    return (raw_src.replace("_", " ").replace("archive", "").strip().title() or "User Incident Report", "💬 Public Community Discussion", 0.45)

def detect_publisher_info(raw_src: str, title: str, content: str):
    text_combo = f"{title or ''} {content or ''} {raw_src or ''}".lower()
    if "tamil guardian" in text_combo or "tamilguardian" in text_combo:
        return ("Tamil Guardian", "🏛️ Tier 1 Verified News", 0.95)
    if "ada derana" in text_combo or "adaderana" in text_combo or "derana" in text_combo:
        return ("Ada Derana News", "🏛️ Tier 1 Verified News", 0.95)
    if "daily mirror" in text_combo or "dailymirror" in text_combo:
        return ("Daily Mirror LK", "🏛️ Tier 1 Verified News", 0.95)
    if "news first" in text_combo or "newsfirst" in text_combo:
        return ("News First LK", "🏛️ Tier 1 Verified News", 0.95)
    if "newswire" in text_combo:
        return ("NewsWire LK", "🏛️ Tier 1 Verified News", 0.90)
    if "global times" in text_combo or "globaltimes" in text_combo:
        return ("Global Times", "🏛️ Tier 1 Verified News", 0.90)
    if "sunday times" in text_combo or "sundaytimes" in text_combo:
        return ("Sunday Times LK", "🏛️ Tier 1 Verified News", 0.95)
    if "ceylon today" in text_combo or "ceylontoday" in text_combo:
        return ("Ceylon Today", "🏛️ Tier 1 Verified News", 0.90)
    if "hiru news" in text_combo or "hirunews" in text_combo:
        return ("Hiru News", "🏛️ Tier 1 Verified News", 0.90)
    if "the island" in text_combo or "theisland" in text_combo:
        return ("The Island LK", "🏛️ Tier 1 Verified News", 0.90)
    if "the morning" in text_combo or "themorning" in text_combo:
        return ("The Morning LK", "🏛️ Tier 1 Verified News", 0.90)
    if "fcdo" in text_combo or "state_dept" in text_combo or "dfat" in text_combo or "sltda" in text_combo:
        return ("Official Gov Advisory", "🏛️ Official Government Advisory", 1.00)
    if "youtube" in text_combo or "youtu.be" in text_combo:
        return ("YouTube Travel Vlogs", "🎥 Verified Video Evidence", 0.65)
    if "tripadvisor" in text_combo:
        return ("TripAdvisor Reviews", "🟢 Verified Traveler Reviews", 0.70)
    if "google maps" in text_combo or "google_maps" in text_combo:
        return ("Google Maps Reviews", "📍 Location-Verified Reviews", 0.65)
    if "reddit" in text_combo:
        return ("Reddit Travel Community", "💬 Public Community Discussion", 0.40)
    
    return get_human_source_info(raw_src)

def resolve_direct_source_url(raw_url: str, title: str, content: str = None, location_name: str = None, source: str = None) -> str:
    if raw_url and str(raw_url).strip().startswith("http"):
        u = str(raw_url).strip()
        if "maps.google.com" not in u and "google.com/maps/place" not in u:
            return u

    clean_t = (title or "").strip()
    if clean_t.startswith("Review:"):
        clean_t = clean_t.replace("Review:", "").strip()

    # Extract clean concise headline snippet
    headline = clean_t.split(" - ")[0].split(". ")[0].strip()[:90]

    combo = f"{source or ''} {title or ''} {content or ''}".lower()
    matched_domain = None
    for k, domain in DOMAIN_MAP.items():
        if k in combo:
            matched_domain = domain
            break

    if matched_domain and headline and len(headline) > 5 and headline.lower() != (location_name or "").lower():
        query = f'site:{matched_domain} "{headline}"'
        return f"https://www.google.com/search?q={quote_plus(query)}&btnI=1"
    elif headline and len(headline) > 5 and headline.lower() != (location_name or "").lower() and headline != "Safety Incident Report":
        query = f'"{headline}" {location_name or ""} Sri Lanka'
        return f"https://www.google.com/search?q={quote_plus(query)}&btnI=1"
    elif content and len(str(content).strip()) > 10:
        c_snip = str(content).strip().split(". ")[0][:80]
        query = f'"{c_snip}" {location_name or ""} Sri Lanka'
        return f"https://www.google.com/search?q={quote_plus(query)}&btnI=1"
    else:
        query = f"{location_name or 'Sri Lanka'} travel review"
        return f"https://www.google.com/search?q={quote_plus(query)}"

def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance between two points on Earth in kilometers."""
    R = 6371.0  # Earth's radius in km
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


class SafetyIntelligenceEngine:
    """
    Computes safety decisions for any GPS coordinate using IDW spatial
    interpolation across the entire report database.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "safety_heatmap.db"
            )
        self.db_path = db_path

    def assess(self, lat: float, lng: float, radius_km: float = 15.0, sort_by: str = "credibility") -> dict:
        """
        Main entry point: assess safety for a given coordinate.

        Uses IDW interpolation to compute a composite safety score from
        all reports within `radius_km`, weighted by:
          - 1/distance^2 (spatial decay)
          - source_weight (credibility tier)
          - temporal decay (newer = more weight)
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Bounding box filter for fast SQL pre-filtering (rough ~1 degree ≈ 111km)
        deg_offset = radius_km / 111.0
        cur.execute("""
            SELECT id, source, source_weight, title, content, url,
                   latitude, longitude, location_name,
                   scam_type, risk_level, is_scam, created_at
            FROM reports
            WHERE latitude BETWEEN ? AND ?
              AND longitude BETWEEN ? AND ?
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
        """, (
            lat - deg_offset, lat + deg_offset,
            lng - deg_offset, lng + deg_offset,
        ))

        rows = cur.fetchall()
        conn.close()

        # Compute precise distances, filter to exact radius, and exclude non-tourism noise
        nearby = []
        for row in rows:
            dist = haversine_km(lat, lng, row["latitude"], row["longitude"])
            if dist <= radius_km:
                item = {
                    "id": row["id"],
                    "source": row["source"],
                    "source_weight": row["source_weight"] or 0.35,
                    "title": row["title"],
                    "content": row["content"] or row["title"] or "",
                    "url": row["url"],
                    "latitude": row["latitude"],
                    "longitude": row["longitude"],
                    "location_name": row["location_name"],
                    "scam_type": row["scam_type"],
                    "risk_level": row["risk_level"] or 1,
                    "is_scam": bool(row["is_scam"]),
                    "created_at": row["created_at"],
                    "distance_km": round(dist, 2),
                }
                if not is_irrelevant_noise(item):
                    nearby.append(item)

        if not nearby:
            # Expand search to find nearest data at any distance
            return self._assess_no_data(lat, lng)

        return self._compute_assessment(lat, lng, nearby, sort_by=sort_by)

    def _compute_assessment(self, lat: float, lng: float, nearby: list, sort_by: str = "credibility") -> dict:
        """Compute the full composite safety assessment."""
        now = datetime.now(timezone.utc)
        DECAY_LAMBDA = 0.00385  # Half-life = 180 days

        # ── IDW-weighted aggregation ──────────────────────────────────────────
        total_weight = 0.0
        weighted_risk_sum = 0.0
        weighted_scam_sum = 0.0

        scam_types = Counter()
        sources = Counter()
        scam_reports = []
        closest_incidents = []

        for r in nearby:
            dist = max(r["distance_km"], 0.1)  # Avoid division by zero
            spatial_weight = 1.0 / (dist ** 2)  # IDW: 1/d^2

            # Source credibility weight
            source_weight = r["source_weight"]

            # Temporal decay
            try:
                created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                days_ago = max(0, (now - created).days)
            except (ValueError, TypeError, AttributeError):
                days_ago = 365
            temporal_weight = math.exp(-DECAY_LAMBDA * days_ago)

            # Combined weight
            combined = spatial_weight * source_weight * temporal_weight
            total_weight += combined

            # Track scam types and sources
            raw_st = r.get("scam_type")
            refined_st = "general_safety"
            if raw_st:
                st_str = str(raw_st).strip()
                if st_str.lower() not in ("nan", "none", "null", "safe", "") and st_str not in ("Unsafe Area", "General Scam"):
                    refined_st = refine_scam_type(r.get("title"), r.get("content"), st_str)
                    disp_st = SCAM_DISPLAY_NAMES.get(refined_st, refined_st.replace("_", " ").title())
                    if disp_st not in ("General Tourist Safety", "Verified Safe Area"):
                        scam_types[disp_st] += 1

            # Determine whether this is an active scam (excluding general safety / positive reviews)
            is_active_scam = bool(r["is_scam"]) and refined_st not in ("general_safety", "safe", "Verified Safe Area")

            # Accumulate weighted risk and scam ratio
            weighted_risk_sum += (r["risk_level"] / 3.0) * combined
            weighted_scam_sum += (1.0 if is_active_scam else 0.0) * combined
            sources[r["source"]] += 1

            if is_active_scam:
                scam_reports.append(r)

        # ── Composite Score ───────────────────────────────────────────────────
        if total_weight == 0 or len(nearby) == 0:
            return self._assess_no_data(lat, lng)

        # Component scores (0.0 to 1.0)
        scam_ratio = weighted_scam_sum / total_weight
        severity_index = weighted_risk_sum / total_weight

        # Scam diversity penalty: many different scam types = systemic problem
        unique_scam_types = len(scam_types)
        diversity_penalty = min(unique_scam_types / 5.0, 1.0)  # Cap at 5 types

        # Source credibility factor: higher if Tier 1 sources confirm the risk
        tier1_sources = {"adaderana", "daily_mirror", "newsfirst", "google_news",
                         "newswire_lk", "ceylon_today", "sundaytimes"}
        tier1_count = sum(1 for r in nearby if r["source"] in tier1_sources and r["is_scam"])
        credibility_factor = min(tier1_count / 3.0, 1.0)

        # Temporal recency: how recent are the scam reports
        recent_scams = sum(1 for r in scam_reports
                          if r.get("created_at") and self._days_ago(r["created_at"]) < 90)
        recency_factor = min(recent_scams / 5.0, 1.0)

        # Final composite formula
        composite = (
            0.30 * scam_ratio +
            0.25 * severity_index +
            0.20 * diversity_penalty +
            0.15 * credibility_factor +
            0.10 * recency_factor
        )
        composite = round(min(max(composite, 0.0), 1.0), 4)

        # ── Safety Verdict ────────────────────────────────────────────────────
        if len(nearby) < 3:
            conf_level = "Low (Preliminary Data)"
        elif len(nearby) >= 10:
            conf_level = "High"
        else:
            conf_level = "Medium"

        if composite >= 0.60:
            # Require at least 3 supporting reports to declare confirmed HIGH RISK
            if len(nearby) < 3:
                verdict = "MODERATE RISK"
                verdict_color = "orange"
                confidence = "Low (Single Incident Warning)"
            else:
                verdict = "HIGH RISK"
                verdict_color = "red"
                confidence = conf_level
        elif composite >= 0.35:
            verdict = "MODERATE RISK"
            verdict_color = "orange"
            confidence = conf_level
        elif composite >= 0.15:
            verdict = "LOW RISK"
            verdict_color = "yellow"
            confidence = conf_level
        else:
            verdict = "SAFE"
            verdict_color = "green"
            confidence = conf_level

        # ── Safety Tips ───────────────────────────────────────────────────────
        tips = set()
        top_scam_types = scam_types.most_common(3)
        for stype, _ in top_scam_types:
            stype_tips = SCAM_SAFETY_TIPS.get(stype, [])
            if not stype_tips:
                # Try finding mapped key from SCAM_DISPLAY_NAMES
                stype_tips = SCAM_SAFETY_TIPS.get(SCAM_DISPLAY_NAMES.get(stype, ""), [])
            for tip in stype_tips[:2]:
                tips.add(tip)

        if not tips:
            if verdict == "HIGH RISK":
                tips = set(SCAM_SAFETY_TIPS["high_risk"])
            elif verdict == "MODERATE RISK":
                tips = set(SCAM_SAFETY_TIPS["moderate_risk"])
            else:
                tips = set(SCAM_SAFETY_TIPS["safe"][:2])
        tips.update(GENERAL_TIPS[:2])

        # Select incidents to display (filtering out non-tourism noise)
        base_reports = scam_reports if scam_reports else nearby
        relevant = [r for r in base_reports if not is_irrelevant_noise(r)]
        reports_for_incidents = relevant if relevant else base_reports

        for r in reports_for_incidents:
            info = detect_publisher_info(r["source"], r.get("title", ""), r.get("content", ""))
            # Boost genuine tourist safety reports
            text_lower = f"{r.get('title', '')} {r.get('content', '')}".lower()
            tourist_relevance = 1.2 if any(w in text_lower for w in ["tourist", "travel", "scam", "robbery", "theft", "harass", "attack", "police", "warning", "tuk tuk", "gem", "safari"]) else 1.0
            r["source_weight"] = max(r.get("source_weight") or 0.35, info[2]) * tourist_relevance

        # Sort incidents based on requested sort_by parameter
        if sort_by == "nearest":
            reports_for_incidents.sort(key=lambda r: (r["distance_km"], -r["source_weight"]))
        elif sort_by == "risk":
            reports_for_incidents.sort(key=lambda r: (-(r["risk_level"] or 1), -r["source_weight"], r["distance_km"]))
        else: # default: credibility
            reports_for_incidents.sort(key=lambda r: (-r["source_weight"], r["distance_km"]))

        incidents = []
        seen_fingerprints = set()
        for r in reports_for_incidents:
            if len(incidents) >= 10:
                break

            full_sum = build_full_summary(r["title"], r["content"])
            # Create a normalized content fingerprint (alphanumeric only) to prevent duplicate display
            raw_fp_text = (r.get("content") or r.get("title") or "").lower()
            fingerprint = re.sub(r'[^a-z0-9]', '', raw_fp_text)[:80]
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)

            src_info = detect_publisher_info(r["source"], r.get("title", ""), r.get("content", ""))
            raw_title = clean_text_formatting(r["title"] or "")
            if raw_title.startswith("Review:"):
                raw_title = raw_title.replace("Review:", "").strip()
            if raw_title.startswith("Google Maps:"):
                raw_title = raw_title.replace("Google Maps:", "").strip()
            
            clean_t = raw_title.split(" - ")[0].strip() if " - " in raw_title else raw_title
            raw_content = (r.get("content") or "").strip()
            
            if not clean_t or len(clean_t) < 5 or clean_t.lower() in ["sri lanka", "review", "nan", "none", "null"]:
                if raw_content and len(raw_content) > 5:
                    first_sentence = raw_content.split(". ")[0].split("\n")[0].strip()
                    if len(first_sentence) > 80:
                        first_sentence = first_sentence[:77] + "..."
                    clean_t = first_sentence[0].upper() + first_sentence[1:]
                else:
                    clean_t = f"Traveler Review — {r.get('location_name') or 'Sri Lanka'}"

            raw_scam = r.get("scam_type")
            if not raw_scam or str(raw_scam).strip().lower() in ["nan", "none", "null", "general scam"]:
                scam_code = "general_safety"
                scam_disp = "General Tourist Safety"
            else:
                scam_code = refine_scam_type(r.get("title"), r.get("content"), str(raw_scam).strip())
                scam_disp = SCAM_DISPLAY_NAMES.get(scam_code, scam_code.replace("_", " ").title())

            if raw_content:
                clean_stem = clean_t.rstrip(".").rstrip("..").rstrip("...")
                if raw_content.startswith(clean_stem):
                    remainder = raw_content[len(clean_stem):].lstrip(". ").strip()
                    snip = build_snippet(remainder if len(remainder) > 15 else raw_content, max_chars=220)
                else:
                    snip = build_snippet(raw_content, max_chars=220)
            else:
                snip = build_snippet(full_sum, max_chars=220)

            verified_url = resolve_direct_source_url(r.get("url"), clean_t, full_sum, r.get("location_name"), source=r.get("source"))

            incidents.append({
                "title": clean_t,
                "scam_type": scam_code,
                "scam_type_display": scam_disp,
                "risk_level": r["risk_level"],
                "source": r["source"],
                "source_display": src_info[0],
                "credibility_label": src_info[1],
                "credibility_score": src_info[2],
                "distance_km": r["distance_km"],
                "location_name": r["location_name"],
                "url": verified_url,
                "content_snippet": snip,
                "full_summary": full_sum,
            })

        # ── Source Breakdown (User-Friendly Labels) ───────────────────────────
        source_breakdown = []
        for src, count in sources.most_common(8):
            src_info = get_human_source_info(src)
            source_breakdown.append({
                "source": src_info[0],
                "count": count,
                "tier": src_info[1],
                "credibility_score": src_info[2],
            })

        # ── Authority Report Data ─────────────────────────────────────────────
        authority_report = None
        if composite >= 0.35 and scam_reports:
            authority_report = {
                "coordinates": {"lat": lat, "lng": lng},
                "risk_level": verdict,
                "composite_score": composite,
                "total_incidents": len(scam_reports),
                "scam_types": dict(scam_types.most_common(5)),
                "verified_sources": tier1_count,
                "recommended_action": "Increased patrol and tourist advisory recommended"
                    if composite >= 0.60 else "Monitor situation and issue awareness bulletin",
                "report_format": "SLTDA/Tourism Police Compatible",
            }

        return {
            "query": {"lat": lat, "lng": lng},
            "verdict": verdict,
            "verdict_color": verdict_color,
            "composite_score": composite,
            "confidence": confidence,
            "total_reports_analyzed": len(nearby),
            "scam_reports_found": len(scam_reports),
            "search_radius_km": 15.0,

            # Score components (for transparency)
            "score_breakdown": {
                "scam_ratio": round(scam_ratio, 4),
                "severity_index": round(severity_index, 4),
                "diversity_penalty": round(diversity_penalty, 4),
                "credibility_factor": round(credibility_factor, 4),
                "recency_factor": round(recency_factor, 4),
            },

            "top_scam_types": [{"type": t, "count": c} for t, c in top_scam_types],
            "safety_tips": list(tips),
            "nearby_incidents": incidents,
            "source_breakdown": source_breakdown,
            "authority_report": authority_report,
            "district_context": self._get_district_context(lat, lng),
        }

    def _assess_no_data(self, lat: float, lng: float) -> dict:
        """Return assessment when no data exists within search radius."""
        import re
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("""
            SELECT location_name, latitude, longitude, scam_type, risk_level, is_scam
            FROM reports
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND location_name IS NOT NULL AND location_name != ''
        """)
        all_rows = cur.fetchall()
        conn.close()

        # Deduplicate places by normalized base name and spatial distance (< 3.0km)
        unique_places = []
        for r in all_rows:
            loc_name, rlat, rlon, stype, rlevel, is_scam = r
            clean_name = str(loc_name).strip()
            if not clean_name or clean_name.lower() in ["sri lanka", "review", "nan", "none", "null", "unknown"]:
                continue

            base_name = clean_name.split(",")[0].strip()
            norm_name = re.sub(r'[^a-z0-9]', '', base_name.lower())
            if not norm_name:
                continue

            dist = haversine_km(lat, lng, rlat, rlon)

            # Check if this place is already represented in unique_places (by name or within 3km)
            duplicate_idx = None
            for idx, existing in enumerate(unique_places):
                ex_base = existing["location_name"].split(",")[0].strip()
                ex_norm = re.sub(r'[^a-z0-9]', '', ex_base.lower())
                spatial_dup = haversine_km(rlat, rlon, existing["lat"], existing["lon"]) < 3.0
                name_dup = (norm_name == ex_norm) or (len(norm_name) > 4 and len(ex_norm) > 4 and (norm_name in ex_norm or ex_norm in norm_name))

                if spatial_dup or name_dup:
                    duplicate_idx = idx
                    break

            if duplicate_idx is not None:
                if dist < unique_places[duplicate_idx]["distance_km"]:
                    unique_places[duplicate_idx] = {
                        "location_name": base_name,
                        "distance_km": round(dist, 1),
                        "scam_type": stype,
                        "risk_level": rlevel or 1,
                        "is_scam": bool(is_scam),
                        "lat": rlat,
                        "lon": rlon,
                    }
            else:
                unique_places.append({
                    "location_name": base_name,
                    "distance_km": round(dist, 1),
                    "scam_type": stype,
                    "risk_level": rlevel or 1,
                    "is_scam": bool(is_scam),
                    "lat": rlat,
                    "lon": rlon,
                })

        unique_places.sort(key=lambda p: p["distance_km"])
        nearest_places = [
            {
                "location_name": p["location_name"],
                "distance_km": p["distance_km"],
                "scam_type": p["scam_type"],
                "risk_level": p["risk_level"],
                "is_scam": p["is_scam"],
            }
            for p in unique_places[:5]
        ]

        return {
            "query": {"lat": lat, "lng": lng},
            "verdict": "INSUFFICIENT DATA",
            "verdict_color": "gray",
            "composite_score": None,
            "confidence": "Low",
            "total_reports_analyzed": 0,
            "scam_reports_found": 0,
            "search_radius_km": 15.0,
            "score_breakdown": {
                "scam_ratio": 0, "severity_index": 0,
                "diversity_penalty": 0, "credibility_factor": 0,
                "recency_factor": 0,
            },
            "top_scam_types": [],
            "safety_tips": GENERAL_TIPS,
            "nearby_incidents": [],
            "source_breakdown": [],
            "authority_report": None,
            "nearest_known_places": nearest_places,
            "district_context": self._get_district_context(lat, lng),
            "message": f"No incident data within 15km search radius. Nearest known location: {nearest_places[0]['location_name']} ({nearest_places[0]['distance_km']}km away)." if nearest_places else "No incident data available for this region.",
        }

    @staticmethod
    def _days_ago(date_str: str) -> int:
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return max(0, (datetime.now(timezone.utc) - dt).days)
        except Exception:
            return 365


    def _get_district_context(self, lat: float, lng: float) -> dict:
        """Helper to fetch macro-district context for a given coordinate."""
        try:
            from app.core.district_engine import get_boundary_index, score_all_districts
            from app.db.session import SessionLocal
            from app.db.models import Report
            
            idx = get_boundary_index()
            dist_name = idx.locate(lat, lng)
            if not dist_name:
                return None

            db = SessionLocal()
            reports = db.query(Report).filter(Report.latitude.isnot(None), Report.longitude.isnot(None)).all()
            db.close()

            scores = score_all_districts(reports)
            s = scores.get(dist_name)
            if not s:
                return {"district_name": dist_name, "risk_tier": "insufficient_data"}

            return {
                "district_name": dist_name,
                "risk_tier": s["risk_tier"],
                "confidence": s["confidence"],
                "report_count": s["report_count"],
                "scam_report_count": s["scam_report_count"],
                "exposure_status": s["exposure_status"],
            }
        except Exception:
            return None


# Singleton instance
_engine = None

def get_engine() -> SafetyIntelligenceEngine:
    global _engine
    if _engine is None:
        _engine = SafetyIntelligenceEngine()
    return _engine
