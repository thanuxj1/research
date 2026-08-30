import csv
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

logger = logging.getLogger(__name__)

DEFAULT_METADATA_CSV_PATH = Path(__file__).resolve().parent / "data_source_metadata.csv"

_METADATA_CACHE: Optional[Dict[str, dict]] = None

BASELINE_RELIABILITY = {
    "official": 100.0,
    "verified": 90.0,
    "research_benchmark": 75.0,
    "estimated": 60.0,
    "fallback": 40.0,
    "unknown": 20.0
}

DEFAULT_COMPONENT_WEIGHTS = {
    "route": 0.15,
    "fuel": 0.15,
    "hotel": 0.15,
    "food": 0.10,
    "attractions": 0.15,
    "public_transport": 0.10,
    "schedule": 0.10,
    "recommendation": 0.10
}


def load_data_source_metadata(csv_path: Optional[Union[str, Path]] = None) -> Dict[str, dict]:
    """Load component data source metadata dataset into memory cache."""
    global _METADATA_CACHE
    target_path = Path(csv_path) if csv_path else DEFAULT_METADATA_CSV_PATH

    if not target_path.exists():
        logger.warning(f"Data source metadata file missing at: {target_path}. Using fallback metadata.")
        return _get_fallback_metadata_map()

    metadata_map: Dict[str, dict] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            comp = row.get("component", "").strip().lower()
            if not comp:
                continue

            try:
                refresh_days = int(row.get("refresh_interval_days", 30))
            except ValueError:
                refresh_days = 30

            try:
                reliability = float(row.get("reliability_score", 75.0))
            except ValueError:
                reliability = 75.0

            metadata_map[comp] = {
                "component": comp,
                "source_type": row.get("source_type", "research_benchmark").strip(),
                "source_name": row.get("source_name", "Research Benchmark Estimate").strip(),
                "effective_date": row.get("effective_date", "2026").strip(),
                "last_updated": row.get("last_updated", "2026-08-01").strip(),
                "refresh_interval_days": refresh_days,
                "reliability_score": reliability,
                "notes": row.get("notes", "").strip()
            }

    _METADATA_CACHE = metadata_map
    return metadata_map


def _get_fallback_metadata_map() -> Dict[str, dict]:
    components = ["route", "fuel", "hotel", "food", "attractions", "public_transport", "schedule", "budget_model", "route_model"]
    fb = {}
    for c in components:
        fb[c] = {
            "component": c,
            "source_type": "research_benchmark",
            "source_name": "Research Benchmark Estimate",
            "effective_date": "2026",
            "last_updated": "2026-08-01",
            "refresh_interval_days": 30,
            "reliability_score": 75.0,
            "notes": "Research benchmark data fallback"
        }
    return fb


def classify_data_source(source_type: str) -> dict:
    """Classify a data source type into standardized baseline metadata attributes."""
    st_clean = source_type.strip().lower() if source_type else "unknown"
    if st_clean not in BASELINE_RELIABILITY:
        st_clean = "unknown"

    rel_score = BASELINE_RELIABILITY[st_clean]

    if st_clean == "official":
        ver_status = "official_government_or_regulatory"
        conf_level = "high"
    elif st_clean == "verified":
        ver_status = "independently_verified"
        conf_level = "high"
    elif st_clean == "research_benchmark":
        ver_status = "benchmark"
        conf_level = "medium"
    elif st_clean == "estimated":
        ver_status = "algorithmically_estimated"
        conf_level = "medium"
    elif st_clean == "fallback":
        ver_status = "system_fallback"
        conf_level = "low"
    else:
        ver_status = "unverified"
        conf_level = "very_low"

    return {
        "source_type": st_clean,
        "baseline_reliability_score": rel_score,
        "verification_status": ver_status,
        "default_confidence_level": conf_level
    }


