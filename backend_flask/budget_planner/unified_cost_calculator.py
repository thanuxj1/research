import logging
from typing import Dict, Union, Optional

logger = logging.getLogger(__name__)

SLIGHTLY_OVER_BUDGET_THRESHOLD = 1.20


def _format_num(val: Union[int, float]) -> Union[int, float]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return round(val, 2)


def calculate_total_trip_cost(
    fuel_cost_lkr: float,
    hotel_cost_lkr: float,
    food_cost_lkr: float,
    attraction_cost_lkr: float
) -> float:
    """Calculate aggregate total trip expenses across all 4 cost categories.
    
    Formula:
        total = fuel + hotel + food + attractions
    """
    if fuel_cost_lkr < 0 or hotel_cost_lkr < 0 or food_cost_lkr < 0 or attraction_cost_lkr < 0:
        raise ValueError("Cost components cannot be negative")

    total = fuel_cost_lkr + hotel_cost_lkr + food_cost_lkr + attraction_cost_lkr
    return _format_num(total)


def calculate_budget_difference(user_budget: float, total_trip_cost: float) -> float:
    """Calculate financial difference between user budget and total trip cost.
    
    Returns:
        float: Positive if under budget, negative if over budget.
    """
    diff = user_budget - total_trip_cost
    return _format_num(diff)


def calculate_budget_status(
    user_budget: float,
    total_trip_cost: float,
    threshold: float = SLIGHTLY_OVER_BUDGET_THRESHOLD
) -> str:
    """Determine deterministic budget status category based on threshold multiplier.
    
    Returns:
        str: 'within_budget', 'slightly_over_budget', or 'significantly_over_budget'
    """
    if user_budget <= 0:
        raise ValueError("User budget must be a positive number greater than zero")

    if total_trip_cost <= user_budget:
        return "within_budget"
    elif total_trip_cost <= (user_budget * threshold):
        return "slightly_over_budget"
    else:
        return "significantly_over_budget"


def calculate_cost_percentages(cost_dict: dict, total_trip_cost: float) -> dict:
    """Calculate percentage contribution of each cost category relative to total trip cost."""
    if total_trip_cost <= 0:
        return {
            "fuel": 0.0,
            "hotel": 0.0,
            "food": 0.0,
            "attractions": 0.0
        }

    fuel_p = round((cost_dict.get("fuel", 0) / total_trip_cost) * 100, 2)
    hotel_p = round((cost_dict.get("hotel", 0) / total_trip_cost) * 100, 2)
    food_p = round((cost_dict.get("food", 0) / total_trip_cost) * 100, 2)
    attr_p = round((cost_dict.get("attractions", 0) / total_trip_cost) * 100, 2)

    return {
        "fuel": fuel_p,
        "hotel": hotel_p,
        "food": food_p,
        "attractions": attr_p
    }


