import logging
from typing import Dict, List, Union, Optional

try:
    from .fuel_calculator import calculate_route_fuel_cost
    from .hotel_calculator import calculate_route_hotel_cost
    from .food_calculator import calculate_route_food_cost
    from .attraction_calculator import calculate_route_attraction_cost
    from .unified_cost_calculator import build_cost_summary
    from .configurations import generate_route
except ImportError:
    from fuel_calculator import calculate_route_fuel_cost
    from hotel_calculator import calculate_route_hotel_cost
    from food_calculator import calculate_route_food_cost
    from attraction_calculator import calculate_route_attraction_cost
    from unified_cost_calculator import build_cost_summary
    from configurations import generate_route

logger = logging.getLogger(__name__)

HOTEL_TIER_HIERARCHY = ["premium", "mid-range", "budget"]
FOOD_TIER_HIERARCHY = ["premium", "standard", "budget"]


def _format_num(val: Union[int, float]) -> Union[int, float]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return round(val, 2)


def get_next_hotel_tier(current_tier: str) -> Optional[str]:
    c_norm = current_tier.strip().lower()
    if c_norm in ("mid_range", "midrange", "standard"):
        c_norm = "mid-range"
    if c_norm in (HOTEL_TIER_HIERARCHY):
        idx = HOTEL_TIER_HIERARCHY.index(c_norm)
        if idx + 1 < len(HOTEL_TIER_HIERARCHY):
            return HOTEL_TIER_HIERARCHY[idx + 1]
    return "budget" if c_norm != "budget" else None


def get_next_food_tier(current_tier: str) -> Optional[str]:
    c_norm = current_tier.strip().lower()
    if c_norm in ("medium", "mid-range", "normal"):
        c_norm = "standard"
    if c_norm in (FOOD_TIER_HIERARCHY):
        idx = FOOD_TIER_HIERARCHY.index(c_norm)
        if idx + 1 < len(FOOD_TIER_HIERARCHY):
            return FOOD_TIER_HIERARCHY[idx + 1]
    return "budget" if c_norm != "budget" else None


