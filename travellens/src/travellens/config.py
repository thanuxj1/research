"""
LostinSriLanka -- central configuration.

Every domain decision in this project lives in this file:
  * which aspects (complaint categories) we recognise
  * which words signal each aspect
  * the minimum evidence thresholds before we display a number

Nothing else in the codebase hard-codes a keyword. If a supervisor asks
"how did you define cleanliness?", the answer is this file.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

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
# MEASURED, not chosen. These were 5 and 15 -- two numbers picked because they
# felt about right, guarding every rate the dashboard publishes. They are now
# set from reports/reliability.json (scripts/46_reliability.py), which splits
# each destination-aspect cell's opinions in half at random, scores each half
# on its own, and measures how well the two halves agree. Spearman-Brown
# corrected, averaged over 200 splits:
#
#     opinions   reliability   halves land apart by
#       2-9         0.462           26.0 pp
#      10-14        0.749           16.0 pp
#      15-19        0.754           14.3 pp
#      20-29        0.809           11.7 pp
#      30-49        0.826            9.3 pp
#      50-99        0.893            6.8 pp
#      100+         0.960            3.7 pp
#
# A permutation null -- the identical study with verdicts shuffled between
# cells -- returns -0.083, so the figures above are a property of the data and
# not of the procedure.
#
# Below MIN_MENTIONS_DISPLAY we do not render an aspect node at all. At 2-9
# opinions two halves of the SAME place disagree by 26 percentage points and
# reproduce each other at 0.46, which is close enough to a coin toss that
# publishing the rate would be publishing noise. The old threshold of 5 sat
# inside that band, so cells of 5-9 opinions were being shown.
MIN_MENTIONS_DISPLAY = 10
# Between DISPLAY and CONFIDENT we render the node but mark it "low confidence".
# 0.80 is the conventional floor for a confident group-level measure, and the
# per-band figures above first clear it at 20-29 -- not at 15, where the old
# threshold sat and reliability is 0.754.
MIN_MENTIONS_CONFIDENT = 20

# Review quotes are stored per DESTINATION. When the dashboard shows a
# district- or country-level aspect it has no quotes of its own, so it
# gathers them from the destinations driving that number. This caps how
# many it will show: a country-level aspect can span hundreds of
# destinations, and rendering all of them replaces "no evidence" with an
# unreadable wall of it. Lives here, with the other display thresholds,
# rather than in the template -- every number the dashboard renders should
# be traceable to this file.
MAX_GATHERED_QUOTES = 60

# A quote whose classifier confidence is below this is shown but marked. It
# is not hidden: filtering out the model's own uncertainty would make the
# evidence look more settled than it is, which is the opposite of what an
# examiner should be shown. 0.60 is where the corpus's own distribution
# turns -- median confidence is 0.75, and 21% of stored quotes fall below
# this line, so it separates a real tail rather than an arbitrary slice.
LOW_CONFIDENCE_QUOTE = 0.60


@dataclass
class Aspect:
    """One complaint category, plus the evidence that identifies it."""
    key: str
    label: str
    description: str              # plain-English definition, quoted in the thesis
    triggers: List[str]           # regex fragments that mark the topic as present
    # Triggers that only count when a second pattern also appears in the same
    # segment. Some words name a topic only in context: a monkey is wildlife
    # until it snatches something, and "the current lighthouse" is not a rip
    # current. Measured per-trigger against the gold set, these three were
    # responsible for most of safety's false positives:
    #     monkeys    fires 13, wrong 11  (precision 0.15)
    #     crocodile  fires  5, wrong  4  (precision 0.20)
    #     currents   fires  6, wrong  4  (precision 0.33)
    # Every one of those errors was a safari sighting or the adjective
    # "current" -- not a hazard. Deleting the words would also lose the real
    # warnings, so they are gated instead of dropped.
    gated: List[Tuple[str, str]] = field(default_factory=list)
    # Patterns that veto the aspect outright, whatever else matched. Gating
    # is not enough for every case: a gated trigger still fires if its cue
    # appears anywhere in the same segment, so "a clean litter free
    # environment" in a review that also mentions the entrance fee would
    # still be tagged price_value. Some phrases simply never mean the
    # aspect -- "litter free", "smoke free", "hassle free" are compound
    # adjectives where "free" has no monetary sense at all -- and those
    # need a veto rather than a condition.
    blocked: List[str] = field(default_factory=list)
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
# Context cues for gated triggers (see Aspect.gated).
#
# RISK_CUE: the words that turn an animal from a sighting into a hazard. Drawn
# from the false positives themselves -- every wrongly tagged monkey/crocodile
# row in the gold set was a safari list ("we saw deer, elephant, crocodiles"),
# and every correct one carried one of these.
RISK_CUE = (
    r"\b(bit|bites?|bitten|attack(ed|s|ing)?|aggressive|snatch(ed|es|ing)?|"
    r"stole|steal(ing)?|chase[sd]?|chasing|beware|care ?ful|watch out|"
    r"danger(ous)?|risky?|afraid|scared|scary|threat(en(ing|ed)?)?|"
    r"warn(ing|ed|s)?|avoid|harm(ful|ed)?|injur|bite)\b"
)
# FATAL_CUE: "Bevis died" is estate history; a death is a safety fact only
# alongside the circumstance that caused it.
FATAL_CUE = (
    r"\b(drown(ed|ing)?|accident|fell|fall(en|ing)?|swept|current|slip(ped|pery)?|"
    r"danger(ous)?|every year|tourists?|visitors?|swimmer|rock|cliff|water)\b"
)

# MONEY_CUE: what turns a mention of foreigners or tips into a statement about
# PRICE, rather than about who visits or what kind of tea is grown.
# ACCESS_CUE: what makes a climb or a jeep a statement about GETTING THERE
# rather than about an activity or an operator. "Climb up the stairs" is what
# you do at the site; "the climb is steep and exhausting" is access. "Safari
# jeep service" is the attraction; "you need a jeep to reach it" is access.
ACCESS_CUE = (
    r"\b(steep|difficult|hard|tough|exhaust\w*|tiring|strenuous|easy|easier|"
    r"access\w*|reach\w*|journey|drive|driving|ride|road|roads|track|trail|"
    r"uphill|downhill|bumpy|rough|narrow|winding|potholes?|km|kilomet\w*|"
    r"miles?|hours?|minutes?|walk|walking|distance|far|steps?)\b"
)

# LITTER_CUE: what turns a container into rubbish. "Carry a water bottle" is
# advice about what to bring; "plastic bottles everywhere" is a complaint
# about what was left behind. The distinction is whether the bottle is being
# discarded, found, or counted among waste.
LITTER_CUE = (
    r"\b(litter(ed|ing)?|rubbish|garbage|waste|trash|thrown|throw(n|ing|s)?|"
    r"dump(ed|ing|s)?|discard(ed)?|left|lying|scatter(ed)?|strewn|everywhere|"
    r"all over|plastics?|polythene|dirty|filthy|mess(y)?|pile[sd]?|"
    r"empty|broken|floating|collect(ed|ing)?|pick(ed)? up|bins?)\b"
)

# FOOD_PROVISION_CUE: what makes a mention of food a statement about what the
# SITE PROVIDES. "Don't show them you have any food" is advice about monkeys.
FOOD_PROVISION_CUE = (
    r"\b(stalls?|shops?|canteens?|restaurants?|cafe|caf\w*|court|outlets?|"
    r"vendors?|sell(s|ing|er)?|buy|bought|serve[sd]?|serving|available|"
    r"provide[sd]?|offer(s|ed|ing)?|price[sd]?|cheap|expensive|tasty|"
    r"delicious|good food|bad food|hygien\w*|menu|drinks?|meals?|snacks?|"
    r"eat(ing)?|lunch|breakfast|dinner)\b"
)

# CROWDING_CUE: what turns "many people" from popularity into congestion.
CROWDING_CUE = (
    r"\b(too many|so many|crowd(ed|s|ing)?|packed|jam(med)?|queue[sd]?|"
    r"queuing|line up|wait(ing)?|rush|congest\w*|bustling|throng\w*|"
    r"noisy|noise|avoid|weekends?|holidays?|peak|season|busy|"
    r"hard to|difficult to|no space|not much space|full)\b"
)

MONEY_CUE = (
    r"\b(price|priced|pricing|cost|costs|charge|charged|charges|fee|fees|"
    r"pay|paid|paying|rupees|lkr|usd|dollars?|euros?|expensive|cheap|money|"
    r"ticket|entrance|entry|admission|rates?|extra|double|per person)\b"
)

# FREE_PRICE_CUE: what makes "free" a statement about PRICE. Either an
# explicit money word (MONEY_CUE), or a thing that is being given away --
# because "free food", "free pickup" and "all is free there" are price
# observations with no money word in them at all. Deliberately does NOT
# include abstract nouns: "a free environment", "free from plastic
# pollution" and "free to roam" are the senses this is separating out.
FREE_PRICE_CUE = (
    r"(?:" + MONEY_CUE + r")"
    r"|\bfree (?:food|drinks?|breakfast|lunch|dinner|meals?|water|wifi|wi-fi|"
    r"parking|pickup|pick.?up|drop|transfer|transport|shuttle|guide|"
    r"tour|entry|entrance|admission|access|sample|tasting|liquor|alcohol|"
    r"beer|tea|coffee|cup|glass|bottle|ticket|shuttle)\b"
    # "free to enter/visit/park/use" -- the verb form of the same claim,
    # which the noun list above cannot reach. NOT "free to all" or "free to
    # roam", which are the non-price senses.
    r"|\bfree to (?:enter|visit|use|park|attend|join|walk in|get in)\b"
    r"|\b(?:is|are|was|were|all) free\b"
    r"|\bfor free\b"
    r"|\bfree of charge\b"
    # ...and the same nouns on the OTHER side of the word, because both
    # orders occur: "free drinks" but also "drink and food free", "drop
    # service free till the hotel".
    r"|\b(?:food|drinks?|breakfast|lunch|dinner|meals?|wifi|wi-fi|parking|"
    r"pickup|pick.?up|transfer|transport|shuttle|service|entry|entrance|"
    r"admission|liquor|alcohol|beer|tea|coffee)s?\b[^.]{0,30}\bfree\b"
)

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
            r"\btracks?\b", r"\bsteps?\b", r"\btrek", r"\bhik(e|ing)\b",
            r"\breach(ing)?\b", r"\bparking\b", r"\bbus\b", r"\btrain\b",
            # City-scale movement. Absent because the gold set is sampled from
            # attraction reviews, where "the path to the summit" is the idiom
            # and "the traffic was heavy" never comes up. A real submission
            # about Kandy left four segments untagged for want of these.
            r"\btraffic\b", r"\bcongestion\b", r"\bjams?\b",
            r"\bpavements?\b", r"\bsidewalks?\b", r"\bfootpaths?\b",
            r"\btransport(ation)?\b", r"\bjourneys?\b", r"\bcommut",
            r"\bgett?ing around\b", r"\bget around\b",
            r"\btuk.?tuk\b", r"\b4wd\b", r"\bfour wheel\b",
            r"\bdriv(e|ing)\b", r"\bwalk(ing)? (up|down|distance)\b",
            r"\bdifficult to (find|reach|access|get)\b", r"\bkm\b", r"\bkilomet",
            # Qualified walks: "a slow walk", "a steep walk", "an easy walk",
            # "a pleasant stroll" describe the JOURNEY, not an activity at
            # the site. Bare \bwalk\b is too broad (every "we walked around"
            # fires). Requiring a qualifying adjective restricts the match to
            # sentences where someone is describing what it was like to get
            # there or move around. Found by testing the probe set: the
            # trained model already labels this aspect correctly once the
            # tagger fires; the gap was purely in the vocabulary.
            r"\b(slow|easy|quick|short|long|pleasant|scenic|leisurely|"
            r"steep|tough|hard|difficult|tiring|exhausting)\s+(walk|stroll|hike|climb)\b",
        ],
        # Both fired at 0.25 precision. "climb" caught "climb up the
        # stairs" and "before climb the Sigiriya" -- what you do once you are
        # there. "jeep" caught "safari jeep service" and a jeep-hire company
        # name -- the attraction and its operator, not how you got in. Gated
        # rather than dropped, because "the climb is exhausting" and "you need
        # a jeep to reach it" are exactly what this aspect is for.
        gated=[
            (r"\bclimb", ACCESS_CUE),
            (r"\bjeep\b", ACCESS_CUE),
            # NOT gated: "tuk tuk", and the reason is worth keeping.
            # A tuk-tuk is transport when it carries you somewhere and a
            # nuisance when it is parked outside pestering you, and gating it
            # behind ACCESS_CUE separates those two on the contested dev
            # sample cleanly: roads_access F1 there went 0.808 -> 0.863.
            # On the HELD-OUT representative sample it went 0.717 -> 0.706.
            # A change that gains on the sample it was tuned on and loses on
            # the sample it was not is the textbook shape of fitting the dev
            # set, so it is not kept, however good the argument sounds.
            # NOT gated: "hiking". The equipment-versus-journey argument that
            # justifies the climb and jeep gates applies to "good hiking
            # shoes" just as well, but measured on the contested dev sample it
            # removed one false positive and created one false negative -- a
            # wash, kept out on the principle that a change with no measured
            # gain does not earn a place in the lexicon.
        ],
        # NOT blocked: "off the beaten track". The idiom looked like a clean
        # veto -- it is one of this aspect's dev-sample false positives -- but
        # the same sample labels "though as it's well off the beaten track" AS
        # roads_access. Vetoing it traded one false positive for one false
        # negative. The annotator reads the phrase as access-relevant at least
        # half the time, so the lexicon should not overrule them.
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
        gated=[
            # "Food" is a facility when the site provides it and not when a
            # reviewer is warning you about monkeys: "always best not to feed
            # them or show them you have any food at all" was tagged as an
            # amenity. The cue is provision -- somewhere to buy it, someone
            # selling it, or a judgement about what is on offer.
            (r"\bfood\b", FOOD_PROVISION_CUE),
        ],
        blocked=[
            # A guidebook is a book. "The guide book said it was 500 rupees"
            # is about a price in a printed guide, not about a guide service
            # at the site.
            r"\bguide ?books?\b",
        ],
        # NOTE on the remaining precision gap. On the contested dev sample
        # "guide" fires as sole evidence 13 times and the human agrees 8 --
        # but the disagreements do not separate on any rule the lexicon could
        # express. "The guide said this would lead to better sightings" is
        # labelled facilities; "Our guide and chauffeur searched for the non
        # crowded places" is not. Both are a guide doing something. That is an
        # annotation-boundary question, not a lexicon question, and facilities
        # has the second-lowest agreement of the four labelled aspects
        # (Cohen's kappa 0.737). Gating "guide" harder here would fit the
        # noise in a 13-row sample; the honest fix is a second pass over
        # facilities with a written rule for what counts as a guide service.
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
            r"\bclean(liness|ed)?\b", r"\bjunk\b",
            # "bottles?" moved to `gated` below. On the contested dev sample it
            # fired as sole evidence 3 times and was wrong all 3: "carry a
            # water bottle", "you should bring a water bottle". A bottle is
            # litter when it has been left somewhere, and equipment when you
            # are told to bring one.
            # Upkeep vocabulary was entirely missing, so "beautifully
            # maintained" and "the place is not maintained well" both fell
            # through. Recall was 0.500 before these were added. Found by
            # evaluating against a 36-positive cleanliness test set.
            r"\bmaintain(ed|ing|ance)?\b", r"\bupkeep\b", r"\bwell kept\b",
            r"\bcared for\b", r"\bneglect(ed|s)?\b", r"\btidy\b", r"\bneat\b",
            r"\bdust(y)?\b", r"\bmudd?y\b", r"\bhygien", r"\bsanitat",
        ],
        gated=[
            # A bottle is litter when it has been left, dropped or seen lying
            # about; it is equipment when a reviewer tells you to bring one.
            # Sole evidence 3 times on the contested dev sample, wrong all 3.
            (r"\bbottles?\b", LITTER_CUE),
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
            r"\brisky?\b", r"\bleech", r"\bwild elephant",
            r"\bfell down\b", r"\brescue\b",
            # Surface hazard. "the pathway is uneven and rough most of the
            # way" is a trip risk a human labelled safety and the lexicon
            # missed entirely -- it had slippery and slip, but nothing for an
            # uneven surface. Adds 0 false positives on the contested dev
            # sample.
            r"\buneven\b",
            # A rip current is a hazard; "the current lighthouse" is a date.
            # Only the hazard readings are kept, spelled out rather than gated,
            # because the distinction is carried by the adjacent word.
            r"\b(rip|under|strong|powerful|dangerous)\s+currents?\b",
            r"\bcurrents?\s+(is|are|was|were|can be)\s+(a\s+)?(little|bit|very|quite|"
            r"really|too|so)?\s*(strong|dangerous|powerful|deadly|rough)",
            r"\brip ?tides?\b", r"\bunder ?tow\b",
            # "deep" is only about risk when it is water that is deep.
            r"\bdeep\s+(water|end|sea|river|pool|point)\b",
            r"\bwater\s+is\s+(very\s+)?deep\b",
            # Lighting and environment hazards: "poorly lit streets at night"
            # and "unlit path" are physical safety concerns. Requires the
            # negative qualifier to avoid firing on "beautifully lit at night".
            r"\bpoorly.?lit\b", r"\bbadly.?lit\b", r"\binadequately.?lit\b",
            r"\bunlit\b",
        ],
        # Wildlife and fatality words: present in the text, but they describe a
        # sighting or a history unless something signals harm. RISK_CUE is what
        # turns "we saw monkeys" into "a monkey bit my son".
        gated=[
            (r"\bmonkeys?\b", RISK_CUE),
            (r"\bcrocodiles?\b", RISK_CUE),
            (r"\bsnakes?\b", RISK_CUE),
            (r"\bdied\b", FATAL_CUE),
            (r"\bdeaths?\b", FATAL_CUE),
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
            r"\blkr\b", r"\brupees\b", r"\busd\b", r"\beuro",
            r"\bprice", r"\bfees?\b",
            # Money verbs were missing entirely: "we had to pay 100 times more
            # than the Sri Lankans", "wanted a tip", "if you're on a budget"
            # all fell through. Recall was 0.571 without these.
            r"\bpay(s|ing|ment)?\b", r"\bpaid\b", r"\bbudget\b",
            r"\bpurchase\b", r"\bcheap",
            # "one driver tried to increase the agreed fare" carried no aspect
            # at all -- the commonest way a visitor describes being
            # overcharged here, and the lexicon had no word for it.
            r"\bfares?\b", r"\baffordable\b", r"\bbargain", r"\bhaggl",
            # NOT bare "worth". r"\bworth (it|the)\b" fired on "worth the drive",
            # "worth the visit", "all worth it" -- recommendations, not prices.
            # It caused every false positive the lexicon made on the price test
            # set. Restricted to explicit money contexts, precision went 0.706 -> 1.000.
            r"\bworth (the (money|price|cost|fee)|\d)",
        ],
        # Precision was 0.733 on the tagged rows, and two triggers did most of
        # the damage. "foreigner" fired on "popular with both the locals with
        # foreigners" -- who visits, not what they pay. "tips" fired on "silver
        # tips", which is tea. Both are genuine price signals elsewhere, so
        # they are gated on a money cue rather than dropped.
        gated=[
            (r"\bforeigner", MONEY_CUE),
            (r"\btips?\b", MONEY_CUE),
            # "free" was the biggest remaining source of wrong PRICE quotes,
            # and it produced them on the praise side specifically -- which
            # is how it surfaced: reading the praise list for Horton Plains
            # showed four "praise" quotes in a row that were nothing of the
            # kind. "free tourist visas", "a clean litter free environment",
            # "National Parks that is just as beautiful and free to all"
            # (a complaint about Sri Lankan pricing, by comparison), and
            # "in the UK national parks are free" (also a complaint).
            #
            # Not dropped: most uses of the word here ARE price -- free
            # entry, free food, free airport pickup, 467 segments in the
            # clearly price sense against ~100 in the others. Gated on the
            # same money cue the other two use, which keeps "entrance was
            # free" and loses "litter free".
            # Its own cue, not MONEY_CUE. "Free" is a price statement in two
            # different shapes: it can sit next to explicit money words
            # ("entrance was free... the fee"), or it can BE the price
            # statement on its own by naming what costs nothing ("free food",
            # "free pickup from the airport", "all is free there"). MONEY_CUE
            # alone caught only the first and dropped 1,061 segments, many of
            # them genuine -- complimentary food, drinks and transfers are
            # among the commonest value observations in this corpus.
            (r"\bfree\b", FREE_PRICE_CUE),
        ],
        # X-free compounds ("litter free", "smoke free", "hassle free") are
        # never about price no matter what else is in the sentence, so the
        # money cue alone would not stop them -- "a clean litter free
        # environment" sitting in a review that also mentions the entrance
        # fee would still pass. Blocked outright instead.
        blocked=[
            r"\b(litter|plastic|smoke|smoking|rubbish|garbage|traffic|"
            r"hassle|stress|worry|care|duty|pollution|noise)[- ]free\b",
            # "free FROM x" is the absence of a nuisance, never a price --
            # "free from polythene and plastic pollution". Distinct from
            # "free FOR x" and bare "free", which usually are about cost.
            r"\bfree from\b",
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
            # Recall on a random draw was 0.286 -- five of seven missed. The
            # description above promises this aspect covers "whether it is
            # peaceful and quiet", but the quiet half was carried by three
            # words, so "redefine the terms beauty, tranquillity and serenity"
            # fell straight through. So did "many pilgrims were present" on the
            # busy side.
            r"\btranquil", r"\bserene\b", r"\bserenity\b", r"\bsolitude\b",
            r"\bdeserted\b", r"\bsecluded\b",
            r"\bbustling\b", r"\bthrong", r"\bjostl", r"\bover ?crowded\b",
            # The "many people" family moved to `gated` below -- as a plain
            # trigger it counted popularity as congestion.
            r"\bpilgrims?\b", r"\bqueu(e|es|ing)\b", r"\bline up\b",
        ],
        gated=[
            # "Many people" is crowding when there are too many of them and
            # popularity when there are simply a lot. Measured on the corpus:
            # this phrase is the only crowd evidence in 182 segments, and 128
            # of those carry no crowding language at all -- "many people visit
            # to enjoy the beautiful sunset", "a place that will provide
            # mental health for many people". Those are statements about who
            # comes, not about the site being busy.
            (r"\b(many|lots? of|full of|plenty of|lot of) "
             r"(people|visitors|tourists|pilgrims|devotees)\b", CROWDING_CUE),
        ],
        blocked=[
            # "Busy" describing the CITY the site sits in, in a sentence
            # praising the site as an escape from it: "a natural wetland park
            # in the busy capital", "perfect place to hide out in busy
            # Colombo". 109 segments in the corpus where "busy" is the only
            # crowd evidence and it refers to somewhere else entirely -- the
            # site is being called the opposite of crowded.
            r"\bbusy\s+(capital|city|cities|town|urban|colombo|kandy|galle|"
            r"street|streets|life|lifestyle|atmosphere|schedule|world|day|"
            r"days|week|routine)\b",
            r"\b(from|escape|away from|amidst|amid|middle of|midst of)\s+"
            r"(the\s+)?busy\b",
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
            # The features themselves. "Surrounded by green hills and centred
            # around Kandy Lake" is a scenery statement containing none of the
            # abstract words this list was built from.
            r"\bhills?\b", r"\blakes?\b", r"\bmountains?\b", r"\brivers?\b",
            r"\bvalleys?\b", r"\blagoons?\b", r"\bcliffs?\b",
            r"\bflora\b", r"\bviewing (point|booth)", r"\bview ?point",
            # Wildlife by name. The description above has always said this
            # aspect covers "wildlife sightings", but the trigger list held
            # only the generic words -- no animal was ever named, so every
            # "we saw monkeys and a few deer" fell straight through. Measured
            # against the human labels, 27 of scenery's 55 positives were
            # missed and most of them were sightings; recall was 0.509.
            #
            # The same nouns live in the safety lexicon, gated behind a risk
            # cue. That is the right division of labour: a monkey is scenery
            # when it is seen and safety when it bites, and one segment may
            # legitimately be both.
            r"\bmonkeys?\b", r"\belephants?\b", r"\bcrocodiles?\b", r"\bcrocs?\b",
            r"\bleopards?\b", r"\bturtles?\b", r"\bterrapins?\b", r"\bdeer\b",
            r"\bpeacocks?\b", r"\bbuffalo(e?s)?\b", r"\blangur", r"\bmacaque",
            r"\bwhales?\b", r"\bdolphins?\b", r"\bsloth ?bear", r"\bmongoose",
            r"\biguanas?\b", r"\bsquirrels?\b", r"\banimals?\b", r"\bsafari\b",
            # NOT "pretty" or "lovely": they are used as intensifiers ("pretty
            # busy", "lovely people") and each added a false positive.
        ],
        polarity_hint="positive control -- must come out positive or the model is wrong",
    ),
}

# --------------------------------------------------------------------------
# Scenery: bare feature nouns, and when they do not mean scenery
#
# The scenery lexicon names the features themselves -- lake, hill, waterfall,
# elephant, animal -- because "surrounded by green hills" is a scenery
# statement containing none of the abstract words the list was built from.
# The cost is that the noun fires wherever it appears, including in sentences
# that are plainly about something else:
#
#     "Bad smell in some areas close to lake"            -> scenery complaint
#     "Animal cages should be more cleaned."             -> scenery complaint
#     "but wish they had more signage regarding the plants." -> scenery complaint
#     "Not the best facilities for all of the animals"   -> scenery complaint
#
# Measured on the corpus: 10,967 of 40,071 scenery mentions (27%) rest on a
# bare noun with no appearance or experience cue anywhere in the segment.
#
# Deleting the nouns is not an option -- they were added because recall was
# 0.509 without them. Gating them on an appearance cue alone is too blunt: it
# would drop 3,343 positive opinions like "One of the best waterfalls in Sri
# Lanka" and "That was a super safari!", which carry no word on the list.
#
# So the rule is narrower, and it is about attribution rather than presence:
# a bare noun does not make a segment scenery WHEN the segment is already
# about another aspect. "Beautiful lake but the road is bad" is untouched --
# "beautiful" is a cue, so its scenery evidence is not bare. Measured effect:
# 2,718 mentions re-attributed (6.8% of scenery), of which 494 are negative --
# a 38% negative share against scenery's corpus-wide 10%, which is the
# misattribution this removes.
#
# NOT CONFIRMED against human labels, and there is now nothing that looks like
# confirmation either. reports/accuracy_all_aspects.json used to quote scenery
# precision 0.750 -- a figure with no labels behind it, since
# LABEL_THESE_price_crowd_scenery.{xlsx,csv} are blank templates and every
# aspect column in goldset_annotator{1,2}.csv is empty. That row has been
# withdrawn; scenery is listed under `unmeasured` there instead. Fill a sheet
# in and re-run scripts/38 and scripts/44 to turn this rule from an argued
# change into a measured one. SCENERY_ATTRIBUTION_RULE = False restores the old
# behaviour for that comparison.
# --------------------------------------------------------------------------
SCENERY_ATTRIBUTION_RULE = True

# The nouns that name a feature without saying anything about how it looks.
SCENERY_BARE_NOUNS = [
    r"\bhills?\b", r"\blakes?\b", r"\bmountains?\b", r"\brivers?\b",
    r"\bvalleys?\b", r"\blagoons?\b", r"\bcliffs?\b", r"\bforests?\b",
    r"\btrees?\b", r"\bplants?\b", r"\bflowers?\b", r"\bbirds?\b",
    r"\banimals?\b", r"\bwaterfalls?\b", r"\bmonkeys?\b",
    r"\belephants?\b", r"\bcrocodiles?\b", r"\bcrocs?\b", r"\bleopards?\b",
    r"\bturtles?\b", r"\bterrapins?\b", r"\bdeer\b", r"\bpeacocks?\b",
    r"\bbuffalo(e?s)?\b", r"\blangur", r"\bmacaque", r"\bwhales?\b",
    r"\bdolphins?\b", r"\bsloth ?bear", r"\bmongoose", r"\biguanas?\b",
    r"\bsquirrels?\b", r"\bsafari\b",
]

# Words that show the feature is being LOOKED AT or ENJOYED rather than merely
# mentioned. Sighting verbs are here because the aspect's own description
# covers "wildlife sightings" and "we saw elephants and deer" contains no
# beauty word; the quality words are here because "one of the best waterfalls"
# is scenery praise that the appearance lexicon misses entirely.
SCENERY_CONTEXT_CUES = (
    r"\b(saw|seen|see|seeing|spot(ted|ting)?|sight(ed|ing|ings)?|watch(ed|ing)?|"
    r"observe(d)?|encounter(ed)?|glimpse(d)?|roam(ing|ed)?|wander(ing|ed)?|"
    r"graz(e|ing)|herd|flock|nest(ing|s)?|migrat|lovely|wonderful|"
    r"enjoy(ed|able)?|magnificent|majestic|"
    r"surrounded by|covered (in|with)|full of|lots of|plenty of|home to)\b"
)

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

# The 25 administrative districts of Sri Lanka, in full.
#
# DISTRICT_CANON above only maps the spellings this corpus happens to contain,
# so deriving a district list from it yields whatever the scrapers reached --
# 19 names, silently missing Batticaloa, Kilinochchi, Monaragala, Mullaitivu,
# Puttalam and Vavuniya. That is fine as a description of corpus coverage and
# wrong as a reference list: the API's /districts endpoint was handing out the
# short list while telling callers to submit one of its values, so a visitor
# reviewing a place in Batticaloa had no correct answer to give.
#
# Coverage is a separate question from validity, and reported separately --
# see /districts, which flags which of these the corpus actually contains.
DISTRICTS: List[str] = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo",
    "Galle", "Gampaha", "Hambantota", "Jaffna", "Kalutara",
    "Kandy", "Kegalle", "Kilinochchi", "Kurunegala", "Mannar",
    "Matale", "Matara", "Monaragala", "Mullaitivu", "Nuwara Eliya",
    "Polonnaruwa", "Puttalam", "Ratnapura", "Trincomalee", "Vavuniya",
]

# Lowercased index, so a submitted "nuwara eliya" or "KANDY" resolves to the
# canonical spelling instead of being rejected on case alone.
DISTRICT_LOOKUP: Dict[str, str] = {d.lower(): d for d in DISTRICTS}
