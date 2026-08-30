"""City coordinates and a small fallback venue list.

Two separate things live here.

**`SRI_LANKA_CITIES`** backs the city picker. It is served by `GET /cities` and
the client renders it, rather than shipping its own copy - the same reason
`GET /conditions` exists. City centroids are public geographic facts and are
accurate enough for a "search near this city" radius.

**`SEED_VENUES`** is a *degradation path*, not a database. It is used only when
the live provider (Overpass or Google) errors or times out, so that the UI can
show something plausible instead of an empty list that reads as "nothing near
you". Every entry carries `approximate: true` and `source: "seed"`, the client
badges it as unverified, and - importantly - map links for seed venues are
generated as a **name search rather than a coordinate pin**, so the user's own
map app resolves the real location instead of trusting an approximate one from
here. Sending someone to a wrong pin is worse than making them tap once more.

These are well-known establishments, but coordinates are neighbourhood-level and
neither opening hours nor continued existence is verified. The live providers are
the source of truth; this is a courtesy.
"""

from __future__ import annotations

# name, latitude, longitude, district
SRI_LANKA_CITIES: tuple[tuple[str, float, float, str], ...] = (
    ("Colombo", 6.9271, 79.8612, "Colombo"),
    ("Dehiwala-Mount Lavinia", 6.8410, 79.8730, "Colombo"),
    ("Sri Jayawardenepura Kotte", 6.8940, 79.9180, "Colombo"),
    ("Moratuwa", 6.7730, 79.8820, "Colombo"),
    ("Negombo", 7.2083, 79.8358, "Gampaha"),
    ("Gampaha", 7.0917, 79.9999, "Gampaha"),
    ("Kalutara", 6.5854, 79.9607, "Kalutara"),
    ("Kandy", 7.2906, 80.6337, "Kandy"),
    ("Matale", 7.4675, 80.6234, "Matale"),
    ("Nuwara Eliya", 6.9497, 80.7891, "Nuwara Eliya"),
    ("Hatton", 6.8913, 80.5956, "Nuwara Eliya"),
    ("Galle", 6.0535, 80.2210, "Galle"),
    ("Hikkaduwa", 6.1395, 80.1063, "Galle"),
    ("Unawatuna", 5.9997, 80.2494, "Galle"),
    ("Matara", 5.9549, 80.5550, "Matara"),
    ("Mirissa", 5.9483, 80.4590, "Matara"),
    ("Tangalle", 6.0240, 80.7940, "Hambantota"),
    ("Hambantota", 6.1246, 81.1185, "Hambantota"),
    ("Ella", 6.8667, 81.0466, "Badulla"),
    ("Badulla", 6.9895, 81.0550, "Badulla"),
    ("Ratnapura", 6.6828, 80.3992, "Ratnapura"),
    ("Kurunegala", 7.4863, 80.3623, "Kurunegala"),
    ("Anuradhapura", 8.3114, 80.4037, "Anuradhapura"),
    ("Polonnaruwa", 7.9403, 81.0188, "Polonnaruwa"),
    ("Dambulla", 7.8600, 80.6517, "Matale"),
    ("Sigiriya", 7.9570, 80.7603, "Matale"),
    ("Trincomalee", 8.5874, 81.2152, "Trincomalee"),
    ("Batticaloa", 7.7170, 81.7000, "Batticaloa"),
    ("Ampara", 7.2970, 81.6820, "Ampara"),
    ("Arugam Bay", 6.8400, 81.8340, "Ampara"),
    ("Jaffna", 9.6615, 80.0255, "Jaffna"),
    ("Vavuniya", 8.7514, 80.4971, "Vavuniya"),
    ("Mannar", 8.9810, 79.9040, "Mannar"),
    ("Puttalam", 8.0362, 79.8283, "Puttalam"),
    ("Chilaw", 7.5758, 79.7953, "Puttalam"),
)

