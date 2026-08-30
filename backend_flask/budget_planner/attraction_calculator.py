import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

logger = logging.getLogger(__name__)

DEFAULT_ATTRACTIONS_CSV = Path(__file__).resolve().parent / "attractions.csv"
MAX_ATTRACTIONS_PER_DESTINATION = 2

# Map user interest category to primary and secondary attraction categories
INTEREST_CATEGORY_MAP: Dict[str, List[str]] = {
    "cultural": ["cultural", "nature"],
    "nature": ["nature", "cultural"],
    "wildlife": ["wildlife", "nature"],
    "adventure": ["adventure", "nature"],
    "beach": ["beach", "nature"]
}

_ATTRACTIONS_CACHE: Optional[Dict[str, List[dict]]] = None


def load_attraction_data(csv_path: Optional[Union[str, Path]] = None) -> Dict[str, List[dict]]:
    """Load attractions dataset from CSV into memory.
    
    Returns:
        dict: Lowercased destination -> list of attraction dicts.
    """
    global _ATTRACTIONS_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_ATTRACTIONS_CSV

    if not target_path.exists():
        logger.error(f"Attractions dataset missing at path: {target_path}")
        raise FileNotFoundError(f"Attractions dataset missing: {target_path}")

    attractions_map: Dict[str, List[dict]] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            dest_raw = row.get("destination", "").strip()
            name_raw = row.get("attraction_name", "").strip()
            cat_raw = row.get("category", "").strip().lower()

            if not dest_raw or not name_raw or dest_raw.startswith("#"):
                continue

            try:
                adult_p = float(row.get("adult_price_lkr", 0))
                child_p = float(row.get("child_price_lkr", 0))
                act_p = float(row.get("activity_price_lkr", 0))
                is_free_val = str(row.get("is_free", "false")).strip().lower() in ("true", "1", "yes")
            except ValueError:
                logger.warning(f"Invalid price at row {line_num}: {row}")
                continue

            dest_norm = dest_raw.lower()

            attraction_entry = {
                "destination": dest_raw,
                "attraction_name": name_raw,
                "category": cat_raw,
                "adult_price_lkr": int(adult_p) if adult_p.is_integer() else round(adult_p, 2),
                "child_price_lkr": int(child_p) if child_p.is_integer() else round(child_p, 2),
                "activity_price_lkr": int(act_p) if act_p.is_integer() else round(act_p, 2),
                "is_free": is_free_val,
                "effective_date": row.get("effective_date", "").strip(),
                "data_source": row.get("data_source", "").strip()
            }

            if dest_norm not in attractions_map:
                attractions_map[dest_norm] = []

            attractions_map[dest_norm].append(attraction_entry)

    _ATTRACTIONS_CACHE = attractions_map
    return attractions_map


def _get_attraction_data() -> Dict[str, List[dict]]:
    global _ATTRACTIONS_CACHE
    if _ATTRACTIONS_CACHE is None:
        load_attraction_data()
    return _ATTRACTIONS_CACHE  # type: ignore


def parse_attraction_route(route: Union[str, List[str]]) -> List[str]:
    """Parse route string or list into normalized destination list."""
    if isinstance(route, list):
        return [str(s).strip() for s in route if str(s).strip()]

    if not isinstance(route, str) or not route.strip():
        return []

    cleaned = re.sub(r'\s*(?:->|→|-->|=>)\s*', '|', route.strip())
    return [s.strip() for s in cleaned.split('|') if s.strip()]


def get_destination_attractions(destination: str, category: Optional[str] = None) -> List[dict]:
    """Retrieve list of attractions for a destination, optionally filtered by category."""
    if not destination or not isinstance(destination, str):
        raise ValueError("Destination must be a non-empty string")

    attr_data = _get_attraction_data()
    dest_norm = destination.strip().lower()

    if dest_norm not in attr_data or not attr_data[dest_norm]:
        raise KeyError(f"No attraction data available for destination: '{destination.strip()}'")

    items = attr_data[dest_norm]

    if category:
        cat_norm = category.strip().lower()
        filtered = [item for item in items if item["category"] == cat_norm]
        return filtered

    return items


def select_attractions(
    destination: str,
    interest: Optional[str] = None,
    max_count: int = MAX_ATTRACTIONS_PER_DESTINATION
) -> List[dict]:
    """Select up to max_count attractions for a destination matching user interest category."""
    all_attrs = get_destination_attractions(destination)

    if not interest:
        return all_attrs[:max_count]

    interest_norm = interest.strip().lower()
    categories_to_try = INTEREST_CATEGORY_MAP.get(interest_norm, [interest_norm])

    selected: List[dict] = []
    selected_names = set()

    for cat in categories_to_try:
        for attr in all_attrs:
            if attr["category"] == cat and attr["attraction_name"] not in selected_names:
                selected.append(attr)
                selected_names.add(attr["attraction_name"])
                if len(selected) >= max_count:
                    return selected

    # Fill remaining with any available destination attraction
    for attr in all_attrs:
        if attr["attraction_name"] not in selected_names:
            selected.append(attr)
            selected_names.add(attr["attraction_name"])
            if len(selected) >= max_count:
                return selected

    return selected[:max_count]


