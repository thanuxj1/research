"""Mapping dishes to the kinds of place that actually sell them.

The problem this file solves: **no external POI database knows which dishes a
venue serves.** Overpass and Google Places return categories - `amenity=restaurant`,
`shop=bakery`, `cuisine=sri_lankan` - and occasionally a name. Nothing anywhere
says "this place does a good kottu". So a naive "restaurants near you" list
attached to a dessert is not merely imprecise, it is misleading: Aluwa is not
sold in restaurants, it is sold in sweet shops and by roadside vendors.

Each dish therefore gets a profile of *where to look*, and every returned venue
carries an honest confidence level saying why it was included:

  named    - the venue's own name contains the dish (a "Kottu" in the name)
  cuisine  - the venue's `cuisine` tag matches the dish's cuisine
  category - only the venue class matches: bakeries plausibly sell buns

The UI renders those three differently. Presenting a `category` guess with the
same authority as a `named` hit is the failure mode worth avoiding here.

Profiles are derived from the dish's category and tags, with per-dish keyword
overrides for the iconic dishes whose names appear on signboards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# OSM selectors, as (key, value) pairs. Passed straight into Overpass QL and
# mapped to Google `includedTypes` by places.py.
RESTAURANT = ("amenity", "restaurant")
FAST_FOOD = ("amenity", "fast_food")
CAFE = ("amenity", "cafe")
BAKERY = ("shop", "bakery")
CONFECTIONERY = ("shop", "confectionery")
PASTRY = ("shop", "pastry")
CONVENIENCE = ("shop", "convenience")
SUPERMARKET = ("shop", "supermarket")
GREENGROCER = ("shop", "greengrocer")
DELI = ("shop", "deli")
ICE_CREAM = ("amenity", "ice_cream")
FOOD_COURT = ("amenity", "food_court")
MARKETPLACE = ("amenity", "marketplace")
TEA_SHOP = ("shop", "tea")
COFFEE_SHOP = ("shop", "coffee")
BEVERAGES = ("shop", "beverages")
STREET_VENDOR = ("amenity", "vending_machine")  # rarely tagged; harmless extra

# Which venue classes a category is worth searching, in rough order of likelihood.
CATEGORY_SELECTORS: dict[str, tuple[tuple[str, str], ...]] = {
    "Main Meals": (RESTAURANT, FAST_FOOD, FOOD_COURT, CAFE),
    "Curries": (RESTAURANT, FAST_FOOD, FOOD_COURT),
    "Short Eats": (BAKERY, FAST_FOOD, CAFE, CONVENIENCE, PASTRY),
    "Soups": (RESTAURANT, CAFE, FOOD_COURT),
    "Sauces & Sides": (RESTAURANT, SUPERMARKET, MARKETPLACE, GREENGROCER),
    "Desserts": (BAKERY, CONFECTIONERY, CAFE, PASTRY, ICE_CREAM, SUPERMARKET),
    "Drinks": (CAFE, RESTAURANT, TEA_SHOP, COFFEE_SHOP, BEVERAGES, FAST_FOOD),
    "Snacks": (CONVENIENCE, SUPERMARKET, CONFECTIONERY, MARKETPLACE),
}

DEFAULT_SELECTORS: tuple[tuple[str, str], ...] = (RESTAURANT, FAST_FOOD, CAFE)

# Venue tiers (see pricing.VENUE_TIER_MULTIPLIERS) a category is typically sold
# at. Used to pick which tier's price estimate to show against a venue when the
# venue's own class is ambiguous.
CATEGORY_TIERS: dict[str, tuple[str, ...]] = {
    "Main Meals": ("street", "canteen", "casual"),
    "Curries": ("canteen", "casual"),
    "Short Eats": ("bakery", "street"),
    "Soups": ("casual",),
    "Sauces & Sides": ("canteen", "casual"),
    "Desserts": ("bakery", "cafe"),
    "Drinks": ("street", "cafe"),
    "Snacks": ("street", "bakery"),
}

# `cuisine=` values worth matching, per category. OSM cuisine tagging in Sri
# Lanka is sparse and inconsistent, so these are a bonus signal, never a filter.
CATEGORY_CUISINES: dict[str, tuple[str, ...]] = {
    "Main Meals": ("sri_lankan", "srilankan", "local", "asian", "indian", "rice"),
    "Curries": ("sri_lankan", "srilankan", "local", "indian", "curry"),
    "Short Eats": ("sri_lankan", "srilankan", "local", "bakery", "sandwich"),
    "Soups": ("sri_lankan", "srilankan", "asian", "chinese", "soup"),
    "Sauces & Sides": ("sri_lankan", "srilankan", "local"),
    "Desserts": ("dessert", "cake", "ice_cream", "sri_lankan", "srilankan", "bakery"),
    "Drinks": ("coffee_shop", "tea", "juice", "cafe", "bubble_tea"),
    "Snacks": ("sri_lankan", "srilankan", "local"),
}

# Dish-name keywords that realistically appear on a Sri Lankan signboard, keyed
# by dish. A hit upgrades a venue's confidence to `named`. Spelling variants
# matter: kottu is signposted kottu, kotthu, koththu and kothu.
NAME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "String Hoppers": ("string hopper", "idiyappam", "indiappa"),
    "Plain Hoppers": ("hopper", "appa", "appam"),
    "Egg Hoppers": ("egg hopper", "hopper", "appa"),
    "Pittu": ("pittu", "puttu"),
    "Kiribath": ("kiribath", "milk rice"),
    "Dosa": ("dosa", "dosai", "thosai"),
    "Idli": ("idli", "iddly"),
    "Naan": ("naan", "tandoor"),
    "Paratha": ("paratha", "parotta"),
    "Puri": ("puri", "poori"),
    "Godamba Roti": ("roti", "rotti"),
    "Pol Roti": ("pol roti", "coconut roti", "roti"),
    "Kurakkan Roti": ("kurakkan", "roti"),
    "Egg Roti": ("egg roti", "roti"),
    "Vegetable Roti": ("roti", "rotti"),
    "Rice and Curry": ("rice and curry", "rice & curry", "bath", "hotel", "canteen"),
    "Yellow rice": ("yellow rice", "kaha bath"),
    "Rathu Kekulu Rice (Red Raw Rice)": ("red rice", "kekulu"),
    "Lamprais (Lump Rice)": ("lamprais", "lump rice", "dutch burgher"),
    "Biryani": ("biryani", "biriyani", "buriyani"),
    "Vegetable Kottu": ("kottu", "kotthu", "koththu", "kothu"),
    "Chicken Kottu": ("kottu", "kotthu", "koththu", "kothu"),
    "Egg Kottu": ("kottu", "kotthu", "koththu", "kothu"),
    "Cheese Kottu": ("kottu", "kotthu", "koththu", "kothu"),
    "Seafood Kottu": ("kottu", "kotthu", "koththu", "kothu"),
    "Dolphin Kottu": ("kottu", "kotthu", "koththu", "kothu"),
    "String Hopper kottu": ("kottu", "kotthu", "koththu"),
    "Vegetable Fried Rice": ("fried rice", "chinese", "wok"),
    "Chicken Fried Rice": ("fried rice", "chinese", "wok"),
    "Egg Fried Rice": ("fried rice", "chinese", "wok"),
    "Seafood Fried Rice": ("fried rice", "seafood", "chinese"),
    "Mixed Fried Rice": ("fried rice", "chinese"),
    "Chopsuey Rice": ("chopsuey", "chop suey", "chinese"),
    "Vegetable Noodles": ("noodles", "chinese"),
    "Egg Noodles": ("noodles", "chinese"),
    "Chicken Noodles": ("noodles", "chinese"),
    "Mixed Seafood Noodles": ("seafood", "noodles"),
    "Crab Curry": ("crab", "seafood", "ministry of crab"),
    "Prawn Curry": ("prawn", "seafood"),
    "Devilled Prawns": ("prawn", "devilled", "seafood"),
    "Cuttlefish Curry": ("cuttlefish", "seafood"),
    "Devilled Cuttlefish": ("cuttlefish", "devilled", "seafood"),
    "Hot Butter Cuttlefish": ("hot butter", "cuttlefish", "seafood"),
    "Fish Ambul Thiyal (Sour Fish Curry)": ("ambul thiyal", "fish", "seafood"),
    "Fish Curry": ("fish", "seafood"),
    "Black Pork Curry": ("pork", "black pork"),
    "Mutton Curry": ("mutton",),
    "Chicken Roll": ("roll", "short eats", "bakery"),
    "Fish Roll": ("roll", "short eats", "bakery"),
    "Egg Roll": ("roll", "short eats", "bakery"),
    "Samosa": ("samosa", "samoosa"),
    "Bread": ("bakery", "bakers", "bread"),
    "Roast Pan": ("bakery", "bakers", "bread"),
    "Chicken Bun": ("bun", "bakery", "bakers"),
    "Fish Bun (Malu Pan)": ("malu pan", "bun", "bakery"),
    "Sausage Bun": ("bun", "bakery"),
    "Egg Bun": ("bun", "bakery"),
    "Seeni Sambol Bun": ("bun", "bakery"),
    "Kimbula Bun": ("kimbula", "bun", "bakery"),
    "Fish Patties": ("patties", "bakery"),
    "Chicken Patties": ("patties", "bakery"),
    "Ulundhu Vadai": ("vadai", "vada", "wade"),
    "Parippu vada": ("vadai", "vada", "wade", "parippu"),
    "Chicken Cutlet": ("cutlet", "bakery"),
    "Fish Cutlet": ("cutlet", "bakery"),
    "Vegetable Cutlet": ("cutlet", "bakery"),
    "Kola Kenda": ("kola kenda", "kenda", "ayurveda"),
    "Kadala (Chickpeas)": ("kadala", "chickpea"),
    "Watalappan": ("watalappan", "wattalappam", "watalappam"),
    "Curd and Treacle": ("curd", "kiri", "meekiri", "treacle"),
    "Kalu Dodol": ("dodol", "kalu dodol"),
    "Aluwa": ("aluwa", "sweet"),
    "Kevum (Oil Cake)": ("kevum", "kavum", "sweet"),
    "Kokis": ("kokis", "sweet"),
    "Athirasa": ("athirasa", "sweet"),
    "Pani Walalu": ("pani walalu", "sweet"),
    "Aasmi": ("aasmi", "sweet"),
    "Thala Bola (Sesame Seed bolls)": ("thala", "sesame"),
    "Thala Karali (Sesame Seed Rolls)": ("thala", "sesame"),
    "Kiri Toffee (Milk Toffee)": ("milk toffee", "toffee"),
    "Pol Toffee (Coconut Toffee)": ("coconut toffee", "toffee"),
    "Butter Cake": ("cake", "bakery", "bakers"),
    "Ribbon Cake": ("cake", "bakery", "bakers"),
    "Coconut Cake": ("cake", "bakery"),
    "Biscuit Pudding": ("pudding", "cake", "bakery"),
    "Caramel Pudding": ("pudding", "bakery"),
    "Jaggery": ("jaggery", "hakuru"),
    "Lavariya": ("lavariya", "sweet"),
    "Helapa": ("helapa", "sweet"),
    "Falooda": ("falooda", "faluda"),
    "Mango Lassi": ("lassi", "juice"),
    "Avocado Juice": ("juice", "fresh juice"),
    "Bubble Tea": ("bubble tea", "boba"),
    "Ceylon Tea": ("tea", "tea shop", "tea centre", "tea center"),
    "Green Tea": ("tea", "tea shop"),
    "Iced Tea": ("tea", "cafe"),
    "Milk Tea": ("tea", "tea shop", "kade"),
    "Masala chai": ("chai", "tea"),
    "Ceylon Coffee": ("coffee", "cafe"),
    "Iced Coffee": ("coffee", "cafe"),
    "Hot Chocolate": ("cafe", "chocolate"),
    "Thambili (King Coconut)": ("thambili", "king coconut", "coconut"),
    "Koththamalli": ("koththamalli", "ayurveda", "herbal"),
    "Ginger Beer": ("ginger beer", "elephant house"),
    "Spicy Cashew": ("cashew", "kaju"),
    "Papadam": ("papadam", "pappadam"),
    "Omelet": ("omelet", "omelette", "kade"),
    "Sandwiches": ("sandwich", "deli", "cafe"),
}

# Dishes that are essentially never sold on their own - they arrive as part of a
# rice-and-curry plate. Saying so is more useful than listing restaurants and
# implying you can walk in and order a bowl of Lunumiris.
ACCOMPANIMENT_ONLY: frozenset[str] = frozenset(
    {
        "Lunumiris",
        "Seeni Sambol",
        "Coconut Sambol",
        "Kochchi Sambol",
        "Gotukola Sambol (Pennywort Salad)",
        "Mango Chutney",
        "Papadam",
        "Malay Pickle",
        "Wambatu Moju (Eggplant Pickle)",
        "Kiri Hodi",
        "Ala Hodi (Potato White Curry)",
    }
)

ACCOMPANIMENT_NOTE = (
    "Usually served as part of a rice-and-curry plate rather than ordered on its "
    "own - look for it at the places below."
)


@dataclass(frozen=True)
class VenueProfile:
    """Where to look for one dish, and how to judge what comes back."""

    dish: str
    category: str
    selectors: tuple[tuple[str, str], ...]
    cuisines: frozenset[str]
    name_patterns: tuple[re.Pattern[str], ...]
    keywords: tuple[str, ...]
    tiers: tuple[str, ...]
    accompaniment_only: bool = False
    note: str | None = None

    @property
    def cache_key(self) -> str:
        """Two dishes searching identical selectors share one upstream call.

        Keyed on the selectors rather than the dish, so all 22 Short Eats issue a
        single Overpass request instead of 22 near-identical ones.
        """
        return "|".join(f"{k}={v}" for k, v in self.selectors)

    def name_confidence(self, venue_name: str) -> bool:
        """Does the venue's name mention this dish?"""
        lowered = (venue_name or "").lower()
        return any(pattern.search(lowered) for pattern in self.name_patterns)

    def cuisine_confidence(self, cuisines: tuple[str, ...]) -> bool:
        return bool(self.cuisines & {c.strip().lower() for c in cuisines})