# name, lat, lon, tier, kind, city, cuisines, note
SEED_VENUES: tuple[tuple[str, float, float, str, str, str, tuple[str, ...], str], ...] = (
    # ------------------------------------------------------------- Colombo
    (
        "Ministry of Crab", 6.9344, 79.8428, "tourist", "restaurant", "Colombo",
        ("seafood", "sri_lankan"), "Old Dutch Hospital precinct, Fort",
    ),
    (
        "Upali's by Nawaloka", 6.9157, 79.8578, "casual", "restaurant", "Colombo",
        ("sri_lankan",), "Sri Lankan menu, Colombo 07",
    ),
    (
        "Raja Bojun", 6.9330, 79.8434, "tourist", "restaurant", "Colombo",
        ("sri_lankan",), "Sri Lankan buffet, Fort",
    ),
    (
        "Hotel De Pilawoos", 6.8952, 79.8570, "street", "fast_food", "Colombo",
        ("sri_lankan",), "Late-night kottu, Colombo 04",
    ),
    (
        "Nana's", 6.9271, 79.8437, "street", "fast_food", "Colombo",
        ("sri_lankan",), "Galle Face Green stalls",
    ),
    (
        "Galle Face Green food stalls", 6.9271, 79.8425, "street", "marketplace", "Colombo",
        ("sri_lankan",), "Evening street food along the promenade",
    ),
    (
        "Green Cabin", 6.9088, 79.8543, "casual", "restaurant", "Colombo",
        ("sri_lankan",), "Rice and curry, short eats, Colombo 03",
    ),
    (
        "Chinese Dragon Cafe", 6.9007, 79.8556, "casual", "restaurant", "Colombo",
        ("chinese", "asian"), "Fried rice, noodles, kottu",
    ),
    (
        "Beach Wadiya", 6.8737, 79.8590, "casual", "restaurant", "Colombo",
        ("seafood",), "Beachside seafood, Wellawatte",
    ),
    (
        "Shanmugas", 6.8790, 79.8617, "casual", "restaurant", "Colombo",
        ("indian", "vegetarian"), "South Indian, Wellawatte",
    ),
    (
        "Perera & Sons", 6.9147, 79.8615, "bakery", "bakery", "Colombo",
        ("bakery",), "Bakery chain - short eats, buns, cakes",
    ),
    (
        "Fab", 6.8996, 79.8586, "bakery", "bakery", "Colombo",
        ("bakery", "cake"), "Bakery and cafe, Colombo 04",
    ),
    (
        "Cargills Food City", 6.9200, 79.8600, "canteen", "supermarket", "Colombo",
        (), "Supermarket chain - packaged snacks and sweets",
    ),
    # --------------------------------------------------------------- Kandy
    (
        "Balaji Dosai", 7.2930, 80.6350, "casual", "restaurant", "Kandy",
        ("indian", "vegetarian"), "Dosa and idli",
    ),
    (
        "Devon Restaurant & Bakery", 7.2920, 80.6340, "bakery", "bakery", "Kandy",
        ("bakery", "sri_lankan"), "Short eats and sweets",
    ),
    (
        "Kandy Muslim Hotel", 7.2937, 80.6362, "street", "restaurant", "Kandy",
        ("sri_lankan",), "Biryani and rice",
    ),
    (
        "The Empire Cafe", 7.2955, 80.6410, "cafe", "cafe", "Kandy",
        ("cafe", "coffee_shop"), "Cafe near the lake",
    ),
    # ---------------------------------------------------------------- Galle
    (
        "Lucky Fort Restaurant", 6.0280, 80.2160, "casual", "restaurant", "Galle",
        ("sri_lankan",), "Rice and curry buffet, Galle Fort",
    ),
    (
        "Pedlar's Inn Cafe", 6.0270, 80.2170, "cafe", "cafe", "Galle",
        ("cafe", "coffee_shop"), "Pedlar Street, Galle Fort",
    ),
    # -------------------------------------------------------------- Jaffna
    (
        "Malayan Cafe", 9.6640, 80.0090, "casual", "restaurant", "Jaffna",
        ("indian", "vegetarian"), "Traditional vegetarian, banana-leaf service",
    ),
    (
        "Rio Ice Cream", 9.6620, 80.0210, "cafe", "ice_cream", "Jaffna",
        ("ice_cream", "dessert"), "Ice cream and falooda",
    ),
    # ---------------------------------------------------------------- Other
    (
        "Lords Restaurant", 7.2100, 79.8380, "tourist", "restaurant", "Negombo",
        ("sri_lankan", "seafood"), "Tourist-facing, Negombo",
    ),
    (
        "Cafe Chill", 6.8670, 81.0460, "tourist", "restaurant", "Ella",
        ("sri_lankan", "asian"), "Main street, Ella",
    ),
    (
        "Grand Hotel", 6.9690, 80.7660, "hotel", "restaurant", "Nuwara Eliya",
        ("sri_lankan", "international"), "Colonial hotel dining and high tea",
    ),
    (
        "Milano Restaurant", 6.9700, 80.7700, "casual", "restaurant", "Nuwara Eliya",
        ("sri_lankan",), "Rice and curry, short eats",
    ),
    (
        "Anna Pooram Vegetarian Restaurant", 8.5730, 81.2330, "casual", "restaurant",
        "Trincomalee", ("indian", "vegetarian"), "South Indian vegetarian",
    ),
    (
        "Mango Mango", 7.8600, 80.6517, "casual", "restaurant", "Dambulla",
        ("sri_lankan", "indian"), "On the Kandy road",
    ),
    (
        "Rice & Curry canteens, Pettah market", 6.9370, 79.8560, "canteen", "food_court",
        "Colombo", ("sri_lankan",), "Cheap rice-packet canteens around the market",
    ),
)
