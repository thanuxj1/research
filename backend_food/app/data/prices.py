"""Per-dish price estimates in Sri Lankan rupees.

Three numbers per dish, not one. A "current price" for Sri Lankan food does not
exist as a scalar: the same chicken kottu is Rs 700 at a roadside kade and
Rs 2,500 in a Colombo hotel. `low` is what a local eatery charges, `typical` is
the ordinary casual-restaurant price, `high` is the tourist/hotel end. The UI
shows the range, and `pricing.py` scales it further by venue tier.

`unit` is load-bearing and must never be dropped. Rs 40 for Plain Hoppers is
*per hopper*; Rs 700 for Rice and Curry is *per plate*. Rendering either number
without its unit produces a confidently wrong price.

--------------------------------------------------------------------------------
PROVENANCE - READ BEFORE TRUSTING THESE NUMBERS
--------------------------------------------------------------------------------
These are **offline estimates with a baseline of 2025-05**, not a live feed.
There is no public price API for Sri Lankan street food, so unlike the venue
layer (`places.py`, which calls Overpass/Google at request time) this table
cannot be made live by wiring up a provider. It is a curated dataset and it goes
stale.

Consequences, all handled explicitly rather than hidden:

* `PRICE_AS_OF` below drives a staleness flag. Past `FOODAI_PRICE_STALE_DAYS`
  the API marks every price `stale: true` and the UI badges it. Sri Lankan food
  prices moved sharply after 2022; a silently old price is worse than no price.
* `FOODAI_PRICE_INFLATION` applies a uniform multiplier so an operator can
  re-base the whole table without editing 155 rows.
* `confidence` is per dish. Staples sold at a fixed price everywhere (bread,
  plain tea) are `high`; market-rate seafood is `low` because it genuinely
  swings week to week.

To replace this with real data, override `FOODAI_PRICE_TABLE` with a CSV export
(`name,low,typical,high,unit,confidence`) - see `pricing.load_price_table`.
"""

from __future__ import annotations

# Baseline date for every figure below. ISO date, used for the staleness flag.
PRICE_AS_OF = "2025-05-01"
CURRENCY = "LKR"
CURRENCY_SYMBOL = "Rs"

# Multipliers applied to `typical` to estimate what a given class of venue
# charges. Keyed by the venue tiers `places.py` assigns to external POI results.
VENUE_TIER_MULTIPLIERS: dict[str, float] = {
    "street": 0.72,      # kade, pavement cart, food stall
    "bakery": 0.85,      # bakery counter, tea kiosk
    "canteen": 0.88,     # workplace/university canteen, rice-packet shop
    "casual": 1.00,      # ordinary sit-down restaurant - the baseline
    "cafe": 1.25,        # cafe, dessert bar
    "tourist": 1.65,     # tourist-facing restaurant
    "hotel": 2.40,       # hotel dining room, resort
}

DEFAULT_TIER = "casual"

# Confidence bands. "low" means the figure swings with market rates or portion
# size and should be read as an order of magnitude only.
CONFIDENCE_LEVELS = ("low", "medium", "high")

