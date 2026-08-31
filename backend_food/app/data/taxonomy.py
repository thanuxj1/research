"""Domain ontology: facets, phrase lexicon, and the dish tag rules.

Everything the query understanding layer knows about the food domain is declared
here as data. The original implementation scattered this knowledge across ~15
inline `if keyword in query_lower: score *= factor` branches inside the /search
handler, which made behaviour impossible to test or reason about.

Two design rules:

1. **Word-boundary matching, never substring.** The original code used
   `'tea' in query`, which fires on "ins*tea*d" and "s*tea*med", and
   `'egg' in name`, which flags *Eggplant Curry* as containing egg. Every
   pattern here is compiled with `\\b` anchors.

2. **Longest phrase wins.** "tea time" must be recognised as a snack intent
   before the bare "tea" drink alias can claim it. Phrases are sorted by token
   length descending at import time.
"""

from __future__ import annotations

import re
from typing import Iterable

# ---------------------------------------------------------------------------
# Ordinal scales
# ---------------------------------------------------------------------------
# The shipped dataset only contains None/Low/Medium/High. "Very High" is kept
# for forward compatibility but is currently unreachable, which is why the
# original code's "Very High" branches were dead.
SPICE_LEVELS: tuple[str, ...] = ("None", "Low", "Medium", "High", "Very High")
SPICE_ORDER: dict[str, int] = {level: i for i, level in enumerate(SPICE_LEVELS)}

PRICE_LEVELS: tuple[str, ...] = ("Low", "Medium", "High")
PRICE_ORDER: dict[str, int] = {level: i for i, level in enumerate(PRICE_LEVELS)}

CATEGORIES: tuple[str, ...] = (
    "Main Meals",
    "Curries",
    "Short Eats",
    "Snacks",
    "Desserts",
    "Drinks",
    "Soups",
    "Sauces & Sides",
)

MEAL_TIMES: tuple[str, ...] = ("Breakfast", "Lunch", "Dinner")

# Facet identifiers used by the NLU layer.
FACET_DIET = "diet"
FACET_SPICE = "spice"
FACET_MEAL = "meal"
FACET_PRICE = "price"
FACET_CATEGORY = "category"
FACET_TAG = "tag"

DIET_VEG = "veg"
DIET_NONVEG = "nonveg"

# ---------------------------------------------------------------------------
# Negation handling
# ---------------------------------------------------------------------------
# Cues that invert the polarity of a facet mention appearing shortly after them.
# Cues that invert a facet mention appearing after them.
#
# Deliberately excluded: "free", "allergy", "intolerance" and "anything". Those
# are *suffix* cues ("gluten free", "nut allergy") or handled by
# NEGATION_CUE_PHRASES ("anything but"). Listing them here as prefix cues made
# them negate the *following* phrase too, so "gluten free breakfast" excluded
# breakfast and "anything mild" excluded mild.
NEGATION_CUES: frozenset[str] = frozenset(
    {
        "not",
        "no",
        "non",
        "none",
        "without",
        "avoid",
        "avoiding",
        "exclude",
        "excluding",
        "except",
        "minus",
        "skip",
        "hate",
        "hates",
        "dislike",
        "dislikes",
        "cannot",
        "cant",
        "never",
        "allergic",
        "intolerant",
    }
)

# Tokens that carry a negation forward to a second coordinated facet, so
# "no eggs or dairy" excludes both.
CONJUNCTIONS: frozenset[str] = frozenset({"and", "or", "nor", "plus"})

# Multi-word cues, normalised before token matching.
NEGATION_CUE_PHRASES: tuple[tuple[str, str], ...] = (
    ("do not like", "not"),
    ("don t like", "not"),
    ("dont like", "not"),
    ("does not like", "not"),
    ("do not want", "not"),
    ("dont want", "not"),
    ("can not eat", "cannot"),
    ("cant eat", "cannot"),
    ("can t eat", "cannot"),
    ("not a fan of", "not"),
    ("stay away from", "avoid"),
    ("keep away from", "avoid"),
    ("allergic to", "allergic"),
    ("anything but", "not"),
    ("other than", "not"),
    ("apart from", "not"),
    ("instead of", "not"),
    ("less of", "not"),
)

# A negation cue does not reach past these tokens, so "not spicy but seafood"
# leaves "seafood" positive.
SCOPE_BREAKERS: frozenset[str] = frozenset({"but", "however", "though", "although", "yet", "still"})

