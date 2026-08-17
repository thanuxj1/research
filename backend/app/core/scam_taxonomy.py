"""
Canonical Scam Type Taxonomy — SafeTravel LK
IT22629180

Single source of truth for all scam/incident category keys.
All modules that emit or consume a scam_type must use these values.

Previously there were four incompatible vocabularies across:
  - nlp_pipeline.py  (SCAM_TAXONOMY keys: "Gem Scam", "Tuk Tuk Scam", …)
  - district_engine.py (severity branch: "harassment", "unsafe_area", "gem_scam")
  - refine_scam_type() (returns: "Price Gouging", "commission_shop", "general_safety")
  - CSV ingestion (field: "Tuk-Tuk / Transport Scam")
  - DEMOGRAPHIC_WEIGHTS (another set)

This module defines the canonical lowercase_underscore keys.
Use DISPLAY_NAMES for any user-facing label.
"""

from typing import FrozenSet

# ── Canonical incident-type keys ──────────────────────────────────────────────
CANONICAL_SCAM_TYPES: FrozenSet[str] = frozenset({
    "gem_scam",            # fake/overpriced gems, sapphires, jewellery investment
    "tuk_tuk_scam",        # overcharging, meter refusal, commission detours
    "overcharging",        # tourist-price menus, inflated entry fees, services
    "fake_guide",          # unlicensed guides, fake monks, donation soliciting
    "transport_fraud",     # airport taxi scams, route diversions, tampered meters
    "accommodation_scam",  # bait-and-switch listings, unreported charges
    "food_scam",           # hidden menu prices, surprise bills, no-menu pricing
    "harassment",          # sexual harassment, stalking, groping, physical threats
    "theft",               # pickpocket, bag snatch, robbery
    "unsafe_area",         # documented danger zones, police advisories
    "general_safety",      # catch-all for lower-confidence / advisory records
})

# ── Display names (user-facing, title-cased) ──────────────────────────────────
DISPLAY_NAMES: dict[str, str] = {
    "gem_scam":            "Gem & Jewellery Scam",
    "tuk_tuk_scam":        "Tuk-Tuk / Transport Scam",
    "overcharging":        "Price Gouging / Overcharging",
    "fake_guide":          "Unlicensed Guide Scam",
    "transport_fraud":     "Transport & Taxi Fraud",
    "accommodation_scam":  "Accommodation Fraud",
    "food_scam":           "Food & Menu Scam",
    "harassment":          "Tourist Harassment / Assault",
    "theft":               "Theft & Robbery",
    "unsafe_area":         "Unsafe Area Advisory",
    "general_safety":      "General Safety Advisory",
}

# ── Legacy-to-canonical mapping ───────────────────────────────────────────────
# Use this to normalise values from old DB records, CSVs, or collectors
LEGACY_MAP: dict[str, str] = {
    # nlp_pipeline SCAM_TAXONOMY keys (Title Case with spaces)
    "Gem Scam":             "gem_scam",
    "Gem & Jewelry Scam":   "gem_scam",
    "Commission Shop":      "tuk_tuk_scam",  # commission scams are transport-adjacent
    "Tuk Tuk Scam":         "tuk_tuk_scam",
    "Overcharging":         "overcharging",
    "Price Gouging":        "overcharging",
    "Fake Guide":           "fake_guide",
    "Unlicensed Guide Scam":"fake_guide",
    "Transport Fraud":      "transport_fraud",
    "Accommodation Scam":   "accommodation_scam",
    "Food/Menu Scam":       "food_scam",
    "Theft / Robbery":      "theft",
    "Theft":                "theft",
    "Physical Assault":     "harassment",   # physical danger → harassment bucket
    "Harassment":           "harassment",
    "Tourist Harassment":   "harassment",
    "Accident / Hazard":    "unsafe_area",
    "Health / Hygiene":     "general_safety",
    "Unsafe Area":          "unsafe_area",
    "General Scam":         "general_safety",
    "General Tourist Safety":"general_safety",
    "Safety Advisory":      "general_safety",
    "Safety Advisory (Non-Incident)": "general_safety",
    # CSV field values
    "Tuk-Tuk / Transport Scam": "tuk_tuk_scam",
    "commission_shop":      "tuk_tuk_scam",
    "fake_guide":           "fake_guide",
    "harassment":           "harassment",
    "unsafe_area":          "unsafe_area",
    "gem_scam":             "gem_scam",
    "general_safety":       "general_safety",
    "safe":                 "general_safety",
}


def normalise(raw: str | None) -> str:
    """Return the canonical key for any raw scam_type value. Defaults to 'general_safety'."""
    if not raw:
        return "general_safety"
    stripped = str(raw).strip()
    if stripped in CANONICAL_SCAM_TYPES:
        return stripped
    return LEGACY_MAP.get(stripped, "general_safety")


def display(canonical_key: str) -> str:
    """Return the user-facing display name for a canonical key."""
    return DISPLAY_NAMES.get(canonical_key, canonical_key.replace("_", " ").title())
