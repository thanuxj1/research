import logging
import re
from typing import Dict, List, Union, Optional

try:
    from .route_calculator import _parse_route_input as parse_route, calculate_route_distance
    from .fuel_calculator import calculate_route_fuel_cost
    from .hotel_calculator import calculate_route_hotel_cost
    from .food_calculator import calculate_route_food_cost
    from .attraction_calculator import calculate_route_attraction_cost
    from .public_transport_calculator import calculate_public_transport_route_cost
    from .unified_cost_calculator import build_cost_summary
except ImportError:
    from route_calculator import _parse_route_input as parse_route, calculate_route_distance
    from fuel_calculator import calculate_route_fuel_cost
    from hotel_calculator import calculate_route_hotel_cost
    from food_calculator import calculate_route_food_cost
    from attraction_calculator import calculate_route_attraction_cost
    from public_transport_calculator import calculate_public_transport_route_cost
    from unified_cost_calculator import build_cost_summary

logger = logging.getLogger(__name__)

INTEREST_DESTINATIONS = {
    "nature": ["Nuwara Eliya", "Ella", "Kandy", "Kitulgala", "Badulla"],
    "beach": ["Galle", "Mirissa", "Bentota", "Hikkaduwa", "Unawatuna", "Arugam Bay", "Trincomalee"],
    "cultural": ["Kandy", "Sigiriya", "Polonnaruwa", "Anuradhapura", "Jaffna"],
    "wildlife": ["Yala", "Udawalawe", "Mirissa", "Anuradhapura"],
    "adventure": ["Ella", "Kitulgala", "Nuwara Eliya", "Arugam Bay"]
}


def _format_num(val: Union[int, float]) -> Union[int, float]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return round(val, 2)


def clean_and_deduplicate_stops(stops: List[str]) -> List[str]:
    """Clean and deduplicate consecutive identical stops in a route."""
    if not stops:
        return []
    res = [stops[0]]
    for s in stops[1:]:
        if s.strip() != res[-1].strip():
            res.append(s.strip())
    if len(res) > 2 and res[0] != res[-1] and res[0] == "Colombo":
        res.append("Colombo")
    return res


def generate_route_candidates(
    primary_route: Union[str, List[str]],
    interest: str = "nature",
    days: int = 4,
    user_budget: float = 50000.0
) -> List[str]:
    """Generate logical alternative route candidates based on trip duration, interest, and budget.
    
    Returns:
        List[str]: List of formatted route string candidates.
    """
    stops = parse_route(primary_route)
    if not stops or len(stops) < 2:
        stops = ["Colombo", "Kandy", "Nuwara Eliya", "Ella", "Colombo"]

    candidates_raw: List[List[str]] = [stops]

    # Pre-defined connected hub circuits
    if days <= 2:
        nature_circuits = [
            ["Colombo", "Kandy", "Colombo"],
            ["Colombo", "Kitulgala", "Colombo"],
            ["Colombo", "Kandy", "Ella", "Colombo"]
        ]
        beach_circuits = [
            ["Colombo", "Galle", "Colombo"],
            ["Colombo", "Bentota", "Colombo"],
            ["Colombo", "Galle", "Mirissa", "Colombo"]
        ]
        cultural_circuits = [
            ["Colombo", "Kandy", "Colombo"],
            ["Colombo", "Sigiriya", "Colombo"],
            ["Colombo", "Kandy", "Sigiriya", "Colombo"]
        ]
        wildlife_circuits = [
            ["Colombo", "Udawalawe", "Colombo"],
            ["Colombo", "Yala", "Colombo"]
        ]
    else:
        nature_circuits = [
            ["Colombo", "Kandy", "Nuwara Eliya", "Ella", "Colombo"],
            ["Colombo", "Kandy", "Ella", "Colombo"],
            ["Colombo", "Kandy", "Nuwara Eliya", "Kandy", "Colombo"],
            ["Colombo", "Kandy", "Colombo"]
        ]
        beach_circuits = [
            ["Colombo", "Galle", "Mirissa", "Colombo"],
            ["Colombo", "Bentota", "Hikkaduwa", "Galle", "Colombo"],
            ["Colombo", "Galle", "Colombo"]
        ]
        cultural_circuits = [
            ["Colombo", "Kandy", "Sigiriya", "Polonnaruwa", "Colombo"],
            ["Colombo", "Kandy", "Sigiriya", "Kandy", "Colombo"],
            ["Colombo", "Anuradhapura", "Colombo"]
        ]
        wildlife_circuits = [
            ["Colombo", "Galle", "Yala", "Galle", "Colombo"],
            ["Colombo", "Udawalawe", "Colombo"]
        ]

    int_lower = interest.lower()
    if int_lower == "beach":
        preferred_pool = beach_circuits
    elif int_lower in ("cultural", "culture", "history"):
        preferred_pool = cultural_circuits
    elif int_lower in ("wildlife", "safari"):
        preferred_pool = wildlife_circuits
    else:
        preferred_pool = nature_circuits

    for cand in preferred_pool:
        if cand not in candidates_raw:
            candidates_raw.append(cand)

    # Convert to formatted route strings
    formatted_candidates: List[str] = []
    for cand in candidates_raw:
        r_str = " -> ".join(cand)
        if r_str not in formatted_candidates:
            formatted_candidates.append(r_str)

    return formatted_candidates[:5]


