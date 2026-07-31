"""
Strict Relevance Filter — SafeTravel LK Research Engine
IT22629180

Every report MUST pass this filter before being stored.
Criteria:
  1. Must be TOURISM context (the person is a tourist/traveler in Sri Lanka)
  2. Must contain a NEGATIVE EXPERIENCE signal (scam, danger, warning, loss)
"""

# ── 1. TOURISM CONTEXT SIGNALS ─────────────────────────────────────────────
TOURIST_CONTEXT = [
    "tourist", "tourists", "tourism", "traveler", "traveller",
    "traveling", "travelling", "travel to", "visited", "visiting",
    "backpacker", "backpacking", "solo travel", "solo trip",
    "vacation", "holiday", "trip to sri lanka", "trip to colombo",
    "hostel", "guesthouse", "hotel in", "stayed at",
    "tuk tuk", "tuk-tuk", "three-wheeler",
    "safari", "surf", "diving", "snorkeling",
    "sightseeing", "attraction", "itinerary", "day trip", 
    "tour guide", "tour operator", "cultural triangle",
    "sigiriya", "kandy", "ella", "galle fort", "mirissa", 
    "arugam", "negombo", "hikkaduwa", "unawatuna", "nuwara eliya",
]

# ── 2. NEGATIVE EXPERIENCE SIGNALS ─────────────────────────────────────────
NEGATIVE_SIGNALS = [
    "scam", "scammed", "scamming", "fraud", "fraudulent", "con",
    "ripped off", "rip off", "ripoff", "swindle", "swindled",
    "fake", "counterfeit", "forged", "bogus",
    "overcharged", "overcharge", "overpriced", "charged extra",
    "tourist price", "double price", "inflated price",
    "unsafe", "dangerous", "danger", "threat", "threatened",
    "harassed", "harassment", "stalked", "followed", "uncomfortable",
    "attacked", "assault", "mugged", "robbery", "robbed",
    "stolen", "theft", "pickpocket", "pickpocketed",
    "lost money", "lost my money", "money gone", "wasted money",
    "refund", "no refund", "wouldn't refund",
    "cheated", "deceived", "lied", "false advertising",
    "refused meter", "no meter", "wrong route", "took the long way",
    "overcharged taxi", "airport scam",
    "different room", "bait and switch", "not as advertised",
    "dirty", "cockroach", "bed bugs",
    "food poisoning", "sick", "drugged", "spiked",
    "injury", "accident", "hospital",
    "warning", "avoid", "beware", "watch out", "be careful",
    "don't trust", "do not trust", "stay away",
    "terrible", "awful", "nightmare", "worst", "horrible",
    "disgusting", "outrageous", "shocking",
    "bad", "sad", "unhappy", "regret", "disappoint", "poor", "issue", "problem", 
    "complain", "ruined", "ill", "police", "stray dog", "bitten", "rabies", 
    "delay", "cancel", "scary", "frighten", "creepy", "rude", "aggressive", "shout",
]