# Maximum number of filler tokens skipped when looking back from a facet phrase
# for its governing cue ("without any more of that coconut").
MAX_FILLER_SKIP = 3

# ---------------------------------------------------------------------------
# Phrase lexicon: surface phrase -> list of (facet, value) constraints
# ---------------------------------------------------------------------------
# A phrase may imply several constraints at once ("for tourists" implies both a
# beginner-friendly preference and a low spice ceiling).
FacetPair = tuple[str, str]

PHRASE_LEXICON: dict[str, list[FacetPair]] = {
    # --- diet -------------------------------------------------------------
    "vegetarian": [(FACET_DIET, DIET_VEG)],
    "vegetarians": [(FACET_DIET, DIET_VEG)],
    "veggie": [(FACET_DIET, DIET_VEG)],
    "veg": [(FACET_DIET, DIET_VEG)],
    "plant based": [(FACET_DIET, DIET_VEG)],
    "meatless": [(FACET_DIET, DIET_VEG)],
    "vegan": [(FACET_DIET, DIET_VEG), (FACET_TAG, "vegan")],
    "non vegetarian": [(FACET_DIET, DIET_NONVEG)],
    "nonveg": [(FACET_DIET, DIET_NONVEG)],
    "non veg": [(FACET_DIET, DIET_NONVEG)],
    "meat": [(FACET_DIET, DIET_NONVEG)],
    "meaty": [(FACET_DIET, DIET_NONVEG)],
    "carnivore": [(FACET_DIET, DIET_NONVEG)],
    # --- spice ------------------------------------------------------------
    # Longest-first ordering makes "medium spice" beat bare "spice".
    "extremely spicy": [(FACET_SPICE, "Very High")],
    "extra spicy": [(FACET_SPICE, "High")],
    "very spicy": [(FACET_SPICE, "High")],
    "super spicy": [(FACET_SPICE, "High")],
    "really spicy": [(FACET_SPICE, "High")],
    "medium spice": [(FACET_SPICE, "Medium")],
    "medium spicy": [(FACET_SPICE, "Medium")],
    "moderately spicy": [(FACET_SPICE, "Medium")],
    "moderate spice": [(FACET_SPICE, "Medium")],
    "low spice": [(FACET_SPICE, "Low")],
    "mildly spiced": [(FACET_SPICE, "Low")],
    "lightly spiced": [(FACET_SPICE, "Low")],
    "zero spice": [(FACET_SPICE, "None")],
    "no heat": [(FACET_SPICE, "None")],
    "spicy": [(FACET_SPICE, "High")],
    "spice": [(FACET_SPICE, "High")],
    "spiced": [(FACET_SPICE, "High")],
    "hot": [(FACET_SPICE, "High")],
    "fiery": [(FACET_SPICE, "High")],
    "chili": [(FACET_SPICE, "High")],
    "chilli": [(FACET_SPICE, "High")],
    "mild": [(FACET_SPICE, "Low")],
    "gentle": [(FACET_SPICE, "Low")],
    "bland": [(FACET_SPICE, "None")],
    # --- price ------------------------------------------------------------
    "cheap": [(FACET_PRICE, "Low")],
    "budget": [(FACET_PRICE, "Low")],
    "affordable": [(FACET_PRICE, "Low")],
    "inexpensive": [(FACET_PRICE, "Low")],
    "low price": [(FACET_PRICE, "Low")],
    "low cost": [(FACET_PRICE, "Low")],
    "expensive": [(FACET_PRICE, "High")],
    "premium": [(FACET_PRICE, "High")],
    "high end": [(FACET_PRICE, "High")],
    "fancy": [(FACET_PRICE, "High")],
    "splurge": [(FACET_PRICE, "High")],
    "mid range": [(FACET_PRICE, "Medium")],
    # --- meal time --------------------------------------------------------
    "breakfast": [(FACET_MEAL, "Breakfast")],
    "morning": [(FACET_MEAL, "Breakfast")],
    "brunch": [(FACET_MEAL, "Breakfast")],
    "lunch": [(FACET_MEAL, "Lunch")],
    "midday": [(FACET_MEAL, "Lunch")],
    "noon": [(FACET_MEAL, "Lunch")],
    "dinner": [(FACET_MEAL, "Dinner")],
    "supper": [(FACET_MEAL, "Dinner")],
    "evening": [(FACET_MEAL, "Dinner")],
    "late night": [(FACET_MEAL, "Dinner")],
    # --- category ---------------------------------------------------------
    # "tea time" must precede "tea"; the sort by token count guarantees it.
    "tea time": [(FACET_TAG, "tea_time")],
    "teatime": [(FACET_TAG, "tea_time")],
    "short eats": [(FACET_CATEGORY, "Short Eats"), (FACET_TAG, "tea_time")],
    "short eat": [(FACET_CATEGORY, "Short Eats"), (FACET_TAG, "tea_time")],
    "with tea": [(FACET_TAG, "tea_time")],
    "drink": [(FACET_CATEGORY, "Drinks")],
    "drinks": [(FACET_CATEGORY, "Drinks")],
    "beverage": [(FACET_CATEGORY, "Drinks")],
    "beverages": [(FACET_CATEGORY, "Drinks")],
    "juice": [(FACET_CATEGORY, "Drinks")],
    "smoothie": [(FACET_CATEGORY, "Drinks")],
    "milkshake": [(FACET_CATEGORY, "Drinks")],
    "shake": [(FACET_CATEGORY, "Drinks")],
    "tea": [(FACET_CATEGORY, "Drinks")],
    "coffee": [(FACET_CATEGORY, "Drinks")],
    "thirsty": [(FACET_CATEGORY, "Drinks")],
    "something to drink": [(FACET_CATEGORY, "Drinks")],
    "dessert": [(FACET_CATEGORY, "Desserts")],
    "desserts": [(FACET_CATEGORY, "Desserts")],
    "sweets": [(FACET_CATEGORY, "Desserts")],
    "sweet treat": [(FACET_CATEGORY, "Desserts")],
    "pudding": [(FACET_CATEGORY, "Desserts")],
    "curry": [(FACET_CATEGORY, "Curries")],
    "curries": [(FACET_CATEGORY, "Curries")],
    "soup": [(FACET_CATEGORY, "Soups")],
    "soups": [(FACET_CATEGORY, "Soups")],
    "broth": [(FACET_CATEGORY, "Soups")],
    "snack": [(FACET_CATEGORY, "Short Eats")],
    "snacks": [(FACET_CATEGORY, "Short Eats")],
    "sambol": [(FACET_CATEGORY, "Sauces & Sides")],
    "sambal": [(FACET_CATEGORY, "Sauces & Sides")],
    "condiment": [(FACET_CATEGORY, "Sauces & Sides")],
    "condiments": [(FACET_CATEGORY, "Sauces & Sides")],
    "side dish": [(FACET_CATEGORY, "Sauces & Sides")],
    "side dishes": [(FACET_CATEGORY, "Sauces & Sides")],
    "pickle": [(FACET_CATEGORY, "Sauces & Sides")],
    "chutney": [(FACET_CATEGORY, "Sauces & Sides")],
    "main meal": [(FACET_CATEGORY, "Main Meals")],
    "main meals": [(FACET_CATEGORY, "Main Meals")],
    "main course": [(FACET_CATEGORY, "Main Meals")],
    "full meal": [(FACET_CATEGORY, "Main Meals")],
    "rice and curry": [(FACET_CATEGORY, "Main Meals")],
    # --- ingredient / attribute tags -------------------------------------
    "seafood": [(FACET_TAG, "seafood")],
    "fish": [(FACET_TAG, "fish"), (FACET_TAG, "seafood")],
    "prawn": [(FACET_TAG, "prawn"), (FACET_TAG, "seafood")],
    "prawns": [(FACET_TAG, "prawn"), (FACET_TAG, "seafood")],
    "shrimp": [(FACET_TAG, "prawn"), (FACET_TAG, "seafood")],
    "crab": [(FACET_TAG, "crab"), (FACET_TAG, "seafood")],
    "cuttlefish": [(FACET_TAG, "cuttlefish"), (FACET_TAG, "seafood")],
    "squid": [(FACET_TAG, "cuttlefish"), (FACET_TAG, "seafood")],
    # Specific meats intentionally do NOT set the diet facet. The tag alone is
    # enough signal, and letting them set diet created unresolvable conflicts
    # for queries like "vegetarian alternative to chicken".
    "chicken": [(FACET_TAG, "chicken")],
    "beef": [(FACET_TAG, "beef")],
    "pork": [(FACET_TAG, "pork")],
    "mutton": [(FACET_TAG, "mutton")],
    "lamb": [(FACET_TAG, "mutton")],
    "egg": [(FACET_TAG, "egg")],
    "eggs": [(FACET_TAG, "egg")],
    "coconut": [(FACET_TAG, "coconut")],
    "dairy": [(FACET_TAG, "dairy")],
    "milk": [(FACET_TAG, "dairy")],
    "gluten": [(FACET_TAG, "gluten")],
    "wheat": [(FACET_TAG, "gluten")],
    "nuts": [(FACET_TAG, "nuts")],
    "nut": [(FACET_TAG, "nuts")],
    "cashew": [(FACET_TAG, "nuts")],
    "peanut": [(FACET_TAG, "nuts")],
    "lentil": [(FACET_TAG, "lentil")],
    "lentils": [(FACET_TAG, "lentil")],
    "dhal": [(FACET_TAG, "lentil")],
    "dal": [(FACET_TAG, "lentil")],
    "rice": [(FACET_TAG, "rice")],
    "jackfruit": [(FACET_TAG, "jackfruit")],
    "soy": [(FACET_TAG, "soy")],
    "soya": [(FACET_TAG, "soy")],
    "sugar": [(FACET_TAG, "high_sugar")],
    "sugary": [(FACET_TAG, "high_sugar")],
    "fried": [(FACET_TAG, "deep_fried")],
    "deep fried": [(FACET_TAG, "deep_fried")],
    "oily": [(FACET_TAG, "deep_fried")],
    "street food": [(FACET_TAG, "street_food")],
    "streetfood": [(FACET_TAG, "street_food")],
    "roadside": [(FACET_TAG, "street_food")],
    "healthy": [(FACET_TAG, "healthy")],
    "nutritious": [(FACET_TAG, "healthy")],
    "light": [(FACET_TAG, "healthy")],
    "wholesome": [(FACET_TAG, "healthy")],
    "diet": [(FACET_TAG, "healthy")],
    "traditional": [(FACET_TAG, "traditional")],
    "authentic": [(FACET_TAG, "traditional")],
    "heritage": [(FACET_TAG, "traditional")],
    "classic": [(FACET_TAG, "traditional")],
    "festive": [(FACET_TAG, "festive")],
    "festival": [(FACET_TAG, "festive")],
    "celebration": [(FACET_TAG, "festive")],
    "new year": [(FACET_TAG, "festive")],
    "must try": [(FACET_TAG, "must_try")],
    "must eat": [(FACET_TAG, "must_try")],
    "famous": [(FACET_TAG, "must_try")],
    "iconic": [(FACET_TAG, "must_try")],
    "signature": [(FACET_TAG, "must_try")],
    "popular": [(FACET_TAG, "must_try")],
    "best": [(FACET_TAG, "must_try")],
    "top": [(FACET_TAG, "must_try")],
    "recommended": [(FACET_TAG, "must_try")],
    "hot drink": [(FACET_TAG, "hot_drink"), (FACET_CATEGORY, "Drinks")],
    "warm drink": [(FACET_TAG, "hot_drink"), (FACET_CATEGORY, "Drinks")],
    "cold drink": [(FACET_TAG, "cold_drink"), (FACET_CATEGORY, "Drinks")],
    "iced": [(FACET_TAG, "cold_drink")],
    "refreshing": [(FACET_TAG, "cold_drink")],
    # --- audience ---------------------------------------------------------
    "tourist": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "tourists": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "beginner": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "beginners": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "foreigner": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "kids": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "children": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
    "first time": [(FACET_TAG, "beginner_friendly"), (FACET_SPICE, "Low")],
}

