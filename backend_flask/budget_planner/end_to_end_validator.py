import logging
import re
from typing import Dict, List, Tuple, Union, Optional

try:
    from .route_calculator import _parse_route_input as parse_route, calculate_route_distance
except ImportError:
    from route_calculator import _parse_route_input as parse_route, calculate_route_distance

logger = logging.getLogger(__name__)

VALID_INTERESTS = {"nature", "beach", "cultural", "culture", "history", "wildlife", "safari", "adventure", "general"}
VALID_TRAVEL_TYPES = {"solo", "couple", "family", "friends", "group", "general"}
VALID_TRANSPORT_MODES = {"car", "private car", "suv", "van", "luxury car", "motorcycle", "bus", "train", "public transport", "public_transport", ""}


def _format_num(val: Union[int, float]) -> Union[int, float]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return round(val, 2)


def normalize_trip_input(data: dict) -> dict:
    """Normalize raw request payload dictionary."""
    if not isinstance(data, dict):
        return {}

    norm = dict(data)

    try:
        budget = float(data.get("budget", 0))
    except (ValueError, TypeError):
        budget = 0.0

    try:
        days = int(data.get("days", 0))
    except (ValueError, TypeError):
        days = 0

    travel_type = str(data.get("travel_type") or "couple").strip().lower()
    interest = str(data.get("interest") or "nature").strip().lower()
    transport_mode = str(data.get("transport_mode") or "private car").strip().lower()

    raw_adults = data.get("adult_travelers")
    raw_children = data.get("child_travelers")

    adult_travelers = int(raw_adults) if raw_adults is not None else None
    child_travelers = int(raw_children) if raw_children is not None else None

    raw_travelers = data.get("travelers")
    if raw_travelers is not None:
        try:
            travelers = int(raw_travelers)
        except (ValueError, TypeError):
            travelers = 1 if travel_type == "solo" else 2
    elif adult_travelers is not None or child_travelers is not None:
        travelers = (adult_travelers or 0) + (child_travelers or 0)
    else:
        travelers = 1 if travel_type == "solo" else 2

    if adult_travelers is None:
        adult_travelers = max(0, travelers - (child_travelers or 0))

    if child_travelers is None:
        child_travelers = max(0, travelers - adult_travelers)

    norm["budget"] = _format_num(budget)
    norm["days"] = days
    norm["travelers"] = travelers
    norm["adult_travelers"] = adult_travelers
    norm["child_travelers"] = child_travelers
    norm["interest"] = interest
    norm["travel_type"] = travel_type
    norm["transport_mode"] = transport_mode

    return norm


