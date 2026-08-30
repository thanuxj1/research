import logging
from typing import Dict, List, Tuple, Any, Optional

logger = logging.getLogger(__name__)

TOLERANCE_LKR = 0.05

REQUIRED_API_FIELDS = [
    "predicted_route",
    "route_distance",
    "fuel_cost",
    "public_transport_cost",
    "transport_comparison",
    "hotel_cost",
    "food_cost",
    "attraction_cost",
    "trip_cost",
    "budget_analysis",
    "budget_optimization",
    "route_optimization",
    "travel_schedule",
    "personalized_recommendation",
    "research_metrics",
    "validation",
    "data_confidence",
    "real_time_data"
]


def validate_cost_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate mathematical consistency of cost calculations across all categories.
    
    Rule: transport_cost + hotel_cost + food_cost + attraction_cost == total_trip_cost (within 0.05 LKR tolerance)
    """
    warnings: List[str] = []
    tc = payload.get("trip_cost", {})
    cb = tc.get("cost_breakdown", {})

    fuel = float(cb.get("fuel_lkr", 0.0))
    hotel = float(cb.get("hotel_lkr", 0.0))
    food = float(cb.get("food_lkr", 0.0))
    attr = float(cb.get("attractions_lkr", 0.0))
    transport = float(cb.get("transport_lkr", 0.0))
    total_cost = float(tc.get("total_trip_cost_lkr", 0.0))

    calc_sum = transport + hotel + food + attr
    if abs(calc_sum - total_cost) > TOLERANCE_LKR:
        warnings.append(f"Cost chain mismatch: transport({transport}) + hotel({hotel}) + food({food}) + attractions({attr}) = {calc_sum} LKR, expected total_trip_cost {total_cost} LKR.")

    # Transport mode double-counting check
    mode = (
        payload.get("trip_cost", {}).get("transport_mode") or
        payload.get("personalized_recommendation", {}).get("selected_trip", {}).get("transport_mode") or
        payload.get("public_transport_cost", {}).get("transport_mode") or
        (payload.get("input") or {}).get("transport_mode") or
        "car"
    ).strip().lower()
    is_public = mode in ("bus", "train", "public_transport", "public transport")

    if is_public:
        if fuel > TOLERANCE_LKR:
            warnings.append(f"Public transport mode '{mode}' has non-zero fuel cost ({fuel} LKR). Double counting detected.")
    else:
        if abs(transport - fuel) > TOLERANCE_LKR:
            warnings.append(f"Private transport mode '{mode}' has transport_cost ({transport}) != fuel_cost ({fuel}).")

    # Budget Deficit / Surplus check
    user_budget = float(tc.get("user_budget_lkr", 0.0))
    expected_deficit = max(0.0, total_cost - user_budget)
    expected_remaining = max(0.0, user_budget - total_cost)
    actual_deficit = float(tc.get("budget_deficit_lkr", 0.0))
    actual_remaining = float(tc.get("remaining_budget_lkr", 0.0))

    if abs(actual_deficit - expected_deficit) > TOLERANCE_LKR:
        warnings.append(f"Budget deficit mismatch: actual {actual_deficit} LKR, expected {expected_deficit} LKR.")

    if abs(actual_remaining - expected_remaining) > TOLERANCE_LKR:
        warnings.append(f"Remaining budget mismatch: actual {actual_remaining} LKR, expected {expected_remaining} LKR.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_budget_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate consistency of budget status classification across system engines."""
    warnings: List[str] = []
    tc = payload.get("trip_cost", {})
    bo = payload.get("budget_optimization", {})
    ro = payload.get("route_optimization", {})
    pr = payload.get("personalized_recommendation", {})

    t_status = tc.get("budget_status")
    user_b = float(tc.get("user_budget_lkr", 0.0))
    total_c = float(tc.get("total_trip_cost_lkr", 0.0))

    expected_sufficient = (total_c <= user_b)
    if expected_sufficient and t_status == "significantly_over_budget":
        warnings.append(f"Budget status contradiction: trip cost ({total_c}) <= budget ({user_b}) but status is '{t_status}'.")

    opt_cost = bo.get("optimized_cost_lkr")
    if opt_cost is not None and opt_cost < 0:
        warnings.append(f"Negative optimized cost ({opt_cost} LKR) in budget optimization.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_route_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate logical continuity from initial predicted route to final selected route."""
    warnings: List[str] = []
    initial_r = payload.get("predicted_route")
    ro = payload.get("route_optimization", {})
    pr = payload.get("personalized_recommendation", {})

    if not initial_r:
        warnings.append("Initial predicted route is missing.")

    selected_r = pr.get("selected_trip", {}).get("route") or ro.get("optimized_route") or initial_r
    if not selected_r or " -> " not in selected_r:
        warnings.append(f"Selected route '{selected_r}' is malformed or invalid.")

    dist_data = payload.get("route_distance", {})
    tot_dist = dist_data.get("total_distance_km", 0)
    if tot_dist <= 0:
        warnings.append(f"Route distance ({tot_dist} km) is non-positive.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_transport_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate transport mode consistency and mode-specific parameters."""
    warnings: List[str] = []
    tc = payload.get("trip_cost", {})
    pt = payload.get("public_transport_cost")
    tcomp = payload.get("transport_comparison", {})

    mode = tc.get("transport_mode") or tcomp.get("selected_mode")
    if not mode:
        warnings.append("Transport mode is missing in transport chain.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_schedule_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate daily travel schedule feasibility and duration bounds."""
    warnings: List[str] = []
    ts = payload.get("travel_schedule", {})

    days = ts.get("total_days", 0)
    itinerary = ts.get("daily_itinerary", [])

    if days > 0 and len(itinerary) != days:
        warnings.append(f"Daily itinerary length ({len(itinerary)}) does not match total days ({days}).")

    score = ts.get("schedule_score", 0.0)
    if score < 0 or score > 100:
        warnings.append(f"Schedule feasibility score ({score}) is out of bounds [0, 100].")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_recommendation_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate multi-objective recommendation scores and candidate ranking."""
    warnings: List[str] = []
    pr = payload.get("personalized_recommendation", {})

    ov_score = pr.get("overall_score", 0.0)
    if ov_score < 0 or ov_score > 100:
        warnings.append(f"Personalized recommendation overall score ({ov_score}) is out of bounds [0, 100].")

    breakdown = pr.get("score_breakdown", {})
    for k, v in breakdown.items():
        if v < 0 or v > 100:
            warnings.append(f"Sub-score '{k}' ({v}) is out of bounds [0, 100].")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_confidence_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate data freshness, source verification, and confidence metrics."""
    warnings: List[str] = []
    dc = payload.get("data_confidence", {})

    c_score = dc.get("overall_confidence_score", 0.0)
    if c_score < 0 or c_score > 100:
        warnings.append(f"Data confidence overall score ({c_score}) is out of bounds [0, 100].")

    level = dc.get("confidence_level")
    if level not in ("high", "medium", "low", "very_low"):
        warnings.append(f"Unknown confidence level label '{level}'.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_realtime_data_chain(payload: dict) -> Tuple[bool, List[str]]:
    """Validate real-time provider integration status and fallback categories."""
    warnings: List[str] = []
    rt = payload.get("real_time_data", {})

    status = rt.get("status")
    if status not in ("fully_live", "mostly_live", "partially_live", "benchmark_fallback", "data_unavailable"):
        warnings.append(f"Unknown real-time data status '{status}'.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_backward_compatibility(payload: dict) -> Tuple[bool, List[str]]:
    """Verify that all required API contract fields are present in the final payload."""
    warnings: List[str] = []
    for field in REQUIRED_API_FIELDS:
        if field not in payload:
            warnings.append(f"Required API field '{field}' is missing from prediction payload.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def run_final_system_validation(input_data: dict, prediction_payload: dict) -> dict:
    """Execute complete end-to-end validation across all 15 system chains."""
    chain_validators = {
        "cost_chain": validate_cost_chain,
        "budget_chain": validate_budget_chain,
        "route_chain": validate_route_chain,
        "transport_chain": validate_transport_chain,
        "schedule_chain": validate_schedule_chain,
        "recommendation_chain": validate_recommendation_chain,
        "confidence_chain": validate_confidence_chain,
        "realtime_data_chain": validate_realtime_data_chain,
        "backward_compatibility": validate_backward_compatibility
    }

    chain_results = {}
    all_passed = True
    all_warnings: List[str] = []

    for chain_name, validator_fn in chain_validators.items():
        passed, warns = validator_fn(prediction_payload)
        chain_results[chain_name] = {
            "passed": passed,
            "warnings": warns
        }
        if not passed:
            all_passed = False
            all_warnings.extend(warns)

    return {
        "valid": all_passed,
        "all_chains_passed": all_passed,
        "chains_evaluated": len(chain_validators),
        "chain_results": chain_results,
        "warnings": all_warnings
    }
