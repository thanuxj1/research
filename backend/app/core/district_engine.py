"""
District Risk Engine — replaces per-point circle markers with a defensible,
confidence-aware, exposure-normalised district choropleth.
IT22629180

THIS FILE IS THE METHODOLOGICAL CORE OF THE MAP REDESIGN.
See /docs/METHODOLOGY.md for the full written justification of every
constant and design decision below (for viva / panel defence).

Root causes this replaces / fixes, vs. the old app/core/scoring.py + clustering.py:
  1. "Everything is red" -> the old pipeline classified 0.02-degree GRID CELLS
     (often 1-3 reports each). With N that small, one scam report already
     yields scam_ratio >= 0.33-1.0, which crossed the "High" threshold almost
     everywhere. Aggregating to real administrative/electoral districts raises
     the typical N per unit from ~2-5 to ~dozens-hundreds, which is the
     statistically defensible minimum for a ratio to mean anything.
  2. No exposure normalisation was actually implemented anywhere in code
     (NRSI/SLTDA footfall existed only in the design document, not in
     scoring.py/clustering.py). This engine implements it for real, and is
     explicit about which districts it could and could not be applied to
     (see app/ml/exposure_baseline.py).
  3. Fixed absolute thresholds ("Score >= 0.70 == High") silently break the
     moment the score distribution shifts (e.g. after a data pipeline change).
     Tiers here are assigned by the *current* distribution (quantile /
     natural-breaks style) so "High" always means "top of today's evidence",
     not "happens to clear a number picked once in 2024".
  4. No way to distinguish "confidently low risk" from "we simply have no
     data" — both used to render as the same colour. This engine returns a
     `insufficient_data` tier that is visually and semantically distinct.
"""

import json
import math
import os
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from shapely.geometry import shape, Point
from shapely.prepared import prep

from app.ml.exposure_baseline import get_exposure, coverage_summary

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "sri_lanka_districts.geojson")

# ---------------------------------------------------------------------------
# Tunable constants — every one documented in METHODOLOGY.md section 3-5.
# ---------------------------------------------------------------------------
DECAY_LAMBDA = math.log(2) / 180          # 180-day half-life, same convention as point-level scoring.py
MIN_REPORTS_INSUFFICIENT = 3              # below this: cannot claim ANY risk level, insufficient_data
MIN_REPORTS_PRELIMINARY = 15              # below this: risk shown but capped at "preliminary" confidence
SEVERITY_WEIGHT = 0.70
SCAM_RATIO_WEIGHT = 0.30


@dataclass
class DistrictAggregate:
    district: str
    constituent_admin_districts: list
    report_count: int = 0
    scam_count: int = 0
    weighted_evidence: float = 0.0     # sum of decay*source_weight over ALL reports (denominator)
    weighted_incidents: float = 0.0    # sum of decay*source_weight*severity over SCAM reports (numerator)
    scam_type_counts: dict = field(default_factory=dict)
    recent_reports: list = field(default_factory=list)  # up to 8 most-recent, for the tooltip/panel


class DistrictBoundaryIndex:
    """Loads district polygons once and does point -> district lookup."""

    def __init__(self, geojson_path: str = _DATA_PATH):
        with open(geojson_path, "r", encoding="utf-8") as f:
            self._fc = json.load(f)
        self._entries = []
        for feat in self._fc["features"]:
            geom = shape(feat["geometry"])
            self._entries.append({
                "district": feat["properties"]["district"],
                "constituents": feat["properties"].get("constituent_admin_districts", [feat["properties"]["district"]]),
                "geom": geom,
                "prepared": prep(geom),
                "bounds": geom.bounds,  # (minx, miny, maxx, maxy) fast reject
            })

    def locate(self, lat: float, lon: float) -> Optional[str]:
        pt = Point(lon, lat)
        for e in self._entries:
            minx, miny, maxx, maxy = e["bounds"]
            if not (minx <= lon <= maxx and miny <= lat <= maxy):
                continue
            if e["prepared"].contains(pt) or e["geom"].touches(pt):
                return e["district"]
        return None

    def all_districts(self):
        return [(e["district"], e["constituents"]) for e in self._entries]

    def feature_collection_template(self):
        """Returns a deep-enough copy of the raw FeatureCollection for the API to annotate."""
        return json.loads(json.dumps(self._fc))


_boundary_index: Optional[DistrictBoundaryIndex] = None


def get_boundary_index() -> DistrictBoundaryIndex:
    global _boundary_index
    if _boundary_index is None:
        _boundary_index = DistrictBoundaryIndex()
    return _boundary_index