def optimize_budget(
    route: Union[str, List[str]],
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
    original_fuel_data: Optional[dict] = None,
    original_hotel_data: Optional[dict] = None,
    original_food_data: Optional[dict] = None,
    original_attraction_data: Optional[dict] = None,
    original_summary: Optional[dict] = None
) -> dict:
    """Intelligent multi-level budget optimization engine.
    
    Generates cost-saving alternatives when requested trip exceeds user budget,
    without altering the original calculation results.
    """
    if user_budget is None or not isinstance(user_budget, (int, float)) or user_budget <= 0:
        raise ValueError("User budget must be a positive number greater than zero")

    if travelers is None or not isinstance(travelers, int) or travelers <= 0:
        raise ValueError("Travelers must be a positive integer greater than zero")

    if days is None or not isinstance(days, int) or days <= 0:
        raise ValueError("Days must be a positive integer greater than zero")

    # If original summary is not passed, compute original baseline trip cost
    if not original_summary:
        f_res = original_fuel_data or calculate_route_fuel_cost(400, transport_mode)
        h_res = original_hotel_data or calculate_route_hotel_cost(route, days, travelers, hotel_tier, user_budget)
        fd_res = original_food_data or calculate_route_food_cost(route, days, travelers, food_tier, include_snacks, food_preferences, user_budget)
        a_res = original_attraction_data or calculate_route_attraction_cost(route, days, travelers, adult_travelers, child_travelers, interest, user_budget)

        fuel_clean = {k: v for k, v in f_res.items() if k != "success"}
        hotel_clean = {k: v for k, v in h_res.items() if k != "success"}
        food_clean = {k: v for k, v in fd_res.items() if k != "success"}
        attr_clean = {k: v for k, v in a_res.items() if k != "success"}

        orig_summary = build_cost_summary(
            fuel_data=fuel_clean,
            hotel_data=hotel_clean,
            food_data=food_clean,
            attraction_data=attr_clean,
            user_budget=user_budget,
            days=days,
            travelers=travelers
        )
    else:
        orig_summary = original_summary
        fuel_clean = original_fuel_data or {}
        hotel_clean = original_hotel_data or {}
        food_clean = original_food_data or {}
        attr_clean = original_attraction_data or {}

    orig_total = orig_summary["total_trip_cost_lkr"]

    # If original trip is already within budget, return within_budget response
    if orig_total <= user_budget:
        return {
            "optimization_status": "within_budget",
            "original_cost_lkr": _format_num(orig_total),
            "optimized_cost_lkr": _format_num(orig_total),
            "user_budget_lkr": _format_num(user_budget),
            "savings_lkr": 0,
            "savings_percentage": 0.0,
            "remaining_budget_lkr": _format_num(user_budget - orig_total),
            "remaining_deficit_lkr": 0,
            "changes": [],
            "optimized_route": str(route),
            "recommendations": [
                "Your requested itinerary is already within your target budget! No cost-saving downgrades required."
            ]
        }

    # Begin optimization sequence
    changes: List[dict] = []
    recommendations: List[str] = []

    cur_route = route
    cur_hotel_tier = hotel_tier or "mid-range"
    cur_food_tier = food_tier or "standard"
    cur_transport = transport_mode

    cur_fuel_data = dict(fuel_clean)
    cur_hotel_data = dict(hotel_clean)
    cur_food_data = dict(food_clean)
    cur_attr_data = dict(attr_clean)

    cur_summary = dict(orig_summary)

    # Strategy A: Hotel Optimization
    next_hotel = get_next_hotel_tier(cur_hotel_tier)
    while next_hotel and cur_summary["total_trip_cost_lkr"] > user_budget:
        prev_h_cost = cur_hotel_data.get("total_cost_lkr", 0)
        new_h_res = calculate_route_hotel_cost(cur_route, days, travelers, next_hotel, user_budget)

        if new_h_res.get("success", True):
            new_h_clean = {k: v for k, v in new_h_res.items() if k != "success"}
            new_h_cost = new_h_clean.get("total_cost_lkr", 0)
            savings = prev_h_cost - new_h_cost

            if savings > 0:
                changes.append({
                    "category": "hotel",
                    "original": cur_hotel_tier,
                    "optimized": next_hotel,
                    "cost_before_lkr": _format_num(prev_h_cost),
                    "cost_after_lkr": _format_num(new_h_cost),
                    "savings_lkr": _format_num(savings),
                    "reason": f"Downgraded accommodation from {cur_hotel_tier} to {next_hotel} tier."
                })
                cur_hotel_tier = next_hotel
                cur_hotel_data = new_h_clean

                cur_summary = build_cost_summary(
                    fuel_data=cur_fuel_data,
                    hotel_data=cur_hotel_data,
                    food_data=cur_food_data,
                    attraction_data=cur_attr_data,
                    user_budget=user_budget,
                    days=days,
                    travelers=travelers
                )

        next_hotel = get_next_hotel_tier(cur_hotel_tier)

    # Strategy B: Food Optimization
    next_food = get_next_food_tier(cur_food_tier)
    while next_food and cur_summary["total_trip_cost_lkr"] > user_budget:
        prev_f_cost = cur_food_data.get("total_cost_lkr", 0)
        new_f_res = calculate_route_food_cost(cur_route, days, travelers, next_food, False, food_preferences, user_budget)

        if new_f_res.get("success", True):
            new_f_clean = {k: v for k, v in new_f_res.items() if k != "success"}
            new_f_cost = new_f_clean.get("total_cost_lkr", 0)
            savings = prev_f_cost - new_f_cost

            if savings > 0:
                changes.append({
                    "category": "food",
                    "original": cur_food_tier,
                    "optimized": next_food,
                    "cost_before_lkr": _format_num(prev_f_cost),
                    "cost_after_lkr": _format_num(new_f_cost),
                    "savings_lkr": _format_num(savings),
                    "reason": f"Switched dining tier from {cur_food_tier} to {next_food} local eateries."
                })
                cur_food_tier = next_food
                cur_food_data = new_f_clean

                cur_summary = build_cost_summary(
                    fuel_data=cur_fuel_data,
                    hotel_data=cur_hotel_data,
                    food_data=cur_food_data,
                    attraction_data=cur_attr_data,
                    user_budget=user_budget,
                    days=days,
                    travelers=travelers
                )

        next_food = get_next_food_tier(cur_food_tier)

    # Strategy C: Attraction Optimization (Prioritize free/low cost)
    if cur_summary["total_trip_cost_lkr"] > user_budget and cur_attr_data.get("selected_attractions"):
        prev_a_cost = cur_attr_data.get("total_cost_lkr", 0)
        free_only_list = [item for item in cur_attr_data["selected_attractions"] if item.get("is_free", False)]

        if free_only_list and len(free_only_list) < len(cur_attr_data["selected_attractions"]):
            new_a_data = dict(cur_attr_data)
            new_a_data["selected_attractions"] = free_only_list
            new_a_data["total_cost_lkr"] = sum(item.get("total_lkr", 0) for item in free_only_list)
            new_a_cost = new_a_data["total_cost_lkr"]
            savings = prev_a_cost - new_a_cost

            if savings > 0:
                changes.append({
                    "category": "attractions",
                    "original": "all_selected_attractions",
                    "optimized": "free_attractions_only",
                    "cost_before_lkr": _format_num(prev_a_cost),
                    "cost_after_lkr": _format_num(new_a_cost),
                    "savings_lkr": _format_num(savings),
                    "reason": "Replaced paid attraction entry tickets with free landmark visits."
                })
                cur_attr_data = new_a_data
                cur_summary = build_cost_summary(
                    fuel_data=cur_fuel_data,
                    hotel_data=cur_hotel_data,
                    food_data=cur_food_data,
                    attraction_data=cur_attr_data,
                    user_budget=user_budget,
                    days=days,
                    travelers=travelers
                )

    # Strategy D: Transport Optimization (Vehicle downgrade or Public Transport option)
    if cur_summary["total_trip_cost_lkr"] > user_budget:
        prev_tr_cost = cur_summary.get("transport_cost_lkr", cur_fuel_data.get("estimated_fuel_cost_lkr", 0))

        # First try private car if using SUV/luxury
        if cur_transport.strip().lower() in ("suv", "van", "luxury car"):
            new_tr_res = calculate_route_fuel_cost(cur_fuel_data.get("total_distance_km", 400), "car")
            if new_tr_res.get("success", True):
                new_tr_clean = {k: v for k, v in new_tr_res.items() if k != "success"}
                new_tr_cost = new_tr_clean.get("estimated_fuel_cost_lkr", 0)
                savings = prev_tr_cost - new_tr_cost

                if savings > 0:
                    changes.append({
                        "category": "transport",
                        "original": cur_transport,
                        "optimized": "car",
                        "cost_before_lkr": _format_num(prev_tr_cost),
                        "cost_after_lkr": _format_num(new_tr_cost),
                        "savings_lkr": _format_num(savings),
                        "reason": f"Switched vehicle type from {cur_transport} to fuel-efficient economy car."
                    })
                    cur_transport = "car"
                    cur_fuel_data = new_tr_clean
                    cur_summary = build_cost_summary(
                        fuel_data=cur_fuel_data,
                        hotel_data=cur_hotel_data,
                        food_data=cur_food_data,
                        attraction_data=cur_attr_data,
                        user_budget=user_budget,
                        days=days,
                        travelers=travelers
                    )

        # If still over budget and transport mode is unspecified or public transport, try train public transport
        req_mode = transport_mode.strip().lower() if transport_mode else ""
        if cur_summary["total_trip_cost_lkr"] > user_budget and (not req_mode or req_mode in ("bus", "train", "public transport", "public_transport")):
            try:
                try:
                    from .public_transport_calculator import calculate_public_transport_route_cost
                except ImportError:
                    from public_transport_calculator import calculate_public_transport_route_cost

                pt_res = calculate_public_transport_route_cost(cur_route, transport_mode="train", adult_travelers=adult_travelers, child_travelers=child_travelers, travelers=travelers)
                if pt_res.get("success") and pt_res.get("available"):
                    pt_cost = pt_res.get("total_cost_lkr", 0)
                    savings = prev_tr_cost - pt_cost
                    if savings > 0:
                        changes.append({
                            "category": "transport",
                            "original": cur_transport,
                            "optimized": "train",
                            "cost_before_lkr": _format_num(prev_tr_cost),
                            "cost_after_lkr": _format_num(pt_cost),
                            "savings_lkr": _format_num(savings),
                            "reason": "Train provides a lower estimated transport cost for the selected route."
                        })
                        cur_transport = "train"
                        cur_fuel_data = {"estimated_fuel_cost_lkr": 0, "fuel_applicable": False}
                        cur_summary = build_cost_summary(
                            fuel_data=cur_fuel_data,
                            hotel_data=cur_hotel_data,
                            food_data=cur_food_data,
                            attraction_data=cur_attr_data,
                            user_budget=user_budget,
                            days=days,
                            travelers=travelers,
                            public_transport_data=pt_res
                        )
            except Exception:
                pass

    # Compute final metrics
    final_total = cur_summary["total_trip_cost_lkr"]
    savings_lkr = _format_num(max(0.0, orig_total - final_total))
    savings_pct = 0.0 if orig_total == 0 else round((savings_lkr / orig_total) * 100, 2)
    rem_budget = _format_num(max(0.0, user_budget - final_total))
    rem_deficit = _format_num(max(0.0, final_total - user_budget))

    # Determine optimization status
    if final_total <= user_budget:
        opt_status = "optimized_within_budget"
        recommendations.append("Applying accommodation and dining tier optimizations brought the trip within budget!")
    elif savings_lkr > 0:
        opt_status = "partially_optimized"
        recommendations.append("Applied available tier downgrades, reducing costs significantly. Small remaining deficit exists.")
    else:
        opt_status = "cannot_meet_budget"
        recommendations.append("The target budget is unrealistically low even for minimum baseline accommodation, food, and transport rates.")

    return {
        "optimization_status": opt_status,
        "original_cost_lkr": _format_num(orig_total),
        "optimized_cost_lkr": _format_num(final_total),
        "user_budget_lkr": _format_num(user_budget),
        "savings_lkr": savings_lkr,
        "savings_percentage": savings_pct,
        "remaining_budget_lkr": rem_budget,
        "remaining_deficit_lkr": rem_deficit,
        "changes": changes,
        "optimized_route": str(cur_route),
        "recommendations": recommendations,
        "optimized_trip": {
            "fuel_cost": cur_fuel_data,
            "hotel_cost": cur_hotel_data,
            "food_cost": cur_food_data,
            "attraction_cost": cur_attr_data,
            "trip_cost": cur_summary
        }
    }
