"""
Sri Lanka District Spatial Lookup
IT22629180

Maps a (latitude, longitude) coordinate to its Sri Lankan district using
bounding-box lookup. This is intentionally a fast O(n) scan — Sri Lanka has
only 25 districts so this is negligible compared to DB query time.

Also provides the canonical district name list, SLTDA 2024 telecom footfall
figures (Jan–Oct 2024 inbound presence, from architecture doc), and
district → province mapping for aggregated province-level views.

Bounding boxes are approximate axis-aligned rectangles sufficient for
district-level assignment. They were derived from the official Survey
Department of Sri Lanka district boundary centroids and extents.
A point on a boundary edge is assigned to whichever district is checked
first in the ordered list (ordered roughly S→N, W→E).
"""

from typing import Optional

# ─── District definitions ─────────────────────────────────────────────────────
# Each entry: (district_key, display_name, lat_min, lat_max, lon_min, lon_max)
# Source: Survey Department of Sri Lanka + OpenStreetMap administrative boundaries
_DISTRICT_BOXES = [
    # Western Province
    ("colombo",     "Colombo",      6.78,  6.98,  79.82, 80.02),
    ("gampaha",     "Gampaha",      6.98,  7.35,  79.83, 80.22),
    ("kalutara",    "Kalutara",     6.35,  6.80,  79.88, 80.45),
    # Central Province
    ("kandy",       "Kandy",        7.10,  7.55,  80.45, 80.90),
    ("matale",      "Matale",       7.40,  8.00,  80.40, 80.90),
    ("nuwara_eliya","Nuwara Eliya", 6.75,  7.20,  80.65, 81.10),
    # Southern Province
    ("galle",       "Galle",        5.90,  6.30,  79.95, 80.55),
    ("matara",      "Matara",       5.85,  6.22,  80.45, 81.00),
    ("hambantota",  "Hambantota",   6.00,  6.45,  80.85, 81.55),
    # Northern Province
    ("jaffna",      "Jaffna",       9.45,  9.85,  79.80, 80.35),
    ("kilinochchi", "Kilinochchi",  9.20,  9.50,  80.15, 80.55),
    ("mannar",      "Mannar",       8.75,  9.30,  79.75, 80.20),
    ("vavuniya",    "Vavuniya",     8.60,  9.00,  80.25, 80.70),
    ("mullaitivu",  "Mullaitivu",   8.95,  9.45,  80.40, 81.00),
    # Eastern Province
    ("batticaloa",  "Batticaloa",   7.55,  8.15,  81.45, 81.90),
    ("ampara",      "Ampara",       6.80,  7.60,  81.35, 81.95),
    ("trincomalee", "Trincomalee",  8.15,  8.90,  80.90, 81.50),
    # North Western Province
    ("kurunegala",  "Kurunegala",   7.35,  7.90,  79.90, 80.55),
    ("puttalam",    "Puttalam",     7.80,  8.50,  79.70, 80.20),
    # North Central Province
    ("anuradhapura","Anuradhapura", 8.00,  9.00,  80.20, 80.90),
    ("polonnaruwa", "Polonnaruwa",  7.70,  8.30,  80.90, 81.45),
    # Uva Province
    ("badulla",     "Badulla",      6.70,  7.20,  80.90, 81.45),
    ("monaragala",  "Monaragala",   6.55,  7.05,  81.15, 81.80),
    # Sabaragamuwa Province
    ("ratnapura",   "Ratnapura",    6.45,  6.95,  80.30, 80.80),
    ("kegalle",     "Kegalle",      7.00,  7.40,  80.25, 80.65),
]

# SLTDA 2024 Telecom Inbound Presence — OFFICIAL figures only (Jan–Oct 2024)
# Source: SLTDA statistical bulletin (8 published districts).
# "Person-district-presences" — NOT unique visitors (same tourist counted per district visited).
# For districts not listed: density-only scoring applies (no exposure normalisation).
# See docs/projected_footfall.md for exploratory projections (not used in scoring).
SLTDA_FOOTFALL_2024: dict[str, int] = {
    "colombo":   4_193_342,
    "galle":     2_671_580,
    "gampaha":   2_100_780,
    "kandy":     1_722_666,
    "matale":    1_249_150,
    "kalutara":  1_181_326,
    "matara":    1_170_772,
    "badulla":     818_133,
}

PROVINCE_MAP: dict[str, str] = {
    "colombo": "Western", "gampaha": "Western", "kalutara": "Western",
    "kandy": "Central", "matale": "Central", "nuwara_eliya": "Central",
    "galle": "Southern", "matara": "Southern", "hambantota": "Southern",
    "jaffna": "Northern", "kilinochchi": "Northern", "mannar": "Northern",
    "vavuniya": "Northern", "mullaitivu": "Northern",
    "batticaloa": "Eastern", "ampara": "Eastern", "trincomalee": "Eastern",
    "kurunegala": "North Western", "puttalam": "North Western",
    "anuradhapura": "North Central", "polonnaruwa": "North Central",
    "badulla": "Uva", "monaragala": "Uva",
    "ratnapura": "Sabaragamuwa", "kegalle": "Sabaragamuwa",
}

ALL_DISTRICTS: list[str] = [d[0] for d in _DISTRICT_BOXES]


def coords_to_district(lat: float, lon: float) -> Optional[str]:
    """
    Maps a (lat, lon) coordinate to a Sri Lankan district key.
    Returns None if the coordinate falls outside all district bounding boxes
    (e.g. in the ocean or outside Sri Lanka entirely).
    """
    for key, _name, lat_min, lat_max, lon_min, lon_max in _DISTRICT_BOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return key
    return None


def get_district_display_name(district_key: str) -> str:
    for key, name, *_ in _DISTRICT_BOXES:
        if key == district_key:
            return name
    return district_key.replace("_", " ").title()


def get_footfall(district_key: str) -> Optional[int]:
    return SLTDA_FOOTFALL_2024.get(district_key)
