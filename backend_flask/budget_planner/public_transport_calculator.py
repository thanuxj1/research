import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

try:
    from .fuel_calculator import calculate_route_fuel_cost
except ImportError:
    from fuel_calculator import calculate_route_fuel_cost

logger = logging.getLogger(__name__)

DEFAULT_TRANSPORT_FARES_CSV = Path(__file__).resolve().parent / "public_transport_fares.csv"

_FARES_CACHE: Optional[Dict[Tuple[str, str, str, str], dict]] = None

# Qualitative research trade-off metadata
MODE_METADATA = {
    "private car": {"comfort_level": "high", "flexibility": "high", "cost_priority": "medium"},
    "suv": {"comfort_level": "very_high", "flexibility": "high", "cost_priority": "high"},
    "motorcycle": {"comfort_level": "low", "flexibility": "high", "cost_priority": "low"},
    "train": {"comfort_level": "medium", "flexibility": "medium", "cost_priority": "low"},
    "bus": {"comfort_level": "medium", "flexibility": "medium", "cost_priority": "low"}
}


def _format_num(val: Union[int, float]) -> Union[int, float]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return round(val, 2)


def load_transport_fare_data(csv_path: Optional[Union[str, Path]] = None) -> Dict[Tuple[str, str, str, str], dict]:
    """Load public transport fare benchmark dataset into memory cache.
    
    Returns:
        dict: (origin_lower, dest_lower, mode_lower, class_lower) -> fare details dict.
    """
    global _FARES_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_TRANSPORT_FARES_CSV

    if not target_path.exists():
        logger.error(f"Public transport fares dataset missing at path: {target_path}")
        raise FileNotFoundError(f"Public transport fares dataset missing: {target_path}")

    fares_map: Dict[Tuple[str, str, str, str], dict] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            orig_raw = row.get("origin", "").strip()
            dest_raw = row.get("destination", "").strip()
            mode_raw = row.get("transport_mode", "").strip().lower()
            class_raw = row.get("fare_class", "").strip().lower()

            if not orig_raw or not dest_raw or orig_raw.startswith("#"):
                continue

            try:
                adult_f = float(row.get("adult_fare_lkr", 0))
                child_f = float(row.get("child_fare_lkr", 0))
            except ValueError:
                logger.warning(f"Invalid fare at row {line_num}: {row}")
                continue

            entry = {
                "origin": orig_raw,
                "destination": dest_raw,
                "transport_mode": mode_raw,
                "fare_class": class_raw,
                "adult_fare_lkr": _format_num(adult_f),
                "child_fare_lkr": _format_num(child_f),
                "effective_date": row.get("effective_date", "2026").strip(),
                "data_source": row.get("data_source", "Research Benchmark Estimate").strip()
            }

            key_fwd = (orig_raw.lower(), dest_raw.lower(), mode_raw, class_raw)
            key_rev = (dest_raw.lower(), orig_raw.lower(), mode_raw, class_raw)

            fares_map[key_fwd] = entry
            if key_rev not in fares_map:
                rev_entry = dict(entry)
                rev_entry["origin"] = dest_raw
                rev_entry["destination"] = orig_raw
                fares_map[key_rev] = rev_entry

    _FARES_CACHE = fares_map
    return fares_map


def _get_fare_data() -> Dict[Tuple[str, str, str, str], dict]:
    global _FARES_CACHE
    if _FARES_CACHE is None:
        load_transport_fare_data()
    return _FARES_CACHE  # type: ignore


def parse_transport_route(route: Union[str, List[str]]) -> List[str]:
    """Parse route string or list into normalized destination list."""
    if isinstance(route, list):
        return [str(s).strip() for s in route if str(s).strip()]

    if not isinstance(route, str) or not route.strip():
        return []

    cleaned = re.sub(r'\s*(?:->|→|-->|=>)\s*', '|', route.strip())
    return [s.strip() for s in cleaned.split('|') if s.strip()]


