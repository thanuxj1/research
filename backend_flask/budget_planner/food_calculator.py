import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

logger = logging.getLogger(__name__)

DEFAULT_FOOD_PRICES_CSV = Path(__file__).resolve().parent / "food_prices.csv"

_FOOD_PRICES_CACHE: Optional[Dict[Tuple[str, str], dict]] = None


def load_food_data(csv_path: Optional[Union[str, Path]] = None) -> Dict[Tuple[str, str], dict]:
    """Load food prices dataset from CSV into memory.
    
    Returns:
        dict: (destination_lower, food_tier_lower) -> dict of meal rates in LKR.
    """
    global _FOOD_PRICES_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_FOOD_PRICES_CSV

    if not target_path.exists():
        logger.error(f"Food prices dataset not found at path: {target_path}")
        raise FileNotFoundError(f"Food prices dataset missing: {target_path}")

    food_map: Dict[Tuple[str, str], dict] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            dest_raw = row.get("destination", "").strip()
            tier_raw = row.get("food_tier", "").strip()

            if not dest_raw or not tier_raw or dest_raw.startswith("#"):
                continue

            try:
                b_lkr = float(row.get("breakfast_lkr", 0))
                l_lkr = float(row.get("lunch_lkr", 0))
                d_lkr = float(row.get("dinner_lkr", 0))
                s_lkr = float(row.get("snacks_lkr", 0))
            except ValueError:
                logger.warning(f"Invalid meal price at row {line_num}: {row}")
                continue

            key = (dest_raw.lower(), tier_raw.lower())
            food_map[key] = {
                "destination": dest_raw,
                "food_tier": tier_raw.lower(),
                "breakfast_lkr": int(b_lkr) if b_lkr.is_integer() else round(b_lkr, 2),
                "lunch_lkr": int(l_lkr) if l_lkr.is_integer() else round(l_lkr, 2),
                "dinner_lkr": int(d_lkr) if d_lkr.is_integer() else round(d_lkr, 2),
                "snacks_lkr": int(s_lkr) if s_lkr.is_integer() else round(s_lkr, 2)
            }

    _FOOD_PRICES_CACHE = food_map
    return food_map


def _get_food_data() -> Dict[Tuple[str, str], dict]:
    global _FOOD_PRICES_CACHE
    if _FOOD_PRICES_CACHE is None:
        load_food_data()
    return _FOOD_PRICES_CACHE  # type: ignore


def normalize_food_tier(tier: Optional[str]) -> str:
    """Normalize food tier string."""
    if not tier:
        return "standard"
    t_norm = tier.strip().lower()
    if t_norm in ("budget", "low", "cheap", "local"):
        return "budget"
    if t_norm in ("standard", "medium", "mid-range", "mid_range", "normal"):
        return "standard"
    if t_norm in ("premium", "high", "luxury", "fine_dining"):
        return "premium"
    raise ValueError(f"Invalid food tier: '{tier}'. Supported tiers: 'budget', 'standard', 'premium'")


def get_destination_food_rate(destination: str, food_tier: str = "standard") -> Tuple[dict, bool]:
    """Retrieve food rates for a destination and tier.
    
    Returns:
        tuple: (rate_dict, is_fallback: bool)
    """
    if not destination or not isinstance(destination, str):
        raise ValueError("Destination must be a non-empty string")

    tier_norm = normalize_food_tier(food_tier)
    food_map = _get_food_data()

    dest_norm = destination.strip().lower()

    key = (dest_norm, tier_norm)
    if key in food_map:
        return food_map[key], False

    # Fallback to regional default
    default_key = ("default", tier_norm)
    if default_key in food_map:
        rate_copy = dict(food_map[default_key])
        rate_copy["destination"] = destination.strip()
        return rate_copy, True

    raise KeyError(f"Food price data missing for tier: '{tier_norm}'")


def parse_food_route(route: Union[str, List[str]]) -> List[str]:
    """Parse route string or list into normalized list of destination stops."""
    if isinstance(route, list):
        return [str(s).strip() for s in route if str(s).strip()]

    if not isinstance(route, str) or not route.strip():
        return []

    cleaned = re.sub(r'\s*(?:->|→|-->|=>)\s*', '|', route.strip())
    return [s.strip() for s in cleaned.split('|') if s.strip()]


