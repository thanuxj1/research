import logging
import re
from typing import Dict, List, Union, Optional, Tuple

try:
    from .route_calculator import _parse_route_input as parse_route, calculate_route_distance
    from .fuel_calculator import calculate_route_fuel_cost
    from .hotel_calculator import calculate_route_hotel_cost
    from .food_calculator import calculate_route_food_cost
    from .attraction_calculator import calculate_route_attraction_cost
    from .public_transport_calculator import calculate_public_transport_route_cost
    from .unified_cost_calculator import build_cost_summary, build_budget_analysis
    from .budget_optimizer import optimize_budget
    from .dynamic_route_optimizer import generate_route_candidates, optimize_itinerary
    from .travel_schedule_optimizer import optimize_travel_schedule
except ImportError:
    from route_calculator import _parse_route_input as parse_route, calculate_route_distance
    from fuel_calculator import calculate_route_fuel_cost
    from hotel_calculator import calculate_route_hotel_cost
    from food_calculator import calculate_route_food_cost
    from attraction_calculator import calculate_route_attraction_cost
    from public_transport_calculator import calculate_public_transport_route_cost
    from unified_cost_calculator import build_cost_summary, build_budget_analysis
    from budget_optimizer import optimize_budget
    from dynamic_route_optimizer import generate_route_candidates, optimize_itinerary
    from travel_schedule_optimizer import optimize_travel_schedule

logger = logging.getLogger(__name__)

DEFAULT_SCORE_WEIGHTS = {
    "budget": 0.25,
    "interest": 0.20,
    "route_quality": 0.15,
    "schedule": 0.15,
    "destination_value": 0.10,
    "transport": 0.05,
    "cost_efficiency": 0.05,
    "preference_match": 0.05
}