def get_public_transport_fare(
    origin: str,
    destination: str,
    transport_mode: str = "train",
    fare_class: Optional[str] = None
) -> Tuple[dict, str]:
    """Look up public transport fare for a leg.
    
    Returns:
        tuple: (fare_entry_dict, resolved_fare_class)
    """
    if not origin or not destination:
        raise ValueError("Origin and destination must be non-empty strings")

    mode_norm = transport_mode.strip().lower()
    if mode_norm not in ("bus", "train"):
        raise ValueError(f"Unsupported public transport mode: '{transport_mode}'. Must be 'bus' or 'train'")

    orig_norm = origin.strip().lower()
    dest_norm = destination.strip().lower()

    if not fare_class:
        class_norm = "second_class" if mode_norm == "train" else "ordinary"
    else:
        class_norm = fare_class.strip().lower()

    fares = _get_fare_data()
    key = (orig_norm, dest_norm, mode_norm, class_norm)

    if key in fares:
        return fares[key], class_norm

    # Fallback to alternative fare class for same leg and mode
    for (o, d, m, c), item in fares.items():
        if o == orig_norm and d == dest_norm and m == mode_norm:
            return item, c

    raise KeyError(f"Fare data unavailable for route: '{origin}' -> '{destination}' via {mode_norm}")


def calculate_public_transport_leg_cost(
    origin: str,
    destination: str,
    transport_mode: str = "train",
    fare_class: Optional[str] = None,
    adult_travelers: int = 1,
    child_travelers: int = 0
) -> dict:
    """Calculate public transport fare cost for a single route leg.
    
    Formula:
        leg_total = (adult_fare * adult_travelers) + (child_fare * child_travelers)
    """
    if adult_travelers < 0 or child_travelers < 0 or (adult_travelers + child_travelers) <= 0:
        raise ValueError("Adult and child traveler counts must be non-negative with total > 0")

    fare_entry, resolved_class = get_public_transport_fare(origin, destination, transport_mode, fare_class)

    adult_f = float(fare_entry["adult_fare_lkr"])
    child_f = float(fare_entry["child_fare_lkr"])

    adult_cost = adult_f * adult_travelers
    child_cost = child_f * child_travelers
    leg_total = adult_cost + child_cost

    return {
        "from": fare_entry["origin"],
        "to": fare_entry["destination"],
        "transport_mode": fare_entry["transport_mode"],
        "fare_class": resolved_class,
        "adult_fare_lkr": _format_num(adult_f),
        "child_fare_lkr": _format_num(child_f),
        "adult_cost_lkr": _format_num(adult_cost),
        "child_cost_lkr": _format_num(child_cost),
        "total_lkr": _format_num(leg_total),
        "available": True
    }


def calculate_public_transport_route_cost(
    route: Union[str, List[str]],
    transport_mode: str = "train",
    fare_class: Optional[str] = None,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    travelers: int = 2
) -> dict:
    """Calculate total public transport route expenses across all consecutive legs.
    
    Returns:
        dict: Detailed public transport breakdown object.
    """
    try:
        mode_norm = transport_mode.strip().lower()
        if mode_norm not in ("bus", "train"):
            return {
                "success": False,
                "available": False,
                "error": f"Unsupported public transport mode: '{transport_mode}'"
            }

        # Resolve traveler counts
        if adult_travelers is None and child_travelers is None:
            if not isinstance(travelers, int) or travelers <= 0:
                return {
                    "success": False,
                    "available": False,
                    "error": "Travelers must be a positive integer greater than zero"
                }
            n_adults = travelers
            n_children = 0
        else:
            n_adults = adult_travelers if adult_travelers is not None else 0
            n_children = child_travelers if child_travelers is not None else 0

        if n_adults < 0 or n_children < 0 or (n_adults + n_children) <= 0:
            return {
                "success": False,
                "available": False,
                "error": "Adult and child counts must be non-negative with positive sum"
            }

        stops = parse_transport_route(route)
        if len(stops) < 2:
            return {
                "success": False,
                "available": False,
                "error": "Route must contain at least 2 destinations"
            }

        legs_list: List[dict] = []
        total_fare_cost = 0.0
        all_available = True
        resolved_class = fare_class or ("second_class" if mode_norm == "train" else "ordinary")

        for i in range(len(stops) - 1):
            orig = stops[i]
            dest = stops[i + 1]

            try:
                leg_calc = calculate_public_transport_leg_cost(
                    origin=orig,
                    destination=dest,
                    transport_mode=mode_norm,
                    fare_class=fare_class,
                    adult_travelers=n_adults,
                    child_travelers=n_children
                )
                legs_list.append(leg_calc)
                total_fare_cost += leg_calc["total_lkr"]
                resolved_class = leg_calc["fare_class"]
            except KeyError:
                all_available = False
                legs_list.append({
                    "from": orig,
                    "to": dest,
                    "transport_mode": mode_norm,
                    "fare_class": resolved_class,
                    "available": False,
                    "reason": f"Fare data unavailable for leg: '{orig}' -> '{dest}'"
                })

        return {
            "success": True,
            "available": all_available,
            "transport_mode": mode_norm,
            "fare_class": resolved_class,
            "adult_travelers": n_adults,
            "child_travelers": n_children,
            "total_travelers": n_adults + n_children,
            "total_cost_lkr": _format_num(total_fare_cost),
            "legs": legs_list,
            "data_source": "Research Benchmark Estimate",
            "effective_date": "2026"
        }

    except Exception as ex:
        logger.exception("Public transport calculation failed")
        return {
            "success": False,
            "available": False,
            "error": f"Public transport calculation failed: {str(ex)}"
        }


