import csv
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Union, Optional

try:
    from .route_calculator import _parse_route_input as parse_route, calculate_leg_distance
    from .fuel_calculator import calculate_route_fuel_cost
    from .hotel_calculator import calculate_route_hotel_cost
    from .food_calculator import calculate_route_food_cost
    from .attraction_calculator import calculate_route_attraction_cost
    from .public_transport_calculator import calculate_public_transport_route_cost
    from .unified_cost_calculator import build_cost_summary
except ImportError:
    from route_calculator import _parse_route_input as parse_route, calculate_leg_distance
    from fuel_calculator import calculate_route_fuel_cost
    from hotel_calculator import calculate_route_hotel_cost
    from food_calculator import calculate_route_food_cost
    from attraction_calculator import calculate_route_attraction_cost
    from public_transport_calculator import calculate_public_transport_route_cost
    from unified_cost_calculator import build_cost_summary

logger = logging.getLogger(__name__)

DEFAULT_SCHEDULE_CSV = Path(__file__).resolve().parent / "attraction_schedule.csv"

_SCHEDULE_CACHE: Optional[Dict[Tuple[str, str], dict]] = None

TIME_PERIOD_RANGES = {
    "early_morning": ("05:00", "08:00"),
    "morning": ("08:00", "12:00"),
    "midday": ("12:00", "14:00"),
    "afternoon": ("14:00", "17:00"),
    "evening": ("17:00", "20:00")
}

ROAD_SPEEDS_KMH = {
    "urban": 30.0,
    "normal": 45.0,
    "highway": 70.0,
    "mountain": 30.0
}


def _format_num(val: Union[int, float]) -> Union[int, float]:
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val.is_integer():
        return int(val)
    return round(val, 2)


def load_attraction_schedule_data(csv_path: Optional[Union[str, Path]] = None) -> Dict[Tuple[str, str], dict]:
    """Load tourist attraction schedule dataset into memory cache.
    
    Returns:
        dict: (destination_lower, attraction_lower) -> schedule details dict.
    """
    global _SCHEDULE_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_SCHEDULE_CSV

    if not target_path.exists():
        logger.error(f"Attraction schedule dataset missing at path: {target_path}")
        raise FileNotFoundError(f"Attraction schedule dataset missing: {target_path}")

    schedule_map: Dict[Tuple[str, str], dict] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            dest_raw = row.get("destination", "").strip()
            attr_raw = row.get("attraction_name", "").strip()

            if not dest_raw or not attr_raw or dest_raw.startswith("#"):
                continue

            try:
                rec_dur = float(row.get("recommended_visit_duration_hours", 1.5))
                min_dur = float(row.get("minimum_visit_duration_hours", 1.0))
                max_dur = float(row.get("maximum_visit_duration_hours", 2.5))
            except ValueError:
                rec_dur, min_dur, max_dur = 1.5, 1.0, 2.5

            entry = {
                "destination": dest_raw,
                "attraction_name": attr_raw,
                "category": row.get("category", "general").strip().lower(),
                "opening_time": row.get("opening_time", "08:00").strip(),
                "closing_time": row.get("closing_time", "18:00").strip(),
                "recommended_visit_duration_hours": rec_dur,
                "minimum_visit_duration_hours": min_dur,
                "maximum_visit_duration_hours": max_dur,
                "preferred_period": row.get("preferred_period", "morning").strip().lower(),
                "best_day_type": row.get("best_day_type", "all_days").strip(),
                "data_source": row.get("data_source", "Research Benchmark Estimate").strip()
            }

            key = (dest_raw.lower(), attr_raw.lower())
            schedule_map[key] = entry

    _SCHEDULE_CACHE = schedule_map
    return schedule_map


def _get_schedule_map() -> Dict[Tuple[str, str], dict]:
    global _SCHEDULE_CACHE
    if _SCHEDULE_CACHE is None:
        load_attraction_schedule_data()
    return _SCHEDULE_CACHE  # type: ignore