def evaluate_route_candidate(
    route: str,
    days: int,
    travelers: int = 2,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    interest: str = "nature",
    travel_type: str = "couple",
    transport_mode: str = "private car",
    hotel_tier: Optional[str] = "mid-range",
    food_tier: Optional[str] = "standard",
    include_snacks: bool = False,
    food_preferences: Optional[dict] = None,
    user_budget: float = 50000.0
) -> dict:
    """Evaluate a candidate route through all existing calculation engines."""
    # 1. Distance
    dist_res = calculate_route_distance(route)
    total_dist = dist_res.get("total_distance_km", 400) if dist_res.get("success") else 400

    # 2. Transport (Fuel or Public Transport)
    mode_norm = transport_mode.strip().lower()
    pt_data = None
    if mode_norm in ("bus", "train", "public transport", "public_transport"):
        pt_mode = "bus" if mode_norm == "bus" else "train"
        pt_res = calculate_public_transport_route_cost(
            route=route,
            transport_mode=pt_mode,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            travelers=travelers
        )
        if pt_res.get("success"):
            pt_data = {k: v for k, v in pt_res.items() if k != "success"}
        fuel_data = {"estimated_fuel_cost_lkr": 0, "fuel_applicable": False}
    else:
        fuel_res = calculate_route_fuel_cost(total_dist, mode_norm)
        fuel_data = {k: v for k, v in fuel_res.items() if k != "success"} if fuel_res.get("success") else {"estimated_fuel_cost_lkr": 0}

    # 3. Hotel
    h_res = calculate_route_hotel_cost(route, days, travelers, hotel_tier, user_budget)
    hotel_data = {k: v for k, v in h_res.items() if k != "success"} if h_res.get("success") else {"total_cost_lkr": 0}

    # 4. Food
    f_res = calculate_route_food_cost(route, days, travelers, food_tier, include_snacks, food_preferences, user_budget)
    food_data = {k: v for k, v in f_res.items() if k != "success"} if f_res.get("success") else {"total_cost_lkr": 0}

    # 5. Attraction
    a_res = calculate_route_attraction_cost(route, days, travelers, adult_travelers, child_travelers, interest, user_budget)
    attraction_data = {k: v for k, v in a_res.items() if k != "success"} if a_res.get("success") else {"total_cost_lkr": 0}

    # 6. Unified Cost
    summary = build_cost_summary(
        fuel_data=fuel_data,
        hotel_data=hotel_data,
        food_data=food_data,
        attraction_data=attraction_data,
        user_budget=user_budget,
        days=days,
        travelers=travelers,
        public_transport_data=pt_data
    )

    stops = parse_route(route)

    return {
        "route": route,
        "stops": stops,
        "total_distance_km": total_dist,
        "fuel_cost_lkr": summary["cost_breakdown"]["fuel_lkr"],
        "transport_cost_lkr": summary["transport_cost_lkr"],
        "hotel_cost_lkr": summary["cost_breakdown"]["hotel_lkr"],
        "food_cost_lkr": summary["cost_breakdown"]["food_lkr"],
        "attraction_cost_lkr": summary["cost_breakdown"]["attractions_lkr"],
        "total_trip_cost_lkr": summary["total_trip_cost_lkr"],
        "budget_difference_lkr": summary["budget_difference_lkr"],
        "budget_deficit_lkr": summary["budget_deficit_lkr"],
        "budget_status": summary["budget_status"],
        "daily_average_cost_lkr": summary["daily_average_cost_lkr"],
        "per_person_cost_lkr": summary["per_person_total_lkr"]
    }


def calculate_route_score(
    candidate_eval: dict,
    user_budget: float,
    interest: str = "nature",
    days: int = 4
) -> dict:
    """Calculate deterministic route score based on budget feasibility, interest match, distance, and cost efficiency.
    
    Formula:
        route_score = budget_score + interest_score + destination_value - distance_penalty - cost_penalty
    """
    total_cost = candidate_eval["total_trip_cost_lkr"]
    distance_km = candidate_eval["total_distance_km"]
    stops = candidate_eval["stops"]
    inter_stops = [s for s in stops[1:-1] if s != "Colombo"]

    # 1. Budget Feasibility Score
    if total_cost <= user_budget:
        budget_score = 100.0 + min(20.0, ((user_budget - total_cost) / user_budget) * 20.0)
    else:
        overshoot = total_cost - user_budget
        budget_score = max(0.0, 100.0 - ((overshoot / user_budget) * 100.0))

    # 2. Interest Match Score
    target_destinations = INTEREST_DESTINATIONS.get(interest.lower(), [])
    matched_count = sum(1 for s in inter_stops if s in target_destinations)
    interest_score = min(40.0, matched_count * 20.0)

    # 3. Destination Value Score
    dest_val_score = len(set(inter_stops)) * 15.0

    # 4. Distance Penalty
    distance_penalty = round(distance_km / 10.0, 2)

    # 5. Cost Penalty
    cost_penalty = round(total_cost / 5000.0, 2)

    total_score = round(budget_score + interest_score + dest_val_score - distance_penalty - cost_penalty, 2)

    return {
        "total_score": total_score,
        "budget_score": _format_num(budget_score),
        "interest_score": _format_num(interest_score),
        "dest_val_score": _format_num(dest_val_score),
        "distance_penalty": distance_penalty,
        "cost_penalty": cost_penalty
    }