def _compile_keywords(keywords: tuple[str, ...]) -> tuple[re.Pattern[str], ...]:
    """Word-boundary anchored, like every other matcher in this codebase.

    Substring matching here would put every venue containing "tea" - "Steakhouse",
    "Tea Gardens Instant Loans" - against Ceylon Tea.
    """
    return tuple(
        re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)") for keyword in keywords
    )


_PROFILE_CACHE: dict[str, VenueProfile] = {}


def profile_for(dish: object) -> VenueProfile:
    """Build (and memoise) the venue profile for a `corpus.Dish`.

    Typed loosely so this module stays independent of `corpus`; only `.name`,
    `.category` and `.tags` are read.
    """
    name = str(getattr(dish, "name", "") or "")
    cached = _PROFILE_CACHE.get(name)
    if cached is not None:
        return cached

    category = str(getattr(dish, "category", "") or "")
    tags = set(getattr(dish, "tags", ()) or ())

    selectors = list(CATEGORY_SELECTORS.get(category, DEFAULT_SELECTORS))
    cuisines = set(CATEGORY_CUISINES.get(category, ()))

    # Tag-driven additions. Seafood is worth its own cuisine value because Sri
    # Lankan coastal restaurants do tag it.
    if {"seafood", "fish", "prawn", "crab"} & tags:
        cuisines.add("seafood")
    if "beverage" in tags or category == "Drinks":
        cuisines.update({"juice", "tea", "coffee_shop"})
    if "dessert" in tags or category == "Desserts":
        cuisines.update({"dessert", "cake"})

    keywords = NAME_KEYWORDS.get(name, ())
    if not keywords:
        # Fall back to the distinctive words of the dish's own name, dropping
        # generic ones that would match half the map.
        generic = {
            "curry", "rice", "fried", "boiled", "mixed", "hot", "sweet", "and",
            "with", "the", "soup", "juice", "milk", "vegetable", "devilled",
        }
        parts = [w for w in re.findall(r"[a-z]+", name.lower()) if len(w) > 3]
        keywords = tuple(w for w in parts if w not in generic)[:3]

    accompaniment = name in ACCOMPANIMENT_ONLY

    profile = VenueProfile(
        dish=name,
        category=category,
        selectors=tuple(dict.fromkeys(selectors)),
        cuisines=frozenset(c.lower() for c in cuisines),
        name_patterns=_compile_keywords(keywords),
        keywords=keywords,
        tiers=CATEGORY_TIERS.get(category, ("casual",)),
        accompaniment_only=accompaniment,
        note=ACCOMPANIMENT_NOTE if accompaniment else None,
    )
    _PROFILE_CACHE[name] = profile
    return profile