def get_attraction_schedule(destination: str, attraction_name: str) -> dict:
    """Look up operating hours and visit guidelines for an attraction."""
    s_map = _get_schedule_map()
    key = (destination.strip().lower(), attraction_name.strip().lower())
    if key in s_map:
        return s_map[key]

    # Partial match fallback
    for (d, a), item in s_map.items():
        if d == destination.strip().lower() and (a in attraction_name.lower() or attraction_name.lower() in a):
            return item

    return {
        "destination": destination,
        "attraction_name": attraction_name,
        "category": "general",
        "opening_time": "08:00",
        "closing_time": "18:00",
        "recommended_visit_duration_hours": 1.5,
        "preferred_period": "morning",
        "data_source": "Research Benchmark Estimate"
    }


def estimate_travel_time(distance_km: float, road_type: str = "normal") -> float:
    """Estimate travel duration in hours based on distance and road speeds."""
    speed = ROAD_SPEEDS_KMH.get(road_type.lower(), 45.0)
    if distance_km <= 0:
        return 0.0
    return round(distance_km / speed, 2)


def parse_time_to_minutes(time_str: str) -> int:
    """Convert 'HH:MM' string to minutes from midnight."""
    parts = time_str.split(":")
    return int(parts[0]) * 60 + int(parts[1])


def format_minutes_to_time(minutes: int) -> str:
    """Convert minutes from midnight to 'HH:MM' string."""
    m = minutes % (24 * 60)
    hrs = m // 60
    mins = m % 60
    return f"{hrs:02d}:{mins:02d}"


def optimize_daily_sequence(
    day_number: int,
    start_dest: str,
    end_dest: str,
    attractions: List[dict],
    travel_mode: str = "private car",
    travel_type: str = "couple"
) -> dict:
    """Build optimized daily sequence of travel, attraction visits, and rest buffers."""
    activities: List[dict] = []
    warnings: List[str] = []

    curr_min = parse_time_to_minutes("08:00")

    # 1. Travel to destination if changing cities
    daily_dist = 0.0
    if start_dest.lower() != end_dest.lower():
        try:
            leg_info = calculate_leg_distance(start_dest, end_dest)
            leg_dist = leg_info.get("distance_km", 100)
        except Exception:
            leg_dist = 100.0

        daily_dist += leg_dist
        road_type = "mountain" if "Nuwara Eliya" in (start_dest, end_dest) or "Ella" in (start_dest, end_dest) else "normal"
        t_hours = estimate_travel_time(leg_dist, road_type)
        t_mins = int(t_hours * 60)

        t_start = format_minutes_to_time(curr_min)
        curr_min += t_mins
        t_end = format_minutes_to_time(curr_min)

        activities.append({
            "time": f"{t_start}-{t_end}",
            "activity": f"Travel {start_dest} -> {end_dest}",
            "type": "travel",
            "duration_hours": t_hours,
            "distance_km": leg_dist
        })
        curr_min += 30  # Buffer after long distance travel

    # 2. Schedule attractions
    for attr in attractions:
        name = attr.get("attraction_name", "Attraction")
        sched = get_attraction_schedule(end_dest, name)

        dur_hrs = attr.get("duration_hours", sched.get("recommended_visit_duration_hours", 1.5))
        dur_mins = int(dur_hrs * 60)

        open_min = parse_time_to_minutes(sched.get("opening_time", "08:00"))
        close_min = parse_time_to_minutes(sched.get("closing_time", "18:00"))

        if curr_min < open_min:
            curr_min = open_min

        arr_time = format_minutes_to_time(curr_min)
        dept_min = curr_min + dur_mins
        dept_time = format_minutes_to_time(dept_min)

        # Check operating hours compliance
        if curr_min < open_min:
            warnings.append(f"Arrived at {name} ({arr_time}) before opening time ({sched['opening_time']}).")
        if dept_min > close_min:
            warnings.append(f"Visit to {name} ends at {dept_time}, which is after closing time ({sched['closing_time']}).")

        activities.append({
            "time": f"{arr_time}-{dept_time}",
            "activity": name,
            "type": "attraction",
            "category": sched.get("category", "general"),
            "duration_hours": dur_hrs
        })

        curr_min = dept_min + 30  # Rest buffer

    return {
        "day": day_number,
        "start_destination": start_dest,
        "destination": end_dest,
        "overnight_destination": end_dest,
        "activities": activities,
        "daily_distance_km": _format_num(daily_dist),
        "warnings": warnings
    }


