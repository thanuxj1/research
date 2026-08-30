import csv
import logging
import math
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

logger = logging.getLogger(__name__)

DEFAULT_HOTELS_CSV = Path(__file__).resolve().parent / "hotels_300.csv"

_HOTEL_DATA_CACHE: Optional[Dict[str, List[dict]]] = None


def load_hotel_data(csv_path: Optional[Union[str, Path]] = None) -> Dict[str, List[dict]]:
    """Load and parse hotels_300.csv dataset.
    
    Returns:
        dict: Lowercased place name -> sorted list of hotel dicts by avg_price_lkr ascending.
    """
    global _HOTEL_DATA_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_HOTELS_CSV

    if not target_path.exists():
        logger.error(f"Hotels dataset missing at path: {target_path}")
        raise FileNotFoundError(f"Hotels dataset missing: {target_path}")

    hotels_by_place: Dict[str, List[dict]] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            place_raw = row.get("place", "").strip()
            hotel_name = row.get("hotel_name", "").strip()
            price_str = row.get("avg_price_lkr", "").strip()

            if not place_raw or not hotel_name or not price_str:
                continue

            try:
                price_val = float(price_str)
                if price_val <= 0:
                    continue
            except ValueError:
                logger.warning(f"Invalid price format at row {line_num}: '{price_str}'")
                continue

            place_norm = place_raw.lower()

            hotel_entry = {
                "place": place_raw,
                "hotel_name": hotel_name,
                "avg_price_lkr": int(price_val) if price_val.is_integer() else round(price_val, 2)
            }

            if place_norm not in hotels_by_place:
                hotels_by_place[place_norm] = []

            hotels_by_place[place_norm].append(hotel_entry)

    # Sort hotels for each destination by price ascending
    for place_norm in hotels_by_place:
        hotels_by_place[place_norm].sort(key=lambda h: h["avg_price_lkr"])

    _HOTEL_DATA_CACHE = hotels_by_place
    return hotels_by_place


def _get_hotel_data() -> Dict[str, List[dict]]:
    global _HOTEL_DATA_CACHE
    if _HOTEL_DATA_CACHE is None:
        load_hotel_data()
    return _HOTEL_DATA_CACHE  # type: ignore


def parse_route_destinations(route: Union[str, List[str]]) -> List[str]:
    """Parse route string or list into clean list of stop names."""
    if isinstance(route, list):
        return [str(s).strip() for s in route if str(s).strip()]

    if not isinstance(route, str) or not route.strip():
        return []

    cleaned = re.sub(r'\s*(?:->|→|-->|=>)\s*', '|', route.strip())
    return [s.strip() for s in cleaned.split('|') if s.strip()]


def calculate_nights(days: int) -> int:
    """Calculate total overnight stays for trip duration."""
    if not isinstance(days, int) or days <= 0:
        raise ValueError("Days must be a positive integer greater than zero")
    return max(0, days - 1)


def determine_overnight_stays(route: Union[str, List[str]], days: int) -> List[Tuple[str, int]]:
    """Determine overnight stay locations and night counts for a route and duration.
    
    Rule:
    - Total nights = days - 1.
    - Excludes start/end Colombo unless Colombo is the only destination.
    - Distributes total nights evenly across intermediate stops.
    """
    total_nights = calculate_nights(days)
    stops = parse_route_destinations(route)

    if not stops or total_nights == 0:
        return []

    # Exclude Colombo start/end if part of a round trip
    if len(stops) > 2 and stops[0].lower() == "colombo" and stops[-1].lower() == "colombo":
        overnight_candidates = stops[1:-1]
    elif len(stops) > 1 and stops[0].lower() == "colombo":
        overnight_candidates = stops[1:]
    else:
        overnight_candidates = stops[:-1] if len(stops) > 1 else stops

    if not overnight_candidates:
        overnight_candidates = [stops[0]]

    n_candidates = len(overnight_candidates)

    if n_candidates == 0:
        return []

    base_nights = total_nights // n_candidates
    extra_nights = total_nights % n_candidates

    result: List[Tuple[str, int]] = []
    for i, dest in enumerate(overnight_candidates):
        nights_assigned = base_nights + (1 if i < extra_nights else 0)
        if nights_assigned > 0:
            result.append((dest, nights_assigned))

    return result


def get_hotels_by_destination(destination: str) -> List[dict]:
    """Retrieve list of available hotels in destination, sorted by price."""
    if not destination or not isinstance(destination, str):
        raise ValueError("Destination must be a non-empty string")

    hotel_data = _get_hotel_data()
    dest_norm = destination.strip().lower()

    if dest_norm not in hotel_data or not hotel_data[dest_norm]:
        raise KeyError(f"No hotel data available for destination: '{destination.strip()}'")

    return hotel_data[dest_norm]


