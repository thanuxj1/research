"""
TravelLens LK -- central configuration.

Every domain decision in this project lives in this file:
  * which aspects (complaint categories) we recognise
  * which words signal each aspect
  * the minimum evidence thresholds before we display a number

Nothing else in the codebase hard-codes a keyword. If a supervisor asks
"how did you define cleanliness?", the answer is this file.
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"

RAW_REVIEWS_CSV = DATA_RAW / "reviews_raw.csv"
KAGGLE_FINAL_CSV = DATA_RAW / "reviews_final_kaggle.csv"   # stopword-stripped; baseline only
CLEAN_REVIEWS_CSV = DATA_PROCESSED / "reviews_clean.csv"
CLEANING_REPORT_JSON = REPORTS / "cleaning_report.json"

# --------------------------------------------------------------------------
# Cleaning thresholds
# --------------------------------------------------------------------------
# Reviews shorter than this carry no recoverable opinion ("nice place", "good").
# Chosen from the observed distribution: 17% of the corpus is <= 3 words and is
# dominated by 277x "nice place", 236x "good", 124x "nice".
MIN_WORDS = 4

# Google truncates long reviews with a horizontal ellipsis when the scraper did
# not click "read more". We KEEP these rows (the opening sentences are still
# usable) but flag them, so the thesis can report exactly how much text was lost
# and can re-run any analysis with them excluded.
TRUNCATION_MARKER = "…"

# --------------------------------------------------------------------------
# Evidence thresholds for the hierarchy
# --------------------------------------------------------------------------
# Below MIN_MENTIONS_DISPLAY we do not render an aspect node at all: three
# complaints is an anecdote, not a finding.
MIN_MENTIONS_DISPLAY = 5
# Between DISPLAY and CONFIDENT we render the node but mark it "low confidence".
MIN_MENTIONS_CONFIDENT = 15


@dataclass
class Aspect:
    """One complaint category, plus the evidence that identifies it."""
    key: str
    label: str
    description: str              # plain-English definition, quoted in the thesis
    triggers: List[str]           # regex fragments that mark the topic as present
    polarity_hint: str = "mixed"  # what this aspect usually looks like in the corpus

    def pattern(self) -> str:
        return "|".join(self.triggers)


# --------------------------------------------------------------------------
# The aspect taxonomy
#
# Six complaint aspects plus one positive "control" aspect (scenery). Scenery is
# included deliberately: it is the dominant POSITIVE theme in the corpus, so it
# lets the dashboard show praise alongside complaint, and it acts as a sanity
# check -- if the model ever labels scenery as mostly negative, the model is
# broken, not the data.
# --------------------------------------------------------------------------
ASPECTS: Dict[str, Aspect] = {
    "roads_access": Aspect(
        key="roads_access",
        label="Roads & Access",
        description=(
            "Getting to and moving around the site: road condition, distance, "
            "signage on the way, parking, public transport, difficulty of the "
            "walk or climb."
        ),
        triggers=[
            r"\broads?\b", r"\baccess(ible|ibility)?\b", r"\bpath(way)?s?\b",
            r"\btracks?\b", r"\bsteps?\b", r"\bclimb", r"\btrek", r"\bhik(e|ing)\b",
            r"\breach(ing)?\b", r"\bparking\b", r"\bbus\b", r"\btrain\b",
            r"\btuk.?tuk\b", r"\bjeep\b", r"\b4wd\b", r"\bfour wheel\b",
            r"\bdriv(e|ing)\b", r"\bwalk(ing)? (up|down|distance)\b",
            r"\bdifficult to (find|reach|access|get)\b", r"\bkm\b", r"\bkilomet",
        ],
        polarity_hint="most-complained aspect in the corpus",
    ),
    "facilities": Aspect(
        key="facilities",
        label="Facilities",
        description=(
            "Amenities provided at the site: toilets, changing rooms, food and "
            "drink, shops, seating, shelter, bins, signage, ticket counters, guides."
        ),
        triggers=[
            r"\btoilets?\b", r"\bwash ?rooms?\b", r"\brest ?rooms?\b",
            r"\bchanging room", r"\bshops?\b", r"\bfood\b", r"\brestaurants?\b",
            r"\bcanteen", r"\bstalls?\b", r"\bbins?\b", r"\bseat(ing|s)?\b",
            r"\bbench", r"\bshelter", r"\bsign ?(age|board)", r"\bticket (counter|office)\b",
            r"\bguides?\b", r"\bfacilit", r"\bamenit", r"\bwater tap\b",
        ],
    ),
    "cleanliness": Aspect(
        key="cleanliness",
        label="Cleanliness",
        description=(
            "Litter, waste and pollution at the site, including plastic and "
            "polythene, bad smells, and general upkeep."
        ),
        triggers=[
            r"\bgarbage\b", r"\blitter(ing|ed)?\b", r"\bdirty\b", r"\bfilthy\b",
            r"\bpollut", r"\bplastics?\b", r"\bpolythene\b", r"\brubbish\b",
            r"\bwaste\b", r"\bsmell(s|y|ing)?\b", r"\bunclean\b", r"\bmessy?\b",
            r"\bclean(liness|ed)?\b", r"\bjunk\b", r"\bbottles?\b",
            # Upkeep vocabulary was entirely missing, so "beautifully
            # maintained" and "the place is not maintained well" both fell
            # through. Recall was 0.500 before these were added. Found by
            # evaluating against a 36-positive cleanliness test set.
            r"\bmaintain(ed|ing|ance)?\b", r"\bupkeep\b", r"\bwell kept\b",
            r"\bcared for\b", r"\bneglect(ed|s)?\b", r"\btidy\b", r"\bneat\b",
            r"\bdust(y)?\b", r"\bmudd?y\b", r"\bhygien", r"\bsanitat",
        ],
        polarity_hint="thin at destination level; strongest as a district-level signal",
    ),
    "safety": Aspect(
        key="safety",
        label="Safety",
        description=(
            "Physical risk to the visitor: slippery ground, deep or fast water, "
            "drowning risk, falls, wildlife (monkeys, crocodiles, leeches), and "
            "explicit warnings addressed to other visitors."
        ),
        triggers=[
            r"\bdanger(ous)?\b", r"\bunsafe\b", r"\bslipper(y|ing)\b", r"\bslip\b",
            # "safe" and "safety" were missing, so every warning phrased as
            # "not safe to swim" fell through the lexicon entirely. Found by
            # evaluating against a 22-positive safety test set.
            r"\bsafe\b", r"\bsafety\b", r"\bprecaution",
            r"\baccidents?\b", r"\bdrown", r"\bcare ?ful\b",
            r"\brisky?\b", r"\bdeep\b", r"\bcurrents?\b", r"\bmonkeys?\b",
            r"\bleech", r"\bcrocodile", r"\bsnakes?\b", r"\bwild elephant",
            r"\bfell down\b", r"\bdied\b", r"\bdeaths?\b", r"\brescue\b",
        ],
        polarity_hint="rarest aspect; expect the weakest model score here",
    ),
    "price_value": Aspect(
        key="price_value",
        label="Price & Value",
        description=(
            "Entrance fees, parking charges, food prices, perceived value for "
            "money, and differential pricing between local and foreign visitors."
        ),
        triggers=[
            r"\bexpensive\b", r"\bover ?charg", r"\bscam", r"\bcheat", r"\brip.?off\b",
            r"\bticket price\b", r"\bentrance fee\b", r"\bentry fee\b", r"\badmission\b",
            r"\bcharges?\b", r"\bcosts?\b", r"\bvalue for money\b", r"\bmoney\b",
            r"\blkr\b", r"\brupees\b", r"\busd\b", r"\beuro", r"\bforeigner",
            r"\bprice", r"\bfees?\b",
            # Money verbs were missing entirely: "we had to pay 100 times more
            # than the Sri Lankans", "wanted a tip", "if you're on a budget"
            # all fell through. Recall was 0.571 without these.
            r"\bpay(s|ing|ment)?\b", r"\bpaid\b", r"\btips?\b", r"\bbudget\b",
            r"\bpurchase\b", r"\bfree\b", r"\bcheap",
            # NOT bare "worth". r"\bworth (it|the)\b" fired on "worth the drive",
            # "worth the visit", "all worth it" -- recommendations, not prices.
            # It caused every false positive the lexicon made on the price test
            # set. Restricted to explicit money contexts, precision went 0.706 -> 1.000.
            r"\bworth (the (money|price|cost|fee)|\d)",
        ],
        polarity_hint="foreign vs local pricing gap is a recurring theme",
    ),
    "crowd": Aspect(
        key="crowd",
        label="Crowding & Noise",
        description=(
            "How busy the site is, queues and noise levels, and conversely "
            "whether it is peaceful and quiet."
        ),
        triggers=[
            r"\bcrowd(ed|s|ing)?\b", r"\brush\b", r"\bnois(y|e)\b", r"\bqueue\b",
            r"\btoo many people\b", r"\bbusy\b", r"\bpeaceful\b", r"\bquiet\b",
            r"\bcalm\b", r"\bpacked\b",
        ],
    ),
    "scenery": Aspect(
        key="scenery",
        label="Scenery & Nature",
        description=(
            "The natural attraction itself: views, landscape, waterfalls, "
            "wildlife sightings, sunrise and sunset. Included as a positive "
            "control aspect -- it should score overwhelmingly positive."
        ),
        triggers=[
            r"\bviews?\b", r"\bscenic\b", r"\bscenery\b", r"\bbeautiful\b",
            r"\bstunning\b", r"\bbreathtaking\b", r"\bnature\b", r"\bnatural\b",
            r"\bwaterfalls?\b", r"\bsunset\b", r"\bsunrise\b", r"\blandscape\b",
            r"\bgorgeous\b", r"\bamazing\b", r"\bmist\b",
            # Flora, fauna and photography vocabulary was missing, so "diverse
            # wetland plants and bird", "the constant noises of birds" and
            # "admire and take photos" all fell through. Recall was 0.600
            # before these; 0.960 after. Measured on a 25-positive test set.
            r"\bphoto(s|graph(y|s)?|shoot)?\b", r"\badmire\b", r"\bpicturesque\b",
            r"\bpanoram", r"\bforests?\b", r"\bwildlife\b", r"\bbirds?\b",
            r"\bflowers?\b", r"\btrees?\b", r"\bplants?\b", r"\bfauna\b",
            r"\bflora\b", r"\bviewing (point|booth)", r"\bview ?point",
            # NOT "pretty" or "lovely": they are used as intensifiers ("pretty
            # busy", "lovely people") and each added a false positive.
        ],
        polarity_hint="positive control -- must come out positive or the model is wrong",
    ),
}

COMPLAINT_ASPECTS = [k for k in ASPECTS if k != "scenery"]

# --------------------------------------------------------------------------
# District name normalisation.
#
# The corpus spells Colombo in lowercase, misspells Kurunegala and Ratnapura,
# and treats Hatton and Kalmunai (both towns, not districts) as districts. We
# keep the original corpus label AND record the correct administrative district,
# so the thesis can state the discrepancy openly rather than silently inheriting
# the scraper's mistake.
# --------------------------------------------------------------------------
DISTRICT_CANON: Dict[str, str] = {
    "colombo": "Colombo",
    "Colombo": "Colombo",
    "Gampaha": "Gampaha",
    "Kalutara": "Kalutara",
    "Galle": "Galle",
    "Matara": "Matara",
    "Hambantota": "Hambantota",
    "Matale": "Matale",
    "Badulla": "Badulla",
    "Rathnapura": "Ratnapura",
    "Kurunagela": "Kurunegala",
    "Kalmunai": "Ampara",          # Kalmunai is a city in Ampara district
    "Hatton": "Nuwara Eliya",      # Hatton is a town in Nuwara Eliya district
}