def validate_trip_input(data: dict) -> Tuple[bool, List[str]]:
    """Validate trip input payload against bounds and composition rules."""
    warnings: List[str] = []

    budget = data.get("budget", 0)
    if budget is None or budget <= 0:
        warnings.append("Target budget must be a positive number greater than zero.")

    days = data.get("days", 0)
    if days is None or days < 1:
        warnings.append("Trip duration must be at least 1 day.")

    travelers = data.get("travelers", 0)
    if travelers is None or travelers < 1:
        warnings.append("Traveler count must be at least 1 person.")

    adults = data.get("adult_travelers")
    children = data.get("child_travelers")

    if adults is not None and adults < 0:
        warnings.append("Adult traveler count cannot be negative.")

    if children is not None and children < 0:
        warnings.append("Child traveler count cannot be negative.")

    if adults is not None and children is not None:
        if adults + children != travelers:
            warnings.append(f"Adult count ({adults}) and child count ({children}) sum to {adults + children}, which does not match total travelers ({travelers}).")

    interest = str(data.get("interest", "")).strip().lower()
    if interest and interest not in VALID_INTERESTS:
        warnings.append(f"Unrecognized interest category '{interest}'. Standard categories are nature, beach, cultural, wildlife, adventure.")

    travel_type = str(data.get("travel_type", "")).strip().lower()
    if travel_type and travel_type not in VALID_TRAVEL_TYPES:
        warnings.append(f"Unrecognized travel type '{travel_type}'. Standard types are solo, couple, family, friends, group.")

    mode = str(data.get("transport_mode", "")).strip().lower()
    if mode and mode not in VALID_TRANSPORT_MODES:
        warnings.append(f"Unrecognized transport mode '{mode}'. Standard modes are car, private car, suv, van, motorcycle, bus, train.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_route_duration(route: str, days: int) -> Tuple[bool, List[str]]:
    """Validate that a route stop count and total distance are compatible with trip duration."""
    warnings: List[str] = []
    stops = parse_route(route)
    if not stops or len(stops) < 2:
        return False, ["Route is empty or invalid."]

    inter_stops = [s for s in stops[1:-1] if s != "Colombo"]
    if days <= 2 and len(inter_stops) > 2:
        warnings.append(f"Route '{route}' contains {len(inter_stops)} intermediate stops, which is excessive for a {days}-day trip.")

    dist_res = calculate_route_distance(route)
    if dist_res.get("success"):
        dist_km = dist_res.get("total_distance_km", 0)
        max_rec_dist = days * 300.0
        if dist_km > max_rec_dist:
            warnings.append(f"Route distance of {dist_km} km exceeds recommended limit of {max_rec_dist} km for a {days}-day trip.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_cost_consistency(trip_cost_data: dict) -> Tuple[bool, List[str]]:
    """Verify mathematical formula total_trip_cost = transport + hotel + food + attractions within tolerance."""
    warnings: List[str] = []

    if not isinstance(trip_cost_data, dict):
        return False, ["Invalid trip cost data payload."]

    total = trip_cost_data.get("total_trip_cost_lkr", 0)
    cb = trip_cost_data.get("cost_breakdown", {})

    t_cost = cb.get("transport_lkr", cb.get("fuel_lkr", 0))
    h_cost = cb.get("hotel_lkr", 0)
    f_cost = cb.get("food_lkr", 0)
    a_cost = cb.get("attractions_lkr", 0)

    calculated_sum = t_cost + h_cost + f_cost + a_cost
    diff = abs(total - calculated_sum)

    if diff > 0.05:
        warnings.append(f"Cost discrepancy detected: total ({total} LKR) does not equal sum of components ({calculated_sum} LKR, diff: {diff} LKR).")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_schedule_feasibility(schedule_data: dict) -> Tuple[bool, List[str]]:
    """Validate daily travel schedule feasibility score and warning counts."""
    warnings: List[str] = []
    if not isinstance(schedule_data, dict):
        return False, ["Invalid travel schedule payload."]

    score = schedule_data.get("schedule_score", 0)
    if score < 0 or score > 100:
        warnings.append(f"Schedule score {score} is out of bounds (0-100).")

    daily = schedule_data.get("daily_itinerary", [])
    for day_info in daily:
        day_warns = day_info.get("warnings", [])
        warnings.extend(day_warns)

    is_valid = len(warnings) == 0
    return is_valid, warnings


def validate_final_recommendation(recommendation_data: dict) -> Tuple[bool, List[str]]:
    """Validate multi-objective recommendation score and selected trip structure."""
    warnings: List[str] = []
    if not isinstance(recommendation_data, dict):
        return False, ["Invalid recommendation payload."]

    score = recommendation_data.get("overall_score", 0)
    if score < 0 or score > 100:
        warnings.append(f"Overall recommendation score {score} is out of bounds (0-100).")

    sel = recommendation_data.get("selected_trip", {})
    if not sel or not sel.get("route"):
        warnings.append("Selected trip recommendation missing route information.")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def run_end_to_end_validation(
    input_data: dict,
    final_selected_route: str,
    final_trip_cost: dict,
    final_schedule: dict,
    recommendation_data: dict
) -> dict:
    """Run comprehensive end-to-end validation checks across all 11 steps.
    
    Returns:
        dict: "validation" payload object.
    """
    input_ok, input_warns = validate_trip_input(input_data)
    route_ok, route_warns = validate_route_duration(final_selected_route, input_data.get("days", 2))
    cost_ok, cost_warns = validate_cost_consistency(final_trip_cost)
    sched_ok, sched_warns = validate_schedule_feasibility(final_schedule)
    rec_ok, rec_warns = validate_final_recommendation(recommendation_data)

    all_warnings = input_warns + route_warns + cost_warns + sched_warns + rec_warns

    overall_valid = input_ok and route_ok and cost_ok and rec_ok

    return {
        "valid": overall_valid,
        "input_valid": input_ok,
        "route_duration_valid": route_ok,
        "costs_consistent": cost_ok,
        "schedule_feasible": sched_ok,
        "recommendation_valid": rec_ok,
        "warnings": all_warnings
    }