INTEREST_CATEGORIES = {
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


def calculate_budget_score(total_cost: float, user_budget: float, is_optimized: bool = False) -> float:
    """Calculate normalized budget score (0-100)."""
    if user_budget <= 0:
        return 0.0

    if total_cost <= user_budget:
        bonus = min(15.0, ((user_budget - total_cost) / user_budget) * 15.0)
        opt_bonus = 5.0 if is_optimized else 0.0
        return _format_num(min(100.0, 80.0 + bonus + opt_bonus))
    else:
        overshoot = total_cost - user_budget
        pct_over = (overshoot / user_budget) * 100.0
        score = max(0.0, 75.0 - (pct_over * 1.2))
        return _format_num(score)


def calculate_interest_score(route: str, interest: str) -> float:
    """Calculate normalized interest match score (0-100)."""
    stops = parse_route(route)
    inter_stops = [s for s in stops[1:-1] if s != "Colombo"]
    if not inter_stops:
        inter_stops = [s for s in stops if s != "Colombo"] or ["Kandy"]

    targets = INTEREST_CATEGORIES.get(interest.lower(), ["Kandy", "Nuwara Eliya", "Ella"])
    matches = sum(1 for s in inter_stops if s in targets)

    ratio = matches / len(inter_stops) if inter_stops else 0.5
    score = min(100.0, 50.0 + (ratio * 50.0))
    return _format_num(score)


def calculate_route_quality_score(distance_km: float, stops: List[str]) -> float:
    """Calculate normalized route quality score (0-100)."""
    score = 90.0

    if distance_km > 500:
        score -= min(30.0, (distance_km - 500) / 10.0)

    unique_stops = set(stops)
    if len(stops) - len(unique_stops) > 1:
        score -= 10.0

    return _format_num(max(0.0, min(100.0, score)))


def calculate_schedule_score(schedule_res: dict) -> float:
    """Extract normalized schedule score (0-100) from Step 10 optimizer."""
    if not schedule_res:
        return 75.0
    return _format_num(schedule_res.get("schedule_score", 75.0))


def calculate_destination_value_score(route: str, interest: str) -> float:
    """Calculate normalized destination value score (0-100)."""
    stops = parse_route(route)
    unique_count = len(set(s for s in stops if s != "Colombo"))
    val = min(100.0, 40.0 + (unique_count * 20.0))
    return _format_num(val)


def calculate_transport_score(transport_mode: str, transport_preference: Optional[str] = None) -> float:
    """Calculate normalized transport score (0-100)."""
    mode_norm = transport_mode.strip().lower()
    pref_norm = (transport_preference or "").strip().lower()

    if pref_norm and (mode_norm in pref_norm or pref_norm in mode_norm):
        return 95.0

    if mode_norm in ("train", "bus"):
        return 85.0
    elif mode_norm in ("private car", "car"):
        return 80.0
    elif mode_norm == "suv":
        return 75.0
    else:
        return 70.0


def calculate_cost_efficiency_score(dest_val_score: float, total_cost: float) -> float:
    """Calculate normalized cost efficiency score (0-100)."""
    if total_cost <= 0:
        return 50.0

    val_per_lkr = (dest_val_score / total_cost) * 10000.0
    score = min(100.0, 40.0 + (val_per_lkr * 15.0))
    return _format_num(score)


def calculate_preference_match_score(
    travel_type: str,
    hotel_tier: Optional[str],
    food_tier: Optional[str],
    transport_mode: str
) -> float:
    """Calculate normalized preference match score (0-100)."""
    score = 85.0

    h_norm = (hotel_tier or "mid-range").lower()
    f_norm = (food_tier or "standard").lower()

    if h_norm in ("mid-range", "budget") and f_norm in ("standard", "budget"):
        score += 10.0

    return _format_num(min(100.0, score))


def calculate_overall_trip_score(score_breakdown: dict, weights: Optional[dict] = None) -> float:
    """Calculate weighted overall score from sub-scores."""
    w = weights or DEFAULT_SCORE_WEIGHTS

    total_score = (
        score_breakdown["budget_score"] * w.get("budget", 0.25) +
        score_breakdown["interest_score"] * w.get("interest", 0.20) +
        score_breakdown["route_quality_score"] * w.get("route_quality", 0.15) +
        score_breakdown["schedule_score"] * w.get("schedule", 0.15) +
        score_breakdown["destination_value_score"] * w.get("destination_value", 0.10) +
        score_breakdown["transport_score"] * w.get("transport", 0.05) +
        score_breakdown["cost_efficiency_score"] * w.get("cost_efficiency", 0.05) +
        score_breakdown["preference_match_score"] * w.get("preference_match", 0.05)
    )

    return _format_num(round(total_score, 2))


def build_trip_candidates(
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
    user_budget: float = 50000.0
) -> List[dict]:
    """Generate distinct complete candidate trip configurations."""
    route_cands = generate_route_candidates(route, interest, days, user_budget)

    candidates_configs: List[dict] = []

    # Candidate 1: Original requested trip
    candidates_configs.append({
        "label": "Original Recommended Trip",
        "route": route,
        "transport_mode": transport_mode,
        "hotel_tier": hotel_tier or "mid-range",
        "food_tier": food_tier or "standard"
    })

    # Candidate 2: Dynamic route optimized candidate
    for r in route_cands:
        if r != route:
            candidates_configs.append({
                "label": f"Dynamic Route Option ({r})",
                "route": r,
                "transport_mode": transport_mode,
                "hotel_tier": hotel_tier or "mid-range",
                "food_tier": food_tier or "standard"
            })
            break

    # Candidate 3: Budget tier optimized candidate
    candidates_configs.append({
        "label": "Budget-Optimized Tier Trip",
        "route": route_cands[1] if len(route_cands) > 1 else route,
        "transport_mode": transport_mode,
        "hotel_tier": "budget",
        "food_tier": "budget"
    })

    # Candidate 4: Alternate transport mode candidate (only if public transport requested or mode unspecified)
    mode_clean = transport_mode.strip().lower() if transport_mode else ""
    if not mode_clean or mode_clean in ("bus", "train", "public transport", "public_transport"):
        candidates_configs.append({
            "label": "Train Public Transport Trip",
            "route": route_cands[1] if len(route_cands) > 1 else route,
            "transport_mode": "train",
            "hotel_tier": "budget",
            "food_tier": "standard"
        })

    # Deduplicate candidates
    dedup: List[dict] = []
    seen = set()
    for c in candidates_configs:
        key = (c["route"], c["transport_mode"], c["hotel_tier"], c["food_tier"])
        if key not in seen:
            seen.add(key)
            dedup.append(c)

    return dedup


def evaluate_trip_candidate(
    candidate_config: dict,
    days: int,
    travelers: int = 2,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    interest: str = "nature",
    travel_type: str = "couple",
    user_budget: float = 50000.0,
    weights: Optional[dict] = None
) -> dict:
    """Evaluate candidate trip through all Step 1-10 calculation engines."""
    route = candidate_config["route"]
    mode = candidate_config["transport_mode"]
    h_tier = candidate_config["hotel_tier"]
    f_tier = candidate_config["food_tier"]

    # 1. Route Distance
    dist_res = calculate_route_distance(route)
    total_dist = dist_res.get("total_distance_km", 400) if dist_res.get("success") else 400
    stops = dist_res.get("route", parse_route(route))

    # 2. Transport Cost (Fuel or Public Transit)
    mode_clean = mode.strip().lower()
    pt_data = None
    if mode_clean in ("bus", "train", "public transport", "public_transport"):
        pt_res = calculate_public_transport_route_cost(route, mode_clean, adult_travelers=adult_travelers, child_travelers=child_travelers, travelers=travelers)
        if pt_res.get("success"):
            pt_data = {k: v for k, v in pt_res.items() if k != "success"}
        fuel_data = {"estimated_fuel_cost_lkr": 0, "fuel_applicable": False}
    else:
        fuel_res = calculate_route_fuel_cost(total_dist, mode_clean)
        fuel_data = {k: v for k, v in fuel_res.items() if k != "success"} if fuel_res.get("success") else {"estimated_fuel_cost_lkr": 0}

    # 3. Hotel, Food, Attraction Cost
    h_res = calculate_route_hotel_cost(route, days, travelers, h_tier, user_budget)
    hotel_data = {k: v for k, v in h_res.items() if k != "success"} if h_res.get("success") else {"total_cost_lkr": 0}

    f_res = calculate_route_food_cost(route, days, travelers, f_tier, False, None, user_budget)
    food_data = {k: v for k, v in f_res.items() if k != "success"} if f_res.get("success") else {"total_cost_lkr": 0}

    a_res = calculate_route_attraction_cost(route, days, travelers, adult_travelers, child_travelers, interest, user_budget)
    attraction_data = {k: v for k, v in a_res.items() if k != "success"} if a_res.get("success") else {"total_cost_lkr": 0}

    # 4. Unified Cost
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

    # 5. Travel Schedule
    sched_res = optimize_travel_schedule(
        route=route, days=days, travelers=travelers,
        adult_travelers=adult_travelers, child_travelers=child_travelers,
        interest=interest, travel_type=travel_type, transport_mode=mode,
        hotel_tier=h_tier, food_tier=f_tier, user_budget=user_budget,
        original_summary=summary
    )

    total_cost = summary["total_trip_cost_lkr"]

    # Sub-scores
    b_score = calculate_budget_score(total_cost, user_budget, (h_tier == "budget" or mode in ("train", "bus")))
    i_score = calculate_interest_score(route, interest)
    r_score = calculate_route_quality_score(total_dist, stops)
    s_score = calculate_schedule_score(sched_res)
    d_score = calculate_destination_value_score(route, interest)
    t_score = calculate_transport_score(mode)
    c_score = calculate_cost_efficiency_score(d_score, total_cost)
    p_score = calculate_preference_match_score(travel_type, h_tier, f_tier, mode)

    score_breakdown = {
        "budget_score": b_score,
        "interest_score": i_score,
        "route_quality_score": r_score,
        "schedule_score": s_score,
        "destination_value_score": d_score,
        "transport_score": t_score,
        "cost_efficiency_score": c_score,
        "preference_match_score": p_score
    }

    overall_score = calculate_overall_trip_score(score_breakdown, weights)

    return {
        "label": candidate_config.get("label", "Trip Candidate"),
        "route": route,
        "transport_mode": mode,
        "hotel_tier": h_tier,
        "food_tier": f_tier,
        "total_distance_km": total_dist,
        "total_cost_lkr": total_cost,
        "user_budget_lkr": _format_num(user_budget),
        "budget_difference_lkr": summary["budget_difference_lkr"],
        "budget_status": summary["budget_status"],
        "overall_score": overall_score,
        "score_breakdown": score_breakdown,
        "travel_schedule": sched_res,
        "summary": summary
    }


def rank_trip_candidates(candidates: List[dict]) -> List[dict]:
    """Sort trip candidates deterministically using tie-breakers:
    1. overall_score DESC
    2. budget_difference ASC
    3. total_cost ASC
    4. distance ASC
    5. route ASC
    """
    return sorted(
        candidates,
        key=lambda x: (
            -x["overall_score"],
            x["total_cost_lkr"] - x["user_budget_lkr"],
            x["total_cost_lkr"],
            x["total_distance_km"],
            x["route"]
        )
    )


def select_best_trip(ranked_candidates: List[dict]) -> Tuple[dict, dict]:
    """Select best overall trip candidate and identify specialized alternatives."""
    best = ranked_candidates[0]

    cheapest = min(ranked_candidates, key=lambda x: x["total_cost_lkr"])
    best_interest = max(ranked_candidates, key=lambda x: x["score_breakdown"]["interest_score"])
    best_budget_fit = max(ranked_candidates, key=lambda x: x["score_breakdown"]["budget_score"])
    best_schedule = max(ranked_candidates, key=lambda x: x["score_breakdown"]["schedule_score"])

    alternatives = {
        "cheapest_trip": cheapest,
        "best_interest_trip": best_interest,
        "best_budget_fit": best_budget_fit,
        "best_schedule": best_schedule
    }

    return best, alternatives


def build_recommendation_summary(best_trip: dict, user_budget: float, interest: str) -> Tuple[List[str], List[str]]:
    """Build explainable rationale bullets ('why_this_trip') and trade-offs."""
    why_this_trip = []
    tradeoffs = []

    if best_trip["total_cost_lkr"] <= user_budget:
        why_this_trip.append(f"Fits within your {user_budget} LKR target budget.")
    else:
        why_this_trip.append(f"Provides the most cost-effective candidate itinerary for your {user_budget} LKR budget.")

    why_this_trip.append(f"Strongly matches your {interest} travel preference.")
    why_this_trip.append(f"Uses an efficient {best_trip['transport_mode']} transport mode.")
    why_this_trip.append("Maintains a high daily schedule feasibility score with adequate rest buffers.")

    if best_trip["transport_mode"] in ("train", "bus"):
        tradeoffs.append("Public transport travel times may be longer than a private car.")

    if best_trip["hotel_tier"] == "budget":
        tradeoffs.append("Accommodation is optimized to budget tier to maximize cost savings.")

    return why_this_trip, tradeoffs


def generate_personalized_recommendation(
    predicted_route: str,
    budget: float,
    days: int,
    travelers: int = 2,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    interest: str = "nature",
    travel_type: str = "couple",
    transport_mode: str = "private car",
    hotel_tier: Optional[str] = "mid-range",
    food_tier: Optional[str] = "standard",
    ml_predicted_budget: Optional[float] = None
) -> Tuple[dict, dict]:
    """Personalized Multi-Objective Trip Recommendation & Decision Engine.
    
    Returns:
        tuple: (personalized_recommendation_dict, research_metrics_dict)
    """
    if budget is None or budget <= 0:
        raise ValueError("Budget must be a positive number greater than zero")

    if days is None or days <= 0:
        raise ValueError("Days must be a positive integer greater than zero")

    # 1. Build trip candidates
    candidates_configs = build_trip_candidates(
        route=predicted_route,
        days=days,
        travelers=travelers,
        adult_travelers=adult_travelers,
        child_travelers=child_travelers,
        interest=interest,
        travel_type=travel_type,
        transport_mode=transport_mode,
        hotel_tier=hotel_tier,
        food_tier=food_tier,
        user_budget=budget
    )

    # 2. Evaluate candidate trips
    evaluated_candidates: List[dict] = []
    for cfg in candidates_configs:
        try:
            ev = evaluate_trip_candidate(
                candidate_config=cfg,
                days=days,
                travelers=travelers,
                adult_travelers=adult_travelers,
                child_travelers=child_travelers,
                interest=interest,
                travel_type=travel_type,
                user_budget=budget
            )
            evaluated_candidates.append(ev)
        except Exception as ex:
            logger.warning(f"Error evaluating candidate {cfg.get('label')}: {ex}")

    if not evaluated_candidates:
        raise RuntimeError("Failed to evaluate any trip candidates")

    # 3. Rank candidates
    ranked = rank_trip_candidates(evaluated_candidates)
    best_trip, alternatives = select_best_trip(ranked)

    why_this_trip, tradeoffs = build_recommendation_summary(best_trip, budget, interest)

    # Clean candidate payloads for API output
    clean_alternatives = {}
    for k, alt in alternatives.items():
        clean_alternatives[k] = {
            "route": alt["route"],
            "transport_mode": alt["transport_mode"],
            "total_cost_lkr": alt["total_cost_lkr"],
            "overall_score": alt["overall_score"]
        }

    personalized_recommendation = {
        "selected_trip": {
            "route": best_trip["route"],
            "transport_mode": best_trip["transport_mode"],
            "hotel_tier": best_trip["hotel_tier"],
            "food_tier": best_trip["food_tier"],
            "total_cost_lkr": best_trip["total_cost_lkr"],
            "budget_lkr": _format_num(budget),
            "remaining_budget_lkr": _format_num(max(0.0, budget - best_trip["total_cost_lkr"])),
            "budget_status": best_trip["budget_status"]
        },
        "overall_score": best_trip["overall_score"],
        "score_breakdown": best_trip["score_breakdown"],
        "alternatives": clean_alternatives,
        "why_this_trip": why_this_trip,
        "tradeoffs": tradeoffs
    }

    ml_budget_val = float(ml_predicted_budget) if ml_predicted_budget is not None else budget
    real_cost_val = float(best_trip["total_cost_lkr"])
    diff = _format_num(ml_budget_val - real_cost_val)
    err_pct = 0.0 if real_cost_val == 0 else round((abs(ml_budget_val - real_cost_val) / real_cost_val) * 100, 2)

    research_metrics = {
        "ml_predicted_budget_lkr": _format_num(ml_budget_val),
        "real_calculated_cost_lkr": real_cost_val,
        "prediction_difference_lkr": diff,
        "prediction_error_percentage": err_pct,
        "initial_route": predicted_route,
        "optimized_route": best_trip["route"],
        "final_selected_route": best_trip["route"],
        "number_of_candidates_evaluated": len(evaluated_candidates),
        "best_overall_score": best_trip["overall_score"]
    }

    return personalized_recommendation, research_metrics, best_trip
