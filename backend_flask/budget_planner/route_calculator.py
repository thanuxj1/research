import csv
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

logger = logging.getLogger(__name__)

DEFAULT_CSV_PATH = Path(__file__).resolve().parent / "destination_distances.csv"

_DISTANCE_CACHE: Optional[Dict[Tuple[str, str], float]] = None
_RAW_NAME_CACHE: Optional[Dict[str, str]] = None


def load_distance_data(csv_path: Optional[Union[str, Path]] = None) -> Dict[Tuple[str, str], float]:
    """Load Sri Lanka destination distance dataset from CSV into memory.
    
    Populates a bidirectional distance mapping with normalized city names.
    """
    global _DISTANCE_CACHE, _RAW_NAME_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_CSV_PATH

    if not target_path.exists():
        logger.error(f"Distance data file not found at path: {target_path}")
        raise FileNotFoundError(f"Distance dataset missing: {target_path}")

    distance_map: Dict[Tuple[str, str], float] = {}
    raw_name_map: Dict[str, str] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            origin_raw = row.get("from", "").strip()
            dest_raw = row.get("to", "").strip()
            dist_str = row.get("distance_km", "").strip()

            if not origin_raw or not dest_raw or not dist_str:
                logger.warning(f"Skipping incomplete row {line_num} in {target_path}: {row}")
                continue

            try:
                dist_val = float(dist_str)
                if dist_val < 0:
                    logger.warning(f"Negative distance encountered at row {line_num}: {dist_val}")
                    continue
            except ValueError:
                logger.warning(f"Invalid distance format at row {line_num}: '{dist_str}'")
                continue

            orig_norm = origin_raw.lower()
            dest_norm = dest_raw.lower()

            raw_name_map[orig_norm] = origin_raw
            raw_name_map[dest_norm] = dest_raw

            distance_map[(orig_norm, dest_norm)] = dist_val
            distance_map[(dest_norm, orig_norm)] = dist_val

    _DISTANCE_CACHE = distance_map
    _RAW_NAME_CACHE = raw_name_map
    return distance_map


def _get_distance_map() -> Dict[Tuple[str, str], float]:
    global _DISTANCE_CACHE
    if _DISTANCE_CACHE is None:
        load_distance_data()
    return _DISTANCE_CACHE  # type: ignore


def calculate_leg_distance(origin: str, destination: str) -> dict:
    """Calculate distance between two consecutive destinations.
    
    Args:
        origin: Departure destination name
        destination: Arrival destination name
        
    Returns:
        dict: {"from": origin, "to": destination, "distance_km": distance}
        
    Raises:
        KeyError: If distance data between origin and destination is unavailable.
    """
    if not origin or not destination:
        raise ValueError("Origin and destination must be non-empty strings")

    dist_map = _get_distance_map()
    orig_norm = origin.strip().lower()
    dest_norm = destination.strip().lower()

    pair = (orig_norm, dest_norm)
    if pair not in dist_map:
        logger.error(f"Distance data unavailable for leg: '{origin}' -> '{destination}'")
        raise KeyError(f"Distance data unavailable for {origin.strip()} -> {destination.strip()}")

    # Return clean original or proper display names
    display_origin = _RAW_NAME_CACHE.get(orig_norm, origin.strip()) if _RAW_NAME_CACHE else origin.strip()
    display_destination = _RAW_NAME_CACHE.get(dest_norm, destination.strip()) if _RAW_NAME_CACHE else destination.strip()

    distance_val = dist_map[pair]
    # Return integer if whole number, else float
    distance_out = int(distance_val) if distance_val.is_integer() else round(distance_val, 2)

    return {
        "from": display_origin,
        "to": display_destination,
        "distance_km": distance_out
    }


def _parse_route_input(route: Union[str, List[str]]) -> List[str]:
    """Parse route input into a normalized list of stop names."""
    if isinstance(route, list):
        stops = [str(stop).strip() for stop in route if str(stop).strip()]
        return stops

    if not isinstance(route, str):
        return []

    # Replace common arrow representations (Unicode →, ASCII ->, -->, =>) with standard separator '|'
    cleaned = re.sub(r'\s*(?:->|→|-->|=>)\s*', '|', route.strip())
    stops = [stop.strip() for stop in cleaned.split('|') if stop.strip()]
    return stops


def calculate_route_distance(route: Union[str, List[str]]) -> dict:
    """Calculate leg distances and total distance for a route itinerary.
    
    Args:
        route: A route string (e.g. "Colombo -> Kandy -> Ella -> Colombo") 
               or a list of stop names ["Colombo", "Kandy", "Ella", "Colombo"].
               
    Returns:
        dict: Success object with route list, legs list, and total_distance_km,
              or error object {"success": False, "error": "..."}.
    """
    try:
        stops = _parse_route_input(route)

        if not stops:
            return {
                "success": False,
                "error": "Route is empty or invalid"
            }

        if len(stops) == 1:
            return {
                "success": True,
                "route": stops,
                "legs": [],
                "total_distance_km": 0
            }

        legs: List[dict] = []
        total_distance = 0.0

        for i in range(len(stops) - 1):
            orig = stops[i]
            dest = stops[i + 1]

            try:
                leg_info = calculate_leg_distance(orig, dest)
                legs.append(leg_info)
                total_distance += leg_info["distance_km"]
            except (KeyError, ValueError) as err:
                return {
                    "success": False,
                    "error": str(err)
                }
            except Exception as e:
                logger.exception(f"Unexpected error calculating leg {orig} -> {dest}")
                return {
                    "success": False,
                    "error": f"Error calculating distance for {orig} -> {dest}: {str(e)}"
                }

        total_out = int(total_distance) if total_distance.is_integer() else round(total_distance, 2)

        return {
            "success": True,
            "route": [leg["from"] for leg in legs] + [legs[-1]["to"]],
            "legs": legs,
            "total_distance_km": total_out
        }

    except FileNotFoundError as fnf_err:
        return {
            "success": False,
            "error": str(fnf_err)
        }
    except Exception as ex:
        logger.exception("Failed to calculate route distance")
        return {
            "success": False,
            "error": f"Distance calculation failed: {str(ex)}"
        }