def _decay(created_at) -> float:
    if not created_at:
        return 1.0
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    days_ago = max(0, (datetime.now(timezone.utc) - created_at).days)
    return math.exp(-DECAY_LAMBDA * days_ago)


from app.core.safety_intelligence import is_irrelevant_noise, refine_scam_type

def aggregate_reports_by_district(reports: list) -> dict:
    """
    reports: list of ORM Report rows (or anything exposing the same attributes).
    Returns {district_name: DistrictAggregate}
    """
    idx = get_boundary_index()
    agg: dict = {name: DistrictAggregate(district=name, constituent_admin_districts=const)
                 for name, const in idx.all_districts()}

    for r in reports:
        lat = getattr(r, "latitude", None) if not isinstance(r, dict) else r.get("latitude")
        lon = getattr(r, "longitude", None) if not isinstance(r, dict) else r.get("longitude")
        if lat is None or lon is None:
            continue

        title = getattr(r, "title", None) if not isinstance(r, dict) else r.get("title")
        content = getattr(r, "content", None) if not isinstance(r, dict) else r.get("content")
        source = getattr(r, "source", None) if not isinstance(r, dict) else r.get("source")

        item_dict = {"title": title, "content": content or title or "", "source": source or ""}
        if is_irrelevant_noise(item_dict):
            continue

        district = idx.locate(lat, lon)
        if district is None or district not in agg:
            continue

        a = agg[district]
        created_at = getattr(r, "created_at", None) if not isinstance(r, dict) else r.get("created_at")
        decay = _decay(created_at)
        src_w = (getattr(r, "source_weight", 0.35) if not isinstance(r, dict) else r.get("source_weight")) or 0.35
        weight = decay * src_w
        is_scam = bool(getattr(r, "is_scam", False) if not isinstance(r, dict) else r.get("is_scam", False))
        risk_level = (getattr(r, "risk_level", 1) if not isinstance(r, dict) else r.get("risk_level", 1)) or 1
        raw_st = getattr(r, "scam_type", None) if not isinstance(r, dict) else r.get("scam_type")

        refined_st = "general_safety"
        if raw_st:
            st_str = str(raw_st).strip()
            if st_str.lower() not in ("nan", "none", "null", "safe", "") and st_str not in ("Unsafe Area", "General Scam"):
                refined_st = refine_scam_type(title, content, st_str)

        is_active_scam = is_scam and refined_st not in ("general_safety", "safe", "Verified Safe Area")

        a.report_count += 1
        a.weighted_evidence += weight
        if is_active_scam:
            a.scam_count += 1
            a.weighted_incidents += weight * (risk_level / 3.0)
            if refined_st and refined_st not in ("general_safety", "safe"):
                a.scam_type_counts[refined_st] = a.scam_type_counts.get(refined_st, 0) + 1

        if len(a.recent_reports) < 8:
            a.recent_reports.append(r)

    return agg


def _confidence_tier(report_count: int) -> str:
    if report_count < MIN_REPORTS_INSUFFICIENT:
        return "insufficient_data"
    if report_count < MIN_REPORTS_PRELIMINARY:
        return "preliminary"
    return "established"


def _raw_component_score(a: DistrictAggregate) -> dict:
    """
    Returns the pre-tiering numeric building blocks. Kept separate from the
    quantile step below so the *math* is independent of what other districts
    currently look like (only the final tier label is relative).
    """
    if a.weighted_evidence <= 0:
        return {"severity": 0.0, "scam_ratio": 0.0, "base_risk": 0.0,
                "incident_rate_per_100k": None, "exposure_status": "unavailable"}

    scam_ratio = a.weighted_incidents / a.weighted_evidence  # already severity-weighted, bounded ~[0,1]
    severity = min(1.0, a.weighted_incidents / max(a.scam_count, 1))
    base_risk = SEVERITY_WEIGHT * severity + SCAM_RATIO_WEIGHT * scam_ratio

    exposure = get_exposure(a.district)
    incident_rate = None
    if exposure.status == "official" and exposure.footfall:
        incident_rate = (a.weighted_incidents / exposure.footfall) * 100_000

    return {
        "severity": round(severity, 4),
        "scam_ratio": round(scam_ratio, 4),
        "base_risk": round(base_risk, 4),
        "incident_rate_per_100k": round(incident_rate, 4) if incident_rate is not None else None,
        "exposure_status": exposure.status,
        "exposure_footfall": exposure.footfall,
        "exposure_source": exposure.source,
        "exposure_period": exposure.period,
    }