# ── 3. HARD EXCLUSION PATTERNS ─────────────────────────────────────────────
HARD_EXCLUSIONS = [
    "a/l exam", "o/l exam", "a/l result", "o/l result",
    "advanced level", "ordinary level", "university admission",
    "11.11 sale", "black friday", "buy now",
    "parliament", "president rajapaksa", "gotabaya", "ranil", "anura",
    "imf loan", "economic crisis", "protest", "riot", "tear gas", "curfew",
    "tamil eelam", "tamilawareness", "justicefor", "srilankapolitics",
    "general election", "presidential election", "cabinet", "minister",
    "supreme court", "high court", "arrested for murder", "drug bust",
    "heroin", "ganja", "cannabis", "smuggling",
    "kerala ganja", "underworld", "gang war", "shooting",
    "cricket match", "ipl", "lpl", "sports news",
    "dating", "relationship advice", "girlfriend", "boyfriend",
    "crypto", "bitcoin", "stock market", "nft",
    "hiring", "job opening", "vacancy", "apply now",
    "book your", "whatsapp link", "tour packages", "special offer",
    "safari jeep", "book now", "pre-book", "contact us for bookings",
    "whatsapp me", "affordable price", "our services", "dm for bookings",
    "online scam racket", "pyramid scam", "online fraud",
    "foreign nationals arrested", "foreigners arrested",
    "racket busted", "arrested for online", "arrested for fraud",
    "nationals arrested", "chinese nationals", "indian nationals",
    "suspects arrested", "suspects detained",
    "cyber fraud ring", "call center scam", "investment scam ring",
    "online gambling", "money laundering", "financial crime",
    "police raid", "special raid", "cid arrested",
    "residing in", "on visa", "overstaying", "illegal stay",
    # ── GOVERNMENT COMMISSIONS & DIPLOMATIC NOISE ──
    "high commissioner", "high commission", "deputy high commissioner",
    "land reforms commission", "elections commissioner", "elections commission",
    "presidential commission", "bribery commission", "human rights commission",
    "police commission", "cabinet sub committee", "french embassy",
    "un high commissioner", "charity commission", "commission to investigate",
    "commissioner of", "lrc director", "election official", "polling booth",
    "ballot paper", "annulled as a group", "district secretary", "local council",
    
    # ── DISASTER & WEATHER NEWS (NON-SCAM) ──
    "disaster management", "affected by floods", "heavy showers", "met dept",
    "meteorology", "sluice gates", "evacuation drills", "river levels",
    "dmc reported", "disaster management center", "disaster management centre",
    "port agreement", "haj pilgrimage",
    
    # ── GLOBAL NEWS (Other countries) ──
    "thailand", "pattaya", "bangkok", "phuket", "bali", "indonesia",
    "europe", "italy", "rome", "paris", "france", "spain", "barcelona", "madrid",
    "london", "united kingdom", "british", "tenerife", "mallorca", "greece", "athens",
    "prague", "shanghai", "vietnam", "cambodia", "philippines",
    "dubai", "kuwait", "qatar", "saudi arabia", "oman", "middle east",
    "employment", "job racket", "domestic work", "work visa", "sending women",
]


def passes_strict_filter(title: str, content: str) -> bool:
    """
    Returns True only if the post is:
      - Explicitly about SRI LANKA (Geographic gate)
      - About a TOURIST context (context check)
      - Describing a NEGATIVE EXPERIENCE (signal check)
      - Not on the hard exclusion list
    """
    text = f"{title} {content}".lower().strip()

    # 1. Hard exclusion check
    # Check for specific words to avoid partial matches (e.g. 'uk' in 'tuk-tuk')
    words = text.split()
    if any(excl in text for excl in HARD_EXCLUSIONS):
        # Additional check for short exclusions to ensure they aren't part of other words
        for excl in HARD_EXCLUSIONS:
            if excl in text:
                # If exclusion is short (like 'uk'), only reject if it's a whole word or clear separator
                if len(excl) <= 3:
                    if f" {excl} " in f" {text} " or text.startswith(excl) or text.endswith(excl):
                        return False
                    continue
                return False

    # 2. GEOGRAPHIC GATE: Must explicitly mention Sri Lanka or its major cities
    lanka_terms = [
        "sri lanka", "lankan", "lanka", "colombo", "kandy", "galle", "ella", 
        "sigiriya", "negombo", "mirissa", "hikkaduwa", "unawatuna", 
        "nuwara eliya", "arugam", "bentota", "jaffna", "dambulla", 
        "polonnaruwa", "trincomalee"
    ]
    if not any(term in text for term in lanka_terms):
        return False

    # 3. TOURISM CONTEXT: Require strong signals or infra + location
    strong_tourist = [
        "tourist", "tourists", "tourism", "traveler", "traveller",
        "traveling", "travelling", "travel to", "backpacker", "backpacking",
        "solo travel", "solo trip", "vacation", "holiday",
        "trip to sri lanka", "trip to colombo", "visited sri lanka",
        "visiting sri lanka",
    ]
    infrastructure = [
        "hostel", "guesthouse", "hotel in", "stayed at",
        "tuk tuk", "tuk-tuk", "three-wheeler", "safari",
        "tour guide", "tour operator", "sightseeing", "itinerary",
        "day trip", "cultural triangle",
    ]
    locations = [
        "colombo", "sigiriya", "kandy", "ella", "galle fort", "mirissa",
        "arugam", "negombo", "hikkaduwa", "unawatuna", "nuwara eliya",
    ]

    has_strong = any(kw in text for kw in strong_tourist)
    has_infra = any(kw in text for kw in infrastructure)
    has_location = any(kw in text for kw in locations)

    if not (has_strong or (has_infra and has_location)):
        return False

    # 4. NEGATIVE EXPERIENCE SIGNAL
    if not any(sig in text for sig in NEGATIVE_SIGNALS):
        return False

    return True