def optimize_itinerary(
    route: str,
    days: int,
    travelers: int = 2,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    interest: str = "nature",
    travel_type: str = "couple",
    transport_mode: str = "private car",
    hotel_tier: Optional[str] = "mid-range",
    food_tier: Optional[str] = "standard",
    include_snacks: bool = False,
    food_preferences: Optional[dict] = None,
    user_budget: float = 50000.0,
    original_summary: Optional[dict] = None
) -> dict:
    """Dynamic Route & Itinerary Optimization Engine.
    
    Evaluates candidate routes, scores each itinerary deterministically,
    and returns optimization metrics and comparative rankings.
    """
    if user_budget is None or user_budget <= 0:
        raise ValueError("User budget must be a positive number greater than zero")

    candidates_list = generate_route_candidates(route, interest, days, user_budget)

    evaluations: List[dict] = []
    for cand in candidates_list:
        ev = evaluate_route_candidate(
            route=cand,
            days=days,
            travelers=travelers,
            adult_travelers=adult_travelers,
            child_travelers=child_travelers,
            interest=interest,
            travel_type=travel_type,
            transport_mode=transport_mode,
            hotel_tier=hotel_tier,
            food_tier=food_tier,
            include_snacks=include_snacks,
            food_preferences=food_preferences,
            user_budget=user_budget
        )
        score_info = calculate_route_score(ev, user_budget, interest, days)
        ev["route_score"] = score_info["total_score"]
        ev["interest_match_score"] = score_info["interest_score"]
        ev["budget_feasibility_score"] = score_info["budget_score"]
        evaluations.append(ev)

    # Sort candidates descending by route_score
    evaluations.sort(key=lambda x: x["route_score"], reverse=True)

    orig_eval = evaluations[0]
    for ev in evaluations:
        if ev["route"] == route:
            orig_eval = ev
            break

    best_cand = evaluations[0]

    orig_cost = orig_eval["total_trip_cost_lkr"]
    best_cost = best_cand["total_trip_cost_lkr"]
    savings_lkr = _format_num(max(0.0, orig_cost - best_cost))
    savings_pct = 0.0 if orig_cost == 0 else round((savings_lkr / orig_cost) * 100, 2)

    if best_cost <= user_budget:
        opt_status = "optimized_within_budget" if orig_cost > user_budget else "within_budget"
        reason = f"The optimized itinerary ({best_cand['route']}) fits comfortably within your budget while preserving your {interest} preference."
    elif savings_lkr > 0:
        opt_status = "partially_optimized"
        reason = f"The optimized itinerary ({best_cand['route']}) reduces cost by {savings_lkr} LKR ({savings_pct}%), offering a more feasible option."
    else:
        opt_status = "cannot_meet_budget"
        reason = "All evaluated route candidates exceed the target budget due to high baseline accommodation and travel costs."

    candidate_summaries = []
    for ev in evaluations:
        candidate_summaries.append({
            "route": ev["route"],
            "distance_km": ev["total_distance_km"],
            "total_cost_lkr": ev["total_trip_cost_lkr"],
            "budget_status": ev["budget_status"],
            "route_score": ev["route_score"],
            "interest_match_score": ev["interest_match_score"],
            "is_selected_as_best": (ev["route"] == best_cand["route"])
        })

    return {
        "original_route": route,
        "original_cost_lkr": _format_num(orig_cost),
        "optimized_route": best_cand["route"],
        "optimized_cost_lkr": _format_num(best_cost),
        "user_budget_lkr": _format_num(user_budget),
        "savings_lkr": savings_lkr,
        "savings_percentage": savings_pct,
        "budget_status": opt_status,
        "reason": reason,
        "best_candidate_score": best_cand["route_score"],
        "route_candidates": candidate_summaries
    }


def compare_route_options(candidates_eval_list: List[dict]) -> dict:
    """Compare multiple route candidates and return comparative rankings."""
    if not candidates_eval_list:
        return {"rankings": []}

    sorted_cands = sorted(candidates_eval_list, key=lambda x: x.get("route_score", 0), reverse=True)
    rankings = []
    for idx, c in enumerate(sorted_cands, start=1):
        rankings.append({
            "rank": idx,
            "route": c.get("route"),
            "score": c.get("route_score"),
            "total_cost_lkr": c.get("total_trip_cost_lkr"),
            "distance_km": c.get("total_distance_km")
        })

    return {
        "total_candidates": len(candidates_eval_list),
        "top_route": rankings[0]["route"] if rankings else "",
        "rankings": rankings
    }