# ---------------------------------------------------------------------------
# Sparse-retrieval query expansion
# ---------------------------------------------------------------------------
# NOTE: these terms are injected into the BM25 token bag ONLY. The original code
# appended synonyms to the string that was then fed to the *sentence encoder* as
# well; keyword stuffing measurably degrades sentence-embedding quality, because
# the encoder is trained on natural language, not term bags. The dense side now
# receives the clean natural-language query instead.
SPARSE_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "mild": ("gentle", "low", "spice", "beginner"),
    "spicy": ("hot", "chili", "fiery", "high"),
    "vegetarian": ("vegan", "plant", "based"),
    "vegan": ("vegetarian", "plant", "based"),
    "breakfast": ("morning", "meal"),
    "lunch": ("midday", "meal"),
    "dinner": ("evening", "meal"),
    "dessert": ("sweet", "pudding", "cake", "toffee"),
    "sweet": ("dessert", "sugar", "jaggery", "treacle"),
    "seafood": ("fish", "prawn", "crab", "cuttlefish"),
    "street": ("kottu", "roti", "vada", "roll"),
    "drink": ("beverage", "juice", "tea", "coffee"),
    "beverage": ("drink", "juice", "tea", "coffee"),
    "healthy": ("nutritious", "herbal", "light"),
    "cheap": ("budget", "affordable", "low", "price"),
    "traditional": ("authentic", "heritage", "ceylon"),
    "tourist": ("beginner", "mild", "safe"),
    "snack": ("short", "eat", "bun", "roll", "patties", "cutlet"),
    "soup": ("broth", "stew"),
}