def build_cost_summary(
    fuel_data: Optional[dict],
    hotel_data: Optional[dict],
    food_data: Optional[dict],
    attraction_data: Optional[dict],
    user_budget: float,
    days: int,
    travelers: int,
    public_transport_data: Optional[dict] = None
) -> dict:
    """Build unified deterministic cost summary combining all component engines.
    
    Args:
        fuel_data: Fuel calculator output dictionary.
        hotel_data: Hotel calculator output dictionary.
        food_data: Food calculator output dictionary.
        attraction_data: Attraction calculator output dictionary.
        user_budget: Target user budget in LKR (> 0).
        days: Duration in days (> 0).
        travelers: Number of travelers (> 0).
        public_transport_data: Optional public transport calculator output dictionary.
        
    Returns:
        dict: Detailed trip_cost breakdown dictionary.
    """
    if user_budget is None or not isinstance(user_budget, (int, float)) or user_budget <= 0:
        raise ValueError("User budget must be a positive number greater than zero")

    if days is None or not isinstance(days, int) or days <= 0:
        raise ValueError("Days must be a positive integer greater than zero")

    if travelers is None or not isinstance(travelers, int) or travelers <= 0:
        raise ValueError("Travelers must be a positive integer greater than zero")

    if fuel_data is None or hotel_data is None or food_data is None or attraction_data is None:
        missing = []
        if fuel_data is None: missing.append("fuel_data")
        if hotel_data is None: missing.append("hotel_data")
        if food_data is None: missing.append("food_data")
        if attraction_data is None: missing.append("attraction_data")
        raise ValueError(f"Missing required cost component calculations: {', '.join(missing)}")

    # Extract component LKR totals
    if public_transport_data and public_transport_data.get("available", True) and public_transport_data.get("total_cost_lkr") is not None:
        transport_lkr = float(public_transport_data.get("total_cost_lkr", 0.0))
        fuel_lkr = 0.0  # Zero fuel to avoid double counting when public transit applies
    else:
        fuel_applicable = fuel_data.get("fuel_applicable", True)
        fuel_lkr = float(fuel_data.get("estimated_fuel_cost_lkr", 0.0)) if fuel_applicable else 0.0
        transport_lkr = fuel_lkr

    hotel_lkr = float(hotel_data.get("total_cost_lkr", 0.0))
    food_lkr = float(food_data.get("total_cost_lkr", 0.0))
    attraction_lkr = float(attraction_data.get("total_cost_lkr", 0.0))

    total_trip_cost_lkr = calculate_total_trip_cost(transport_lkr, hotel_lkr, food_lkr, attraction_lkr)
    budget_diff = calculate_budget_difference(user_budget, total_trip_cost_lkr)

    deficit_lkr = _format_num(max(0.0, total_trip_cost_lkr - user_budget))
    remaining_lkr = _format_num(max(0.0, user_budget - total_trip_cost_lkr))

    status = calculate_budget_status(user_budget, total_trip_cost_lkr)
    utilization_pct = round((total_trip_cost_lkr / user_budget) * 100, 2)

    daily_avg = _format_num(total_trip_cost_lkr / days)
    per_person_total = _format_num(total_trip_cost_lkr / travelers)
    per_person_daily = _format_num(total_trip_cost_lkr / (travelers * days))

    cost_breakdown = {
        "transport_lkr": _format_num(transport_lkr),
        "fuel_lkr": _format_num(fuel_lkr),
        "hotel_lkr": _format_num(hotel_lkr),
        "food_lkr": _format_num(food_lkr),
        "attractions_lkr": _format_num(attraction_lkr)
    }

    raw_category_costs = {
        "fuel": transport_lkr,
        "hotel": hotel_lkr,
        "food": food_lkr,
        "attractions": attraction_lkr
    }

    cost_percentages = calculate_cost_percentages(raw_category_costs, total_trip_cost_lkr)

    # Determine largest cost category
    largest_category = max(raw_category_costs, key=raw_category_costs.get)  # type: ignore
    largest_amount = raw_category_costs[largest_category]

    return {
        "total_trip_cost_lkr": total_trip_cost_lkr,
        "transport_cost_lkr": _format_num(transport_lkr),
        "user_budget_lkr": _format_num(user_budget),
        "budget_difference_lkr": budget_diff,
        "budget_deficit_lkr": deficit_lkr,
        "remaining_budget_lkr": remaining_lkr,
        "budget_status": status,
        "budget_utilization_percentage": utilization_pct,
        "daily_average_cost_lkr": daily_avg,
        "per_person_total_lkr": per_person_total,
        "per_person_daily_lkr": per_person_daily,
        "largest_cost_category": largest_category,
        "largest_cost_category_amount_lkr": _format_num(largest_amount),
        "cost_breakdown": cost_breakdown,
        "cost_percentages": cost_percentages
    }


def build_budget_analysis(ml_predicted_budget: float, real_calculated_cost: float) -> dict:
    """Build research budget analysis object comparing ML model prediction against real component cost.
    
    Returns:
        dict: budget_analysis metrics.
    """
    ml_val = float(ml_predicted_budget)
    real_val = float(real_calculated_cost)

    diff = _format_num(ml_val - real_val)
    error_pct = 0.0 if real_val == 0 else round((abs(ml_val - real_val) / real_val) * 100, 2)

    return {
        "ml_predicted_budget_lkr": _format_num(ml_val),
        "real_calculated_cost_lkr": _format_num(real_val),
        "prediction_difference_lkr": diff,
        "prediction_error_percentage": error_pct
    }