def calculate_daily_food_cost(
    destination: str,
    food_tier: str = "standard",
    travelers: int = 1,
    include_snacks: bool = False,
    food_preferences: Optional[dict] = None
) -> dict:
    """Calculate daily per-person and total group meal costs for a destination.
    
    Formula:
        daily_per_person = breakfast + lunch + dinner + snacks (if active)
        daily_group_total = daily_per_person * travelers
    """
    if not isinstance(travelers, int) or travelers <= 0:
        raise ValueError("Travelers must be a positive integer greater than zero")

    rate, is_fallback = get_destination_food_rate(destination, food_tier)

    prefs = food_preferences or {}
    b_active = prefs.get("breakfast", True)
    l_active = prefs.get("lunch", True)
    d_active = prefs.get("dinner", True)
    s_active = prefs.get("snacks", include_snacks)

    b_cost = rate["breakfast_lkr"] if b_active else 0
    l_cost = rate["lunch_lkr"] if l_active else 0
    d_cost = rate["dinner_lkr"] if d_active else 0
    s_cost = rate["snacks_lkr"] if s_active else 0

    per_person_lkr = b_cost + l_cost + d_cost + s_cost
    total_lkr = per_person_lkr * travelers

    return {
        "destination": destination,
        "food_tier": rate["food_tier"],
        "breakfast_lkr": b_cost,
        "lunch_lkr": l_cost,
        "dinner_lkr": d_cost,
        "snacks_lkr": s_cost,
        "per_person_lkr": per_person_lkr,
        "travelers": travelers,
        "total_lkr": total_lkr,
        "is_fallback": is_fallback
    }


def calculate_route_food_cost(
    route: Union[str, List[str]],
    days: int,
    travelers: int = 2,
    food_tier: str = "standard",
    include_snacks: bool = False,
    food_preferences: Optional[dict] = None,
    user_budget: Optional[float] = None
) -> dict:
    """Calculate total route food expenses over trip duration and itinerary.
    
    Args:
        route: Itinerary route string or destination list.
        days: Trip duration in days (> 0).
        travelers: Number of travelers (> 0).
        food_tier: Dining category ('budget', 'standard', 'premium').
        include_snacks: Whether optional snacks allowance is enabled.
        food_preferences: Optional meal override dict {'breakfast': True, ...}.
        user_budget: Stated total budget in LKR for budget impact checks.
        
    Returns:
        dict: Calculation results breakdown or error dictionary.
    """
    try:
        if not isinstance(days, int) or days <= 0:
            return {
                "success": False,
                "error": "Days must be a positive integer greater than zero"
            }

        if not isinstance(travelers, int) or travelers <= 0:
            return {
                "success": False,
                "error": "Travelers must be a positive integer greater than zero"
            }

        stops = parse_food_route(route)
        if not stops:
            return {
                "success": False,
                "error": "Route is empty or invalid"
            }

        tier_norm = normalize_food_tier(food_tier)

        # Map each travel day 1..days to a route destination
        daily_breakdown: List[dict] = []
        total_food_cost = 0

        num_stops = len(stops)

        for day in range(1, days + 1):
            # Select destination for day: cycle or step through stops
            if num_stops == 1:
                dest = stops[0]
            elif day <= num_stops:
                dest = stops[day - 1]
            else:
                dest = stops[(day - 1) % num_stops]

            day_calc = calculate_daily_food_cost(
                destination=dest,
                food_tier=tier_norm,
                travelers=travelers,
                include_snacks=include_snacks,
                food_preferences=food_preferences
            )

            day_item = {
                "day": day,
                "destination": dest,
                "breakfast_lkr": day_calc["breakfast_lkr"],
                "lunch_lkr": day_calc["lunch_lkr"],
                "dinner_lkr": day_calc["dinner_lkr"],
                "snacks_lkr": day_calc["snacks_lkr"],
                "per_person_lkr": day_calc["per_person_lkr"],
                "travelers": travelers,
                "total_lkr": day_calc["total_lkr"],
                "is_fallback": day_calc["is_fallback"]
            }

            daily_breakdown.append(day_item)
            total_food_cost += day_calc["total_lkr"]

        daily_average = int(total_food_cost / days) if (total_food_cost / days).is_integer() else round(total_food_cost / days, 2)
        per_person_total = int(total_food_cost / travelers) if (total_food_cost / travelers).is_integer() else round(total_food_cost / travelers, 2)

        budget_impact = "normal"
        if user_budget and user_budget > 0:
            if total_food_cost > (user_budget * 0.4):
                budget_impact = "high"
            elif total_food_cost < (user_budget * 0.15):
                budget_impact = "low"

        return {
            "success": True,
            "food_tier": tier_norm,
            "travelers": travelers,
            "days": days,
            "include_snacks": include_snacks,
            "total_cost_lkr": total_food_cost,
            "daily_average_lkr": daily_average,
            "per_person_total_lkr": per_person_total,
            "budget_impact": budget_impact,
            "daily_breakdown": daily_breakdown
        }

    except FileNotFoundError as fnf_err:
        return {
            "success": False,
            "error": str(fnf_err)
        }
    except ValueError as val_err:
        return {
            "success": False,
            "error": str(val_err)
        }
    except Exception as ex:
        logger.exception("Failed to calculate route food cost")
        return {
            "success": False,
            "error": f"Food calculation failed: {str(ex)}"
        }