# ---------------------------------------------------------------------------
# Dish tag rules
# ---------------------------------------------------------------------------
# Each tag is a set of keywords matched (word-boundary) against
# "<name> <description>". These tags power three things at once: facet
# filtering, ranking signals, and the health-warning engine. One tagging pass,
# one source of truth.
TAG_KEYWORDS: dict[str, tuple[str, ...]] = {
    # --- allergens / ingredients -----------------------------------------
    "seafood": (
        "fish", "prawn", "prawns", "crab", "cuttlefish", "seafood", "malu",
        "anchovies", "sardine", "shrimp",
    ),
    "fish": ("fish", "malu", "ambul thiyal", "anchovies", "sardine"),
    "prawn": ("prawn", "prawns", "shrimp"),
    "crab": ("crab",),
    "cuttlefish": ("cuttlefish", "squid"),
    "coconut": (
        "coconut", "pol roti", "pol toffee", "hopper", "hoppers", "pittu",
        "kiribath", "kiri hodi", "watalappan", "kalu dodol", "lavariya",
        "helapa", "aggala", "aluwa", "kevum", "thala", "dosa", "idli",
        "kola kenda", "sambol", "polos", "ala hodi", "dhal curry",
        "mushroom curry", "pumpkin curry", "cashew nut curry",
        "fish white curry", "butter chicken",
    ),
    # "custard" is an egg preparation; without it Caramel Pudding - a
    # crème-caramel egg custard - carried no egg tag at all, because neither its
    # name nor its description contains the word "egg".
    "egg": ("egg", "eggs", "omelet", "omelette", "custard"),
    # "cream"/"creamy" are texture words in this corpus ("creamy coconut milk
    # curry"), not dairy indicators, so they are deliberately absent.
    "dairy": (
        "milk", "milkshake", "butter", "cheese", "curd", "yogurt", "yoghurt",
        "ghee", "chocolate", "lassi", "ice cream", "condensed milk",
        # Named explicitly rather than via "custard", which would wrongly claim
        # Watalappan - that is a *coconut* custard.
        "caramel pudding", "biscuit pudding",
    ),
    "gluten": (
        "bread", "roti", "naan", "paratha", "puri", "godamba", "kottu", "roll",
        "rolls", "bun", "buns", "patties", "cutlet", "samosa", "sandwich",
        "sandwiches", "roast pan", "biscuit", "cake", "pastry", "flour",
        "noodles", "wheat",
    ),
    "nuts": ("cashew", "nut", "nuts", "peanut", "groundnut", "sesame", "thala"),
    "soy": ("soya", "soy", "tofu"),
    "lentil": ("lentil", "lentils", "dhal", "dal", "parippu", "vadai", "vada", "kadala", "chickpea", "chickpeas"),
    "rice": ("rice", "kiribath", "biryani", "hoppers", "pittu", "idli", "string hoppers", "lamprais"),
    "jackfruit": ("jackfruit", "polos", "kos"),
    "chicken": ("chicken",),
    "beef": ("beef",),
    "pork": ("pork",),
    "mutton": ("mutton", "lamb"),
    # --- nutrition profile (drives the health engine) --------------------
    "high_sugar": (
        "toffee", "cake", "pudding", "jaggery", "treacle", "falooda",
        "bubble tea", "lassi", "ginger beer", "lemonade", "watalappan",
        "aggala", "aluwa", "athirasa", "kevum", "aasmi", "kokis", "dosi",
        "pani walalu", "kalu dodol", "sweet", "sugar", "candy", "syrup",
        "hot chocolate", "kimbula bun", "seeni sambol", "dessert",
    ),
    "high_gi": ("rice", "biryani", "hoppers", "pittu", "string hoppers", "idli", "bread", "noodles"),
    "high_sodium": (
        "devilled", "pickle", "lunumiris", "kochchi", "papadam", "spicy cashew",
        "malay pickle", "salted", "salty",
    ),
    "high_purine": (
        "mutton", "beef", "pork", "meatball", "anchovies", "sardine", "seafood",
        "prawn", "crab", "cuttlefish", "fish", "lamb",
    ),
    "deep_fried": (
        "fried", "deep-fried", "deep fried", "devilled", "roll", "rolls",
        "cutlet", "patties", "samosa", "vada", "vadai", "kokis", "kevum",
        "puri", "athirasa", "aasmi", "dolphin kottu",
    ),
    "high_saturated_fat": ("pork", "beef", "mutton", "meatball", "butter", "cream", "coconut milk", "lamb"),
    "high_protein": (
        "chicken", "beef", "pork", "mutton", "fish", "prawn", "crab",
        "cuttlefish", "meatball", "soya meat", "egg", "lamb",
    ),
    "high_potassium": ("banana blossom", "lotus root", "ambarella", "cashew", "dhal", "potato", "manioc", "sweet potato"),
    "alcohol": ("beer", "alcohol", "arrack", "wine"),
    "caffeine": ("coffee", "tea", "chocolate"),
    # --- style / occasion ------------------------------------------------
    "street_food": ("street food", "kottu", "vada", "vadai", "roll", "roti", "bun", "samosa", "street"),
    "tea_time": (
        "tea-time", "tea time", "short eat", "bun", "roll", "patties",
        "cutlet", "vada", "vadai", "cake", "kokis", "toffee", "samosa",
        "biscuit", "sandwich",
    ),
    "festive": ("festive", "new year", "celebration", "festival"),
    "healthy": ("healthy", "nutritious", "herbal", "wholesome", "detox", "light", "high nutrition"),
    # "famous" deliberately lives in must_try only, not here.
    "traditional": ("traditional", "authentic", "heritage"),
    "must_try": ("must-try", "must try", "famous", "signature", "popular", "iconic"),
    "beginner_friendly": ("beginner", "beginner-friendly", "tourist", "tourists", "good for tourists", "safe", "gentle"),
    "hot_drink": ("hot drink", "warm beverage", "hot beverage"),
    "cold_drink": ("cold drink", "iced", "chilled", "refreshing", "cold beverage"),
    "vegan": ("vegan", "plant-based"),
}