def calculate_data_freshness_score(
    last_updated: str,
    refresh_interval_days: int,
    current_date: Optional[str] = None
) -> dict:
    """Calculate deterministic freshness score (0-100) and status based on date elapsed."""
    if not last_updated:
        return {
            "freshness_score": 30.0,
            "freshness_status": "unknown",
            "days_since_update": None,
            "refresh_interval_days": refresh_interval_days
        }

    try:
        updated_dt = datetime.strptime(last_updated, "%Y-%m-%d").date()
    except ValueError:
        return {
            "freshness_score": 30.0,
            "freshness_status": "unknown",
            "days_since_update": None,
            "refresh_interval_days": refresh_interval_days
        }

    if current_date:
        try:
            now_dt = datetime.strptime(current_date, "%Y-%m-%d").date()
        except ValueError:
            now_dt = date(2026, 8, 22)
    else:
        now_dt = date(2026, 8, 22)

    days_elapsed = (now_dt - updated_dt).days

    if days_elapsed < 0:
        # Future date edge case
        return {
            "freshness_score": 100.0,
            "freshness_status": "fresh",
            "days_since_update": 0,
            "refresh_interval_days": refresh_interval_days
        }

    interval = max(1, refresh_interval_days)

    if days_elapsed <= interval:
        status = "fresh"
        score = 100.0 - ((days_elapsed / interval) * 20.0)
    elif days_elapsed <= interval * 2:
        status = "aging"
        score = 80.0 - (((days_elapsed - interval) / interval) * 30.0)
    else:
        status = "stale"
        over_days = days_elapsed - (interval * 2)
        score = max(0.0, 50.0 - (over_days * 0.5))

    return {
        "freshness_score": round(max(0.0, min(100.0, score)), 2),
        "freshness_status": status,
        "days_since_update": days_elapsed,
        "refresh_interval_days": interval
    }


def calculate_source_reliability_score(source_type: str, custom_reliability: Optional[float] = None) -> float:
    """Calculate deterministic source reliability score."""
    if custom_reliability is not None and 0 <= custom_reliability <= 100:
        return round(float(custom_reliability), 2)
    classification = classify_data_source(source_type)
    return round(classification["baseline_reliability_score"], 2)


def get_confidence_level_label(score: float) -> str:
    """Classify confidence score into categorical levels."""
    if score >= 80.0:
        return "high"
    elif score >= 60.0:
        return "medium"
    elif score >= 40.0:
        return "low"
    else:
        return "very_low"


def calculate_component_confidence(
    component: str,
    metadata: dict,
    current_date: Optional[str] = None
) -> dict:
    """Calculate comprehensive confidence metrics for a component.
    
    Formula: confidence_score = (freshness_score * 0.40) + (reliability_score * 0.60)
    """
    source_type = metadata.get("source_type", "research_benchmark")
    source_name = metadata.get("source_name", "Research Benchmark Estimate")
    last_updated = metadata.get("last_updated", "2026-08-01")
    refresh_days = metadata.get("refresh_interval_days", 30)
    rel_custom = metadata.get("reliability_score")

    freshness_res = calculate_data_freshness_score(last_updated, refresh_days, current_date)
    f_score = freshness_res["freshness_score"]
    r_score = calculate_source_reliability_score(source_type, rel_custom)

    conf_score = round((f_score * 0.40) + (r_score * 0.60), 2)
    conf_level = get_confidence_level_label(conf_score)

    return {
        "component": component,
        "source_type": source_type,
        "source_name": source_name,
        "freshness_score": f_score,
        "reliability_score": r_score,
        "confidence_score": conf_score,
        "confidence_level": conf_level,
        "effective_date": metadata.get("effective_date", "2026"),
        "last_updated": last_updated,
        "freshness_status": freshness_res["freshness_status"],
        "days_since_update": freshness_res["days_since_update"]
    }