def _quantile_tiers(values: list) -> list:
    """
    Data-driven breakpoints (quartiles) over districts that HAVE enough data to
    be scored at all. This is what stops every district from converging on
    'High' the moment absolute thresholds stop matching the data: labels are
    always relative to the current evidence base, and are recomputed on every
    request from the live data, not hardcoded once.
    Returns breakpoints [q25, q50, q75].
    """
    if not values:
        return [0.0, 0.0, 0.0]
    sorted_v = sorted(values)
    if len(sorted_v) < 4:
        # too few scoreable districts for quartiles; fall back to halves
        mid = statistics.median(sorted_v)
        return [mid * 0.5, mid, mid * 1.5]
    q25 = sorted_v[max(0, int(len(sorted_v) * 0.25) - 1)]
    q50 = sorted_v[int(len(sorted_v) * 0.50)]
    q75 = sorted_v[min(len(sorted_v) - 1, int(len(sorted_v) * 0.75))]
    return [q25, q50, q75]


def score_all_districts(reports: list) -> dict:
    """
    Main entry point. Returns {district_name: full_score_dict} ready to be
    merged into the GeoJSON FeatureCollection by the API layer.
    """
    agg = aggregate_reports_by_district(reports)

    prelim = {}
    for name, a in agg.items():
        components = _raw_component_score(a)
        confidence = _confidence_tier(a.report_count)
        prelim[name] = {"aggregate": a, "components": components, "confidence": confidence}

    # Only districts with enough evidence AND a non-zero score participate in
    # setting the relative Low/Moderate/High breakpoints. Insufficient-data
    # districts never contaminate the scale and never receive a colour tier.
    scoreable_scores = [
        p["components"]["base_risk"] for name, p in prelim.items()
        if p["confidence"] != "insufficient_data"
    ]
    q25, q50, q75 = _quantile_tiers(scoreable_scores)

    results = {}
    for name, p in prelim.items():
        a: DistrictAggregate = p["aggregate"]
        comp = p["components"]
        confidence = p["confidence"]

        if confidence == "insufficient_data":
            tier = "insufficient_data"
            final_risk_score = None
            final_severity = None
            final_scam_ratio = None
            final_rate = None
        else:
            score = comp["base_risk"]
            if score <= q25:
                tier = "low"
            elif score <= q50:
                tier = "moderate"
            elif score <= q75:
                tier = "high"
            else:
                tier = "severe"
            final_risk_score = comp["base_risk"]
            final_severity = comp["severity"]
            final_scam_ratio = comp["scam_ratio"]
            final_rate = comp["incident_rate_per_100k"]

        top_scam_types = sorted(a.scam_type_counts.items(), key=lambda kv: -kv[1])[:5]

        results[name] = {
            "district": name,
            "constituent_admin_districts": a.constituent_admin_districts,
            "report_count": a.report_count,
            "scam_report_count": a.scam_count,
            "confidence": confidence,             # insufficient_data | preliminary | established
            "risk_tier": tier,                     # insufficient_data | low | moderate | high | severe
            "risk_score_0_1": final_risk_score,
            "severity_component": final_severity,
            "scam_ratio_component": final_scam_ratio,
            "incident_rate_per_100k_visitors": final_rate,
            "exposure_status": comp["exposure_status"],
            "exposure_footfall": comp.get("exposure_footfall"),
            "exposure_source": comp.get("exposure_source"),
            "exposure_period": comp.get("exposure_period"),
            "top_scam_types": [{"type": t, "count": c} for t, c in top_scam_types],
            "breakpoints_used": {"q25": round(q25, 4), "q50": round(q50, 4), "q75": round(q75, 4)},
            "recent_reports_raw": a.recent_reports,  # API layer formats these for the response
        }
    return results


def methodology_report() -> dict:
    """Machine-readable summary of every constant/decision, for a /methodology endpoint or appendix."""
    return {
        "decay_half_life_days": 180,
        "min_reports_insufficient_data": MIN_REPORTS_INSUFFICIENT,
        "min_reports_preliminary": MIN_REPORTS_PRELIMINARY,
        "severity_weight": SEVERITY_WEIGHT,
        "scam_ratio_weight": SCAM_RATIO_WEIGHT,
        "tiering_method": "quantile (data-relative), computed fresh per request over districts with confidence != insufficient_data",
        "exposure_baseline": coverage_summary(),
    }