# Phrases removed from the haystack *before* a tag's positive keywords are
# matched. Without these the keyword ontology produces confident false
# positives, several of which are safety-relevant:
#
#   "creamy coconut milk potato curry" -> dairy  -> false lactose warning
#   "boiled sweet potatoes"            -> sugar  -> false diabetes warning
#   "sweet spicy stir-fried chicken"   -> sugar  -> false diabetes warning
#
# A plant milk is not dairy and a sweet-and-sour pickle is not a dessert.
TAG_NEGATIVE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dairy": (
        "coconut milk", "soya milk", "soy milk", "almond milk", "plant milk",
        "milk rice", "king coconut",
    ),
    "high_sugar": (
        "sweet potato", "sweet potatoes", "sweet sour", "sweet and sour",
        "sweet spicy", "sweet corn",
    ),
    "deep_fried": ("sweet rolls", "seed rolls", "string hopper"),
    "gluten": ("sweet rolls", "seed rolls", "rice flour", "lentil flour", "millet flour"),
    "alcohol": ("ginger beer", "root beer"),
}

# Tags a dish gets purely from its dataset category.
CATEGORY_TAGS: dict[str, tuple[str, ...]] = {
    "Drinks": ("drink",),
    "Desserts": ("dessert", "high_sugar"),
    "Short Eats": ("tea_time",),
    "Snacks": ("tea_time",),
    "Soups": ("soup",),
    "Sauces & Sides": ("condiment",),
}