def validate_daily_schedule(activities: List[dict]) -> List[str]:
    """Detect schedule conflicts and warnings."""
    warnings: List[str] = []
    total_travel_hours = sum(a.get("duration_hours", 0) for a in activities if a.get("type") == "travel")
    total_attr_hours = sum(a.get("duration_hours", 0) for a in activities if a.get("type") == "attraction")

    if total_travel_hours + total_attr_hours > 10.0:
        warnings.append("Daily active travel and activity time exceeds recommended maximum of 10 hours.")

    attr_count = sum(1 for a in activities if a.get("type") == "attraction")
    if attr_count > 4:
        warnings.append(f"Day contains {attr_count} attractions, which may cause travel fatigue.")

    return warnings


def calculate_schedule_score(itinerary_days: List[dict], user_budget: float, interest: str) -> float:
    """Calculate deterministic feasibility score for the daily travel schedule.
    
    Formula:
        score = base_score(100) - warning_penalties - travel_penalties
    """
    score = 100.0
    total_warnings = sum(len(d.get("warnings", [])) for d in itinerary_days)
    score -= (total_warnings * 10.0)

    total_dist = sum(d.get("daily_distance_km", 0) for d in itinerary_days)
    score -= round(total_dist / 20.0, 2)

    return _format_num(max(0.0, min(100.0, score)))


def optimize_travel_schedule(
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
    """Context-Aware Travel Schedule & Daily Itinerary Optimization Engine.
    
    Converts an optimized route into a practical day-by-day travel schedule payload.
    """
    if days is None or days <= 0:
        raise ValueError("Days must be a positive integer greater than zero")

    if travelers is None or travelers <= 0:
        raise ValueError("Travelers must be a positive integer greater than zero")

    stops = parse_route(route)
    if not stops or len(stops) < 2:
        stops = ["Colombo", "Kandy", "Colombo"]

    # Compute attraction recommendations for the route
    a_res = calculate_route_attraction_cost(route, days, travelers, adult_travelers, child_travelers, interest, user_budget)
    sel_attractions = a_res.get("selected_attractions", [])

    # Group attractions by destination
    attr_by_dest: Dict[str, List[dict]] = {}
    for item in sel_attractions:
        dest = item.get("destination", stops[0])
        attr_by_dest.setdefault(dest, []).append(item)

    # Distribute destinations across days
    inter_stops = [s for s in stops[1:-1] if s != "Colombo"]
    if not inter_stops:
        inter_stops = ["Kandy"]

    itinerary_days: List[dict] = []
    total_distance_km = 0.0
    total_activity_hours = 0.0
    total_travel_hours = 0.0

    curr_start = stops[0]

    for d in range(1, days + 1):
        if d <= len(inter_stops):
            curr_dest = inter_stops[d - 1]
        else:
            curr_dest = inter_stops[-1] if inter_stops else stops[0]

        if d == days:
            curr_dest = stops[-1]

        day_attrs = attr_by_dest.get(curr_dest, [])

        day_seq = optimize_daily_sequence(
            day_number=d,
            start_dest=curr_start,
            end_dest=curr_dest,
            attractions=day_attrs,
            travel_mode=transport_mode,
            travel_type=travel_type
        )

        daily_warnings = validate_daily_schedule(day_seq["activities"])
        day_seq["warnings"].extend(daily_warnings)

        daily_dist = day_seq["daily_distance_km"]
        total_distance_km += daily_dist

        for act in day_seq["activities"]:
            if act["type"] == "travel":
                total_travel_hours += act["duration_hours"]
            elif act["type"] == "attraction":
                total_activity_hours += act["duration_hours"]

        itinerary_days.append(day_seq)
        curr_start = curr_dest

    score = calculate_schedule_score(itinerary_days, user_budget, interest)

    feasibility = "feasible" if score >= 70.0 else "partially_feasible"

    return {
        "optimized_route": str(route),
        "total_days": days,
        "schedule_score": score,
        "daily_itinerary": itinerary_days,
        "schedule_summary": {
            "total_distance_km": _format_num(total_distance_km),
            "total_activity_hours": _format_num(total_activity_hours),
            "total_travel_hours": _format_num(total_travel_hours),
            "feasibility": feasibility,
            "data_source": "Research Benchmark Estimate"
        }
    }