def compare_transport_costs(
    route: Union[str, List[str]],
    total_distance_km: float,
    selected_mode: str = "private car",
    travelers: int = 2,
    adult_travelers: Optional[int] = None,
    child_travelers: Optional[int] = None,
    custom_efficiency: Optional[float] = None
) -> dict:
    """Compare trip transport costs across private vehicles and public transit options.
    
    Returns:
        dict: Detailed transport_comparison output payload.
    """
    mode_norm = selected_mode.strip().lower()
    all_modes = ["private car", "suv", "motorcycle", "train", "bus"]

    mode_costs: Dict[str, Optional[float]] = {}
    mode_details: Dict[str, dict] = {}

    for mode in all_modes:
        if mode in ("bus", "train"):
            res = calculate_public_transport_route_cost(
                route=route,
                transport_mode=mode,
                adult_travelers=adult_travelers,
                child_travelers=child_travelers,
                travelers=travelers
            )
            if res.get("success") and res.get("available"):
                mode_costs[mode] = res["total_cost_lkr"]
                mode_details[mode] = res
            else:
                mode_costs[mode] = None
        else:
            res = calculate_route_fuel_cost(
                total_distance_km=total_distance_km,
                transport_mode=mode,
                custom_efficiency=custom_efficiency
            )
            if res.get("success") and res.get("fuel_applicable"):
                mode_costs[mode] = res["estimated_fuel_cost_lkr"]
                mode_details[mode] = res
            else:
                mode_costs[mode] = None

    selected_cost = mode_costs.get(mode_norm)

    alternatives: List[dict] = []
    cheapest_mode = mode_norm
    cheapest_cost = selected_cost if selected_cost is not None else float("inf")

    for mode, cost in mode_costs.items():
        if cost is not None and cost < cheapest_cost:
            cheapest_cost = cost
            cheapest_mode = mode

        if mode != mode_norm and cost is not None and selected_cost is not None:
            meta = MODE_METADATA.get(mode, {"comfort_level": "medium", "flexibility": "medium", "cost_priority": "medium"})

            if cost < selected_cost:
                savings = selected_cost - cost
                savings_pct = round((savings / selected_cost) * 100, 2)
                alternatives.append({
                    "mode": mode,
                    "cost_lkr": _format_num(cost),
                    "savings_lkr": _format_num(savings),
                    "savings_percentage": savings_pct,
                    "comfort_level": meta["comfort_level"],
                    "flexibility": meta["flexibility"],
                    "cost_priority": meta["cost_priority"]
                })
            else:
                extra = cost - selected_cost
                alternatives.append({
                    "mode": mode,
                    "cost_lkr": _format_num(cost),
                    "additional_cost_lkr": _format_num(extra),
                    "comfort_level": meta["comfort_level"],
                    "flexibility": meta["flexibility"],
                    "cost_priority": meta["cost_priority"]
                })

    return {
        "selected_mode": mode_norm,
        "selected_mode_cost_lkr": _format_num(selected_cost) if selected_cost is not None else 0.0,
        "cheapest_option": cheapest_mode,
        "cheapest_cost_lkr": _format_num(cheapest_cost) if cheapest_cost != float("inf") else 0.0,
        "alternatives": alternatives
    }