# Tags that may never be inferred for a vegetarian dish. Guards against the
# description of a veg dish mentioning a meat comparison
# (e.g. Polos Curry: "meat-like texture").
NONVEG_ONLY_TAGS: frozenset[str] = frozenset(
    {"seafood", "fish", "prawn", "crab", "cuttlefish", "chicken", "beef", "pork", "mutton"}
)

# Tags that behave as allergens: when a user excludes one it becomes a HARD
# filter (drop the result) rather than a soft ranking penalty. Getting an
# allergen wrong is a safety issue, not a relevance issue.
ALLERGEN_TAGS: frozenset[str] = frozenset(
    {"seafood", "fish", "prawn", "crab", "cuttlefish", "coconut", "egg", "dairy", "gluten", "nuts", "soy", "alcohol"}
)

# Human-readable labels for the UI.
TAG_LABELS: dict[str, str] = {
    "seafood": "Seafood",
    "fish": "Fish",
    "prawn": "Prawn",
    "crab": "Crab",
    "cuttlefish": "Cuttlefish",
    "coconut": "Coconut",
    "egg": "Egg",
    "dairy": "Dairy",
    "gluten": "Gluten",
    "nuts": "Nuts",
    "soy": "Soy",
    "lentil": "Lentil",
    "rice": "Rice",
    "jackfruit": "Jackfruit",
    "chicken": "Chicken",
    "beef": "Beef",
    "pork": "Pork",
    "mutton": "Mutton",
    "high_sugar": "High sugar",
    "high_gi": "High GI",
    "high_sodium": "High sodium",
    "high_purine": "High purine",
    "deep_fried": "Deep fried",
    "high_saturated_fat": "High saturated fat",
    "high_protein": "High protein",
    "high_potassium": "High potassium",
    "alcohol": "Alcohol",
    "caffeine": "Caffeine",
    "street_food": "Street food",
    "tea_time": "Tea time",
    "festive": "Festive",
    "healthy": "Healthy",
    "traditional": "Traditional",
    "must_try": "Must try",
    "beginner_friendly": "Beginner friendly",
    "hot_drink": "Hot drink",
    "cold_drink": "Cold drink",
    "vegan": "Vegan",
    "drink": "Drink",
    "dessert": "Dessert",
    "soup": "Soup",
    "condiment": "Condiment",
}