def calculate_attraction_cost(
    attraction: dict,
    adult_travelers: int = 1,
    child_travelers: int = 0
) -> dict:
    """Calculate entrance and activity expenses for a specific attraction.
    
    Formula:
        adult_entrance = adult_price * adult_travelers (0 if is_free)
        child_entrance = child_price * child_travelers (0 if is_free)
        activity_cost = activity_price * (adult_travelers + child_travelers)
        total_lkr = adult_entrance + child_entrance + activity_cost
    """
    if adult_travelers < 0 or child_travelers < 0 or (adult_travelers + child_travelers) <= 0:
        raise ValueError("Travelers count must be positive and non-negative")

    is_free = bool(attraction.get("is_free", False))
    adult_p = float(attraction.get("adult_price_lkr", 0))
    child_p = float(attraction.get("child_price_lkr", 0))
    act_p = float(attraction.get("activity_price_lkr", 0))

    adult_cost = 0.0 if is_free else (adult_p * adult_travelers)
    child_cost = 0.0 if is_free else (child_p * child_travelers)
    total_group = adult_travelers + child_travelers
    activity_cost = act_p * total_group

    total_lkr = adult_cost + child_cost + activity_cost

    return {
        "destination": attraction.get("destination", ""),
        "attraction_name": attraction.get("attraction_name", ""),
        "category": attraction.get("category", ""),
        "adult_price_lkr": int(adult_p) if adult_p.is_integer() else round(adult_p, 2),
        "child_price_lkr": int(child_p) if child_p.is_integer() else round(child_p, 2),
        "activity_price_lkr": int(act_p) if act_p.is_integer() else round(act_p, 2),
        "adult_cost_lkr": int(adult_cost) if adult_cost.is_integer() else round(adult_cost, 2),
        "child_cost_lkr": int(child_cost) if child_cost.is_integer() else round(child_cost, 2),
        "activity_cost_lkr": int(activity_cost) if activity_cost.is_integer() else round(activity_cost, 2),
        "total_lkr": int(total_lkr) if total_lkr.is_integer() else round(total_lkr, 2),
        "is_free": is_free
    }


def calculate_route_attraction_cost(
    route: Union[str, List[str]],
    days: int,
    travelers: int = 2,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    interest: str = "nature",
    user_budget: Optional[float] = None
) -> dict:
    """Calculate deterministic attraction and activity costs for a route.
    
    Args:
        route: Itinerary route string or destination list.
        days: Trip duration in days (> 0).
        travelers: Total travelers count (> 0).
        adult_travelers: Adult count (defaults to travelers if not provided).
        child_travelers: Child count (defaults to 0 if not provided).
        interest: User travel interest category.
        user_budget: Optional stated budget in LKR for budget impact checks.
        
    Returns:
        dict: Detailed calculation breakdown or error response.
    """
    try:
        if not isinstance(days, int) or days <= 0:
            return {
                "success": False,
                "error": "Days must be a positive integer greater than zero"
            }

        # Resolve adult and child counts
        if adult_travelers is None and child_travelers is None:
            if not isinstance(travelers, int) or travelers <= 0:
                return {
                    "success": False,
                    "error": "Travelers must be a positive integer greater than zero"
                }
            n_adults = travelers
            n_children = 0
        else:
            n_adults = adult_travelers if adult_travelers is not None else 0
            n_children = child_travelers if child_travelers is not None else 0

        if not isinstance(n_adults, int) or not isinstance(n_children, int):
            return {
                "success": False,
                "error": "Adult and child traveler counts must be integers"
            }

        if n_adults < 0 or n_children < 0 or (n_adults + n_children) <= 0:
            return {
                "success": False,
                "error": "Total travelers (adults + children) must be a positive number greater than zero"
            }

        stops = parse_attraction_route(route)
        if not stops:
            return {
                "success": False,
                "error": "Route is empty or invalid"
            }

        # Determine visited destinations (exclude return Colombo on day trips if longer route)
        if len(stops) > 2 and stops[0].lower() == "colombo" and stops[-1].lower() == "colombo":
            visited_destinations = stops[:-1]
        else:
            visited_destinations = stops

        # Deduplicate while preserving order
        unique_visited: List[str] = []
        for d in visited_destinations:
            if d not in unique_visited:
                unique_visited.append(d)

        selected_attractions_list: List[dict] = []
        total_attraction_cost = 0

        for dest in unique_visited:
            try:
                chosen_attrs = select_attractions(
                    destination=dest,
                    interest=interest,
                    max_count=MAX_ATTRACTIONS_PER_DESTINATION
                )
                for attr in chosen_attrs:
                    cost_calc = calculate_attraction_cost(
                        attraction=attr,
                        adult_travelers=n_adults,
                        child_travelers=n_children
                    )
                    selected_attractions_list.append(cost_calc)
                    total_attraction_cost += cost_calc["total_lkr"]

            except KeyError:
                selected_attractions_list.append({
                    "destination": dest,
                    "is_fallback": True,
                    "fallback_reason": f"No attraction data available for destination '{dest}'"
                })

        # Assess budget impact
        budget_impact = "normal"
        if user_budget and user_budget > 0:
            if total_attraction_cost > (user_budget * 0.25):
                budget_impact = "high"
            elif total_attraction_cost < (user_budget * 0.05):
                budget_impact = "low"

        return {
            "success": True,
            "total_cost_lkr": total_attraction_cost,
            "adult_travelers": n_adults,
            "child_travelers": n_children,
            "total_travelers": n_adults + n_children,
            "interest": interest,
            "budget_impact": budget_impact,
            "selected_attractions": selected_attractions_list
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
        logger.exception("Failed to calculate route attraction cost")
        return {
            "success": False,
            "error": f"Attraction calculation failed: {str(ex)}"
        }