def calculate_overall_confidence(
    component_confidences: Dict[str, dict],
    is_public_transport_used: bool = False
) -> dict:
    """Calculate overall weighted confidence score across active trip components."""
    active_weights = dict(DEFAULT_COMPONENT_WEIGHTS)

    if not is_public_transport_used and "public_transport" in active_weights:
        pt_weight = active_weights.pop("public_transport")
        remaining_sum = sum(active_weights.values())
        if remaining_sum > 0:
            for k in active_weights:
                active_weights[k] = active_weights[k] + (active_weights[k] / remaining_sum) * pt_weight

    total_weight = 0.0
    weighted_score_sum = 0.0
    comp_scores: Dict[str, float] = {}

    for comp, weight in active_weights.items():
        comp_data = component_confidences.get(comp)
        if comp_data:
            c_score = comp_data["confidence_score"]
            weighted_score_sum += c_score * weight
            total_weight += weight
            comp_scores[comp] = c_score

    overall_score = round(weighted_score_sum / total_weight, 2) if total_weight > 0 else 75.0
    overall_level = get_confidence_level_label(overall_score)

    lowest_comp = min(comp_scores.keys(), key=lambda k: comp_scores[k]) if comp_scores else "unknown"
    highest_comp = max(comp_scores.keys(), key=lambda k: comp_scores[k]) if comp_scores else "unknown"

    return {
        "overall_confidence_score": overall_score,
        "confidence_level": overall_level,
        "components_evaluated": len(comp_scores),
        "lowest_confidence_component": lowest_comp,
        "highest_confidence_component": highest_comp
    }


def build_data_provenance(
    components_used: Optional[List[str]] = None,
    current_date: Optional[str] = None
) -> dict:
    """Build complete data provenance dictionary for system components."""
    meta_map = load_data_source_metadata()
    target_comps = components_used or ["route", "fuel", "hotel", "food", "attractions", "schedule"]

    provenance = {}
    for comp in target_comps:
        comp_meta = meta_map.get(comp, {
            "source_type": "research_benchmark",
            "source_name": "Research Benchmark Estimate",
            "last_updated": "2026-08-01",
            "refresh_interval_days": 30,
            "reliability_score": 75.0,
            "effective_date": "2026"
        })
        comp_conf = calculate_component_confidence(comp, comp_meta, current_date)
        provenance[comp] = comp_conf

    return {"data_provenance": provenance}


def build_confidence_summary(
    components_confidence: Dict[str, dict],
    overall: dict
) -> dict:
    """Build deterministic confidence summary dictionary with contextual warnings."""
    warnings: List[str] = []

    stale_comps = [c for c, data in components_confidence.items() if data.get("freshness_status") == "stale"]
    benchmark_comps = [c for c, data in components_confidence.items() if data.get("source_type") == "research_benchmark"]

    if "hotel" in benchmark_comps:
        warnings.append("Hotel prices are based on research benchmark data and may vary depending on booking date and availability.")

    if "fuel" in benchmark_comps:
        warnings.append("Fuel costs are estimated from national fuel price benchmark averages.")

    for c in stale_comps:
        warnings.append(f"{c.capitalize()} data may be outdated and should be verified before booking.")

    if overall["confidence_level"] in ("low", "very_low"):
        warnings.append(f"Overall recommendation confidence is {overall['confidence_level']} and should be independently verified.")

    return {
        "overall_confidence_score": overall["overall_confidence_score"],
        "confidence_level": overall["confidence_level"],
        "lowest_confidence_component": overall["lowest_confidence_component"],
        "highest_confidence_component": overall["highest_confidence_component"],
        "components_evaluated": overall["components_evaluated"],
        "stale_data_components": stale_comps,
        "benchmark_data_components": benchmark_comps,
        "warnings": warnings
    }


def validate_data_freshness(metadata_map: Optional[Dict[str, dict]] = None) -> dict:
    """Validate completeness and date validity of data source metadata map."""
    target_map = metadata_map if metadata_map is not None else load_data_source_metadata()
    warnings: List[str] = []
    today = date(2026, 8, 22)

    for comp, meta in target_map.items():
        last_up = meta.get("last_updated")
        if not last_up:
            warnings.append(f"Component '{comp}' is missing last_updated date.")
            continue

        try:
            up_dt = datetime.strptime(last_up, "%Y-%m-%d").date()
            if up_dt > today:
                warnings.append(f"Component '{comp}' has a future last_updated date ({last_up}).")
        except ValueError:
            warnings.append(f"Component '{comp}' has invalid date format '{last_up}'. Expected YYYY-MM-DD.")

        rel = meta.get("reliability_score", 0)
        if rel < 0 or rel > 100:
            warnings.append(f"Component '{comp}' has invalid reliability score {rel}.")

    is_valid = len(warnings) == 0
    return {
        "valid": is_valid,
        "warnings": warnings
    }