# name -> (low, typical, high, unit, confidence)
#
# `typical` is what the derived Low/Medium/High band is computed from; see
# pricing.BAND_THRESHOLDS. The one dish whose numbers disagree with the band in
# sri_lankan_food_dataset.csv is Crab Curry, documented in KNOWN_BAND_MISMATCHES.
DISH_PRICES: dict[str, tuple[int, int, int, str, str]] = {
    # ----------------------------------------------------------------- Main Meals
    "String Hoppers": (120, 200, 400, "plate of 10", "high"),
    "Plain Hoppers": (25, 40, 90, "per hopper", "high"),
    "Egg Hoppers": (70, 110, 220, "per hopper", "high"),
    "Pittu": (150, 250, 500, "portion", "medium"),
    "Kiribath": (120, 200, 400, "portion", "medium"),
    "Kadala (Chickpeas)": (80, 150, 300, "portion", "high"),
    "Boiled Manioc": (120, 200, 400, "portion", "medium"),
    "Boiled Sweet Potatoes": (120, 200, 380, "portion", "medium"),
    "Dosa": (150, 250, 550, "per dosa", "high"),
    "Pol Roti": (50, 90, 180, "per roti", "high"),
    "Kurakkan Roti": (60, 100, 200, "per roti", "high"),
    "Egg Roti": (150, 250, 480, "per roti", "high"),
    "Vegetable Roti": (90, 150, 300, "per roti", "high"),
    "Paratha": (120, 200, 400, "per paratha", "high"),
    "Puri": (90, 150, 320, "portion", "medium"),
    "Idli": (90, 150, 320, "portion", "high"),
    "Naan": (150, 250, 500, "per naan", "high"),
    "Godamba Roti": (70, 120, 240, "per roti", "high"),
    "Vegetable Noodles": (400, 650, 1300, "plate", "high"),
    "Egg Noodles": (450, 700, 1400, "plate", "high"),
    "Chicken Noodles": (600, 850, 1700, "plate", "high"),
    "Rice and Curry": (350, 700, 2200, "plate", "medium"),
    "Yellow rice": (350, 600, 1200, "portion", "medium"),
    "Rathu Kekulu Rice (Red Raw Rice)": (300, 550, 1100, "portion", "medium"),
    "Vegetable Fried Rice": (450, 700, 1400, "plate", "high"),
    "Chicken Fried Rice": (600, 900, 1800, "plate", "high"),
    "Egg Fried Rice": (500, 750, 1500, "plate", "high"),
    "Vegetable Kottu": (450, 700, 1400, "plate", "high"),
    "Chicken Kottu": (650, 950, 2000, "plate", "high"),
    "Egg Kottu": (550, 800, 1600, "plate", "high"),
    "Dolphin Kottu": (750, 1100, 2200, "plate", "medium"),
    "String Hopper kottu": (600, 900, 1800, "plate", "medium"),
    "Mixed Seafood Noodles": (1100, 1600, 3200, "plate", "medium"),
    "Lamprais (Lump Rice)": (950, 1400, 2800, "parcel", "medium"),
    "Biryani": (850, 1300, 2800, "plate", "medium"),
    "Seafood Fried Rice": (1100, 1600, 3200, "plate", "medium"),
    "Mixed Fried Rice": (900, 1300, 2600, "plate", "high"),
    "Chopsuey Rice": (900, 1300, 2600, "plate", "medium"),
    "Cheese Kottu": (950, 1400, 2800, "plate", "high"),
    "Seafood Kottu": (1250, 1800, 3600, "plate", "medium"),
    # -------------------------------------------------------------------- Curries
    "Dhal Curry": (100, 200, 450, "portion", "high"),
    "Ala Baduma (Stir-fried Potato)": (110, 200, 450, "portion", "high"),
    "Kiri Hodi": (80, 150, 350, "portion", "high"),
    "Ala Hodi (Potato White Curry)": (100, 180, 400, "portion", "high"),
    "Chicken Curry": (280, 450, 1100, "portion", "medium"),
    "Egg Curry": (150, 250, 550, "portion", "high"),
    "Fish Curry": (280, 450, 1100, "portion", "medium"),
    "Fish White Curry": (280, 450, 1100, "portion", "medium"),
    "Fish Ambul Thiyal (Sour Fish Curry)": (320, 500, 1300, "portion", "medium"),
    "Cuttlefish Curry": (350, 500, 1400, "portion", "low"),
    "Meatball Curry": (250, 400, 950, "portion", "medium"),
    "Mushroom Curry": (220, 350, 800, "portion", "medium"),
    "Soya Meat Curry": (150, 250, 550, "portion", "high"),
    "Devilled Soya Meat": (180, 300, 650, "portion", "high"),
    "Polos Curry": (180, 300, 700, "portion", "high"),
    "Kir Kos (Jackfruit Curry)": (180, 300, 700, "portion", "high"),
    "Pumpkin Curry": (110, 200, 450, "portion", "high"),
    "Beetroot Curry": (110, 200, 450, "portion", "high"),
    "Green Bean Curry": (130, 220, 500, "portion", "high"),
    "Ambarella Curry": (110, 200, 450, "portion", "medium"),
    "Kesel Muwa Curry (Banana Blossom Curry)": (150, 250, 550, "portion", "medium"),
    "Nelum Ala Curry (Lotus Root Curry)": (180, 300, 700, "portion", "low"),
    "Eggplant Curry": (150, 250, 550, "portion", "high"),
    "Devilled Chicken": (550, 850, 1800, "portion", "high"),
    "Butter Chicken Curry": (650, 950, 2000, "portion", "high"),
    "Devilled Fish": (600, 900, 1900, "portion", "medium"),
    "Devilled Cuttlefish": (750, 1100, 2400, "portion", "low"),
    "Black Pork Curry": (600, 900, 1900, "portion", "medium"),
    "Devilled Pork": (650, 950, 2000, "portion", "medium"),
    "Beef Curry": (500, 750, 1600, "portion", "medium"),
    "Devilled Beef": (600, 900, 1900, "portion", "medium"),
    "Mutton Curry": (750, 1100, 2400, "portion", "medium"),
    "Hot Butter Cuttlefish": (800, 1150, 2500, "portion", "low"),
    "Prawn Curry": (850, 1200, 2800, "portion", "low"),
    "Devilled Prawns": (850, 1200, 2800, "portion", "low"),
    "Crab Curry": (1800, 2800, 6500, "portion", "low"),
    "Cashew Nut Curry": (550, 800, 1700, "portion", "medium"),
    # ---------------------------------------------------------------- Sauces/Sides
    "Lunumiris": (60, 100, 250, "portion", "high"),
    "Seeni Sambol": (90, 150, 350, "portion", "high"),
    "Coconut Sambol": (60, 100, 250, "portion", "high"),
    "Kochchi Sambol": (70, 120, 300, "portion", "high"),
    "Wambatu Moju (Eggplant Pickle)": (150, 250, 550, "portion", "high"),
    "Gotukola Sambol (Pennywort Salad)": (90, 150, 350, "portion", "high"),
    "Mango Chutney": (120, 200, 450, "portion", "medium"),
    "Papadam": (25, 40, 90, "per piece", "high"),
    "Malay Pickle": (120, 200, 480, "portion", "medium"),
    # ---------------------------------------------------------------------- Soups
    "Vegetable Soup": (400, 600, 1300, "bowl", "high"),
    "Chicken Soup": (500, 750, 1600, "bowl", "high"),
    "Pork Soup": (580, 850, 1800, "bowl", "medium"),
    "Beef Soup": (550, 800, 1700, "bowl", "medium"),
    "Mutton Soup": (600, 900, 1900, "bowl", "medium"),
    # ----------------------------------------------------------------- Short Eats
    "Chicken Roll": (90, 140, 300, "per roll", "high"),
    "Fish Roll": (80, 130, 280, "per roll", "high"),
    "Egg Roll": (80, 130, 280, "per roll", "high"),
    "Samosa": (70, 110, 250, "per samosa", "high"),
    "Bread": (140, 180, 320, "450g loaf", "high"),
    "Roast Pan": (90, 130, 260, "loaf", "high"),
    "Sandwiches": (150, 250, 700, "per sandwich", "medium"),
    "Chicken Bun": (100, 150, 320, "per bun", "high"),
    "Fish Bun (Malu Pan)": (80, 120, 260, "per bun", "high"),
    "Sausage Bun": (100, 150, 320, "per bun", "high"),
    "Egg Bun": (90, 140, 300, "per bun", "high"),
    "Seeni Sambol Bun": (70, 110, 240, "per bun", "high"),
    "Kimbula Bun": (80, 120, 260, "per bun", "high"),
    "Fish Patties": (80, 120, 260, "per patty", "high"),
    "Chicken Patties": (90, 130, 280, "per patty", "high"),
    "Ulundhu Vadai": (40, 70, 160, "per vadai", "high"),
    "Parippu vada": (30, 50, 120, "per vadai", "high"),
    "Kola Kenda": (60, 100, 250, "cup", "medium"),
    "Omelet": (120, 200, 480, "per omelet", "high"),
    "Chicken Cutlet": (80, 120, 260, "per cutlet", "high"),
    "Fish Cutlet": (70, 110, 240, "per cutlet", "high"),
    "Vegetable Cutlet": (60, 90, 200, "per cutlet", "high"),
    # ------------------------------------------------------------------- Desserts
    "Watalappan": (220, 350, 850, "portion", "high"),
    "Curd and Treacle": (250, 400, 950, "portion", "high"),
    "Biscuit Pudding": (250, 400, 900, "portion", "medium"),
    "Caramel Pudding": (220, 350, 800, "portion", "medium"),
    "Kiri Toffee (Milk Toffee)": (35, 60, 140, "per piece", "high"),
    "Pol Toffee (Coconut Toffee)": (30, 50, 120, "per piece", "high"),
    "Thala Bola (Sesame Seed bolls)": (35, 60, 140, "per piece", "high"),
    "Thala Karali (Sesame Seed Rolls)": (35, 60, 140, "per piece", "high"),
    "Wali thalapa": (90, 150, 350, "portion", "medium"),
    "Lavariya": (60, 100, 230, "per piece", "high"),
    "Helapa": (60, 100, 230, "per piece", "high"),
    "Aggala": (30, 50, 120, "per piece", "medium"),
    "Aluwa": (40, 70, 160, "per piece", "high"),
    "Athirasa": (55, 90, 200, "per piece", "high"),
    "Kevum (Oil Cake)": (50, 80, 190, "per piece", "high"),
    "Aasmi": (60, 100, 230, "per piece", "medium"),
    "Kokis": (40, 70, 160, "per piece", "high"),
    "Dosi": (150, 250, 600, "100g", "low"),
    "Pani Walalu": (55, 90, 200, "per piece", "high"),
    "Kalu Dodol": (320, 500, 1200, "250g", "medium"),
    "Coconut Cake": (90, 150, 380, "slice", "medium"),
    "Butter Cake": (150, 250, 600, "slice", "high"),
    "Ribbon Cake": (150, 250, 600, "slice", "high"),
    "Jaggery": (250, 400, 900, "250g", "medium"),
    # --------------------------------------------------------------------- Drinks
    "Ceylon Coffee": (150, 250, 700, "cup", "high"),
    "Iced Coffee": (300, 450, 1100, "glass", "high"),
    "Ceylon Tea": (50, 100, 400, "cup", "high"),
    "Green Tea": (90, 150, 500, "cup", "high"),
    "Iced Tea": (220, 350, 900, "glass", "high"),
    "Milk Tea": (70, 120, 450, "cup", "high"),
    "Masala chai": (150, 250, 700, "cup", "medium"),
    "Thambili (King Coconut)": (90, 150, 400, "per nut", "high"),
    "Koththamalli": (50, 100, 300, "cup", "high"),
    "Ginger Beer": (120, 200, 450, "bottle", "high"),
    "Lemonade": (150, 250, 650, "glass", "high"),
    "Soya Milk": (90, 150, 350, "carton", "high"),
    "Bubble Tea": (600, 850, 1600, "cup", "medium"),
    "Mango Lassi": (400, 600, 1300, "glass", "medium"),
    "Avocado Juice": (450, 650, 1400, "glass", "medium"),
    "Falooda": (450, 650, 1400, "glass", "medium"),
    "Hot Chocolate": (400, 600, 1400, "cup", "medium"),
    # --------------------------------------------------------------------- Snacks
    "Spicy Cashew": (1100, 1500, 3000, "250g", "medium"),
}

# Dishes whose numeric `typical` lands in a different band than the
# `price_range` column of sri_lankan_food_dataset.csv.
#
# Crab Curry is recorded as Medium, but crab is sold at market rate and a
# portion is realistically Rs 1,800-6,500 - solidly High. This mirrors the
# spice disagreement already documented in the README: the structured column
# stays authoritative for ranking, and the disagreement is surfaced rather
# than silently reconciled. `tests/test_pricing.py` pins this set exactly, so
# any *new* drift fails the suite.
KNOWN_BAND_MISMATCHES: frozenset[str] = frozenset({"Crab Curry"})