# ---------------------------------------------------------------------------
# Compiled structures
# ---------------------------------------------------------------------------
def _compile_keyword_matcher(keywords: Iterable[str]) -> re.Pattern[str]:
    """Word-boundary alternation, longest alternative first.

    Longest-first matters for correctness of `re` alternation: without it,
    "fish" would consume the prefix of "fish white curry".
    """
    ordered = sorted({k.strip().lower() for k in keywords if k.strip()}, key=len, reverse=True)
    if not ordered:
        return re.compile(r"(?!)")  # never matches
    alternation = "|".join(re.escape(k) for k in ordered)
    return re.compile(rf"(?<!\w)(?:{alternation})(?!\w)")


TAG_MATCHERS: dict[str, re.Pattern[str]] = {
    tag: _compile_keyword_matcher(keywords) for tag, keywords in TAG_KEYWORDS.items()
}

TAG_NEGATIVE_MATCHERS: dict[str, re.Pattern[str]] = {
    tag: _compile_keyword_matcher(keywords)
    for tag, keywords in TAG_NEGATIVE_KEYWORDS.items()
}

# Phrases grouped by token count, descending, for greedy longest-match scanning.
PHRASES_BY_LENGTH: list[tuple[int, dict[str, list[FacetPair]]]] = []


def _build_phrase_index() -> None:
    buckets: dict[int, dict[str, list[FacetPair]]] = {}
    for phrase, pairs in PHRASE_LEXICON.items():
        n = len(phrase.split())
        buckets.setdefault(n, {})[phrase] = pairs
    PHRASES_BY_LENGTH.clear()
    for n in sorted(buckets, reverse=True):
        PHRASES_BY_LENGTH.append((n, buckets[n]))


_build_phrase_index()

MAX_PHRASE_TOKENS: int = PHRASES_BY_LENGTH[0][0] if PHRASES_BY_LENGTH else 1


def tag_label(tag: str) -> str:
    return TAG_LABELS.get(tag, tag.replace("_", " ").title())


def spice_rank(level: str) -> int:
    """Ordinal for a spice label; unknown/missing sorts as Medium."""
    return SPICE_ORDER.get(str(level).strip().title(), SPICE_ORDER["Medium"])


def price_rank(level: str) -> int:
    return PRICE_ORDER.get(str(level).strip().title(), PRICE_ORDER["Medium"])