def normalize_tier(tier: Optional[str]) -> str:
    """Normalize hotel tier string."""
    if not tier:
        return "mid-range"
    t_norm = tier.strip().lower()
    if t_norm in ("budget", "low", "economy"):
        return "budget"
    if t_norm in ("mid-range", "mid_range", "medium", "moderate"):
        return "mid-range"
    if t_norm in ("premium", "high", "luxury"):
        return "premium"
    raise ValueError(f"Invalid hotel tier: '{tier}'. Supported tiers: 'budget', 'mid-range', 'premium'")


def select_hotel(destination: str, tier: str = "mid-range") -> dict:
    """Select a deterministic hotel from dataset for a given destination and tier.
    
    Deterministic strategy:
    - budget: Lowest price hotel (index 0)
    - mid-range: Median price hotel (index len // 2)
    - premium: Highest price hotel (index -1)
    """
    hotels = get_hotels_by_destination(destination)
    tier_norm = normalize_tier(tier)

    if tier_norm == "budget":
        chosen = hotels[0]
    elif tier_norm == "premium":
        chosen = hotels[-1]
    else:  # mid-range
        chosen = hotels[len(hotels) // 2]

    return {
        "destination": chosen["place"],
        "hotel_name": chosen["hotel_name"],
        "price_per_night_lkr": chosen["avg_price_lkr"],
        "tier": tier_norm
    }


def calculate_route_hotel_cost(
    route: Union[str, List[str]],
    days: int,
    travelers: int = 2,
    hotel_tier: Optional[str] = None,
    user_budget: Optional[float] = None
) -> dict:
    """Calculate deterministic hotel accommodation costs for a route and trip parameters.
    
    Args:
        route: Itinerary route string or destination list.
        days: Trip duration in days (> 0).
        travelers: Number of travelers (> 0, default 2).
        hotel_tier: Optional tier preference ('budget', 'mid-range', 'premium').
        user_budget: Optional stated budget in LKR for budget impact checks.
        
    Returns:
        dict: Detailed accommodation calculation result or error response.
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

        stops = parse_route_destinations(route)
        if not stops:
            return {
                "success": False,
                "error": "Route is empty or invalid"
            }

        selected_tier = normalize_tier(hotel_tier)
        overnight_stays = determine_overnight_stays(route, days)
        total_nights = sum(nights for _, nights in overnight_stays)

        if total_nights == 0:
            return {
                "success": True,
                "hotel_tier": selected_tier,
                "total_nights": 0,
                "total_rooms": 0,
                "travelers": travelers,
                "total_cost_lkr": 0,
                "budget_impact": "normal",
                "stays": []
            }

        # Calculate required rooms: 1 room per 2 guests standard
        rooms_required = math.ceil(travelers / 2)

        stays_list: List[dict] = []
        total_accommodation_cost = 0

        for dest, nights in overnight_stays:
            try:
                hotels_in_dest = get_hotels_by_destination(dest)
            except KeyError as ke:
                return {
                    "success": False,
                    "error": str(ke).strip("'")
                }

            # Selected tier option
            selected_pick = select_hotel(dest, selected_tier)
            nightly_room_price = selected_pick["price_per_night_lkr"]
            nightly_total_for_group = nightly_room_price * rooms_required
            stay_total_lkr = nightly_total_for_group * nights

            # Generate full tier options breakdown for this stay
            tier_options = {}
            for t_name in ("budget", "mid-range", "premium"):
                t_pick = select_hotel(dest, t_name)
                t_price = t_pick["price_per_night_lkr"]
                t_total = t_price * rooms_required * nights
                tier_key = "mid_range" if t_name == "mid-range" else t_name
                tier_options[tier_key] = {
                    "hotel_name": t_pick["hotel_name"],
                    "price_per_night_lkr": t_price,
                    "nights": nights,
                    "total_lkr": t_total
                }

            stays_list.append({
                "destination": dest,
                "nights": nights,
                "hotel_name": selected_pick["hotel_name"],
                "tier": selected_tier,
                "price_per_night_lkr": nightly_room_price,
                "rooms": rooms_required,
                "total_lkr": stay_total_lkr,
                "options": tier_options
            })

            total_accommodation_cost += stay_total_lkr

        # Budget impact assessment
        budget_impact = "normal"
        if user_budget and user_budget > 0:
            if total_accommodation_cost > (user_budget * 0.6):
                budget_impact = "high"

        return {
            "success": True,
            "hotel_tier": selected_tier,
            "total_nights": total_nights,
            "total_rooms": rooms_required,
            "travelers": travelers,
            "total_cost_lkr": total_accommodation_cost,
            "budget_impact": budget_impact,
            "stays": stays_list
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
        logger.exception("Failed to calculate route hotel cost")
        return {
            "success": False,
            "error": f"Hotel calculation failed: {str(ex)}"
        }
