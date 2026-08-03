"""
Exposure Baseline Registry — solves the "Denominator Problem" for district scoring.
IT22629180

WHY THIS FILE EXISTS
---------------------
Raw incident counts are meaningless on their own: a district with 40 reports and
2 million tourist visits is objectively SAFER than a district with 10 reports and
20,000 visits. Without a visitor-volume denominator, every popular destination
looks "high risk" simply because popularity generates more reports (both good
and bad). This is the exposure bias problem.

The only authoritative denominator available is SLTDA's telecom-inbound-presence
footfall series (Jan-Oct 2024). SLTDA has NOT published this figure for every
district. We do not fabricate numbers for the missing ones — a fabricated
denominator would be scientifically worse than no denominator at all, and would
not survive a viva/panel cross-examination.

Instead:
  - Districts WITH a published SLTDA figure get `exposure_status = "official"`
    and a full normalised incident rate (NRSI-eligible).
  - Districts WITHOUT one get `exposure_status = "unavailable"`. Their score is
    still computed (see district_engine.py) but is explicitly flagged as
    "density-only, not exposure-normalised" and is capped at a lower confidence
    tier so the UI and any reviewer can see the methodological limitation at a
    glance rather than have it silently hidden inside a single blended number.

Update this table when SLTDA publishes a fuller series. Every entry carries its
source and reporting window so provenance is auditable.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ExposureRecord:
    district: str
    footfall: Optional[int]          # telecom-inbound-presence count, SLTDA period
    source: str
    period: str
    status: str                       # "official" | "unavailable"


# Figures as published in the project's SLTDA 2025 exposure dataset
# (Jan-Oct 2024 telecom inbound presence). Keyed by canonical district name
# used in sri_lanka_districts.geojson -> properties.district
_SLTDA_FOOTFALL_JAN_OCT_2024 = {
    "Colombo":    4_193_342,
    "Galle":      2_671_580,
    "Gampaha":    2_100_780,
    "Kandy":      1_722_666,
    "Matale":     1_249_150,
    "Kalutara":   1_181_326,
    "Matara":     1_170_772,
    "Badulla":      818_133,
}

_SOURCE = "Sri Lanka Tourism Development Authority (SLTDA) — Telecommunication Inbound Presence Dataset"
_PERIOD = "Jan-Oct 2024"

# All 22 district polygons used by this build (see sri_lanka_districts.geojson).
# "Vanni (Mannar/Vavuniya/Mullaitivu)" is a merged electoral-district polygon;
# it is intentionally left without a footfall figure until SLTDA (or DCS) publish
# a disaggregated number for that combined region.
_ALL_DISTRICTS = [
    "Ampara", "Anuradhapura", "Badulla", "Batticaloa", "Colombo", "Galle",
    "Gampaha", "Hambantota", "Jaffna", "Kalutara", "Kandy", "Kegalle",
    "Kurunegala", "Vanni (Mannar/Vavuniya/Mullaitivu)", "Matale", "Matara",
    "Monaragala", "Nuwara Eliya", "Polonnaruwa", "Puttalam", "Ratnapura",
    "Trincomalee",
]

EXPOSURE_REGISTRY: dict[str, ExposureRecord] = {}
for _d in _ALL_DISTRICTS:
    _footfall = _SLTDA_FOOTFALL_JAN_OCT_2024.get(_d)
    EXPOSURE_REGISTRY[_d] = ExposureRecord(
        district=_d,
        footfall=_footfall,
        source=_SOURCE if _footfall else "not published by SLTDA at this administrative level",
        period=_PERIOD if _footfall else "n/a",
        status="official" if _footfall else "unavailable",
    )


def get_exposure(district: str) -> ExposureRecord:
    return EXPOSURE_REGISTRY.get(
        district,
        ExposureRecord(district=district, footfall=None, source="unknown district", period="n/a", status="unavailable"),
    )


def coverage_summary() -> dict:
    """Used by /districts/methodology to state coverage plainly, e.g. for a viva."""
    official = [d for d, r in EXPOSURE_REGISTRY.items() if r.status == "official"]
    unavailable = [d for d, r in EXPOSURE_REGISTRY.items() if r.status == "unavailable"]
    return {
        "total_districts": len(EXPOSURE_REGISTRY),
        "with_official_sltda_footfall": official,
        "without_official_footfall": unavailable,
        "coverage_ratio": round(len(official) / len(EXPOSURE_REGISTRY), 3),
    }
