import time
import logging
from typing import Dict, List, Tuple, Union, Optional, Any

try:
    from .data_provider_config import SANITY_LIMITS, get_providers_for_component
    from .data_cache_manager import save_cached_data, load_cached_data, is_cache_fresh, get_cache_age
except ImportError:
    from data_provider_config import SANITY_LIMITS, get_providers_for_component
    from data_cache_manager import save_cached_data, load_cached_data, is_cache_fresh, get_cache_age

logger = logging.getLogger(__name__)


def normalize_external_data(component: str, raw_data: dict) -> dict:
    """Normalize raw provider data payload into standardized system structure."""
    if not isinstance(raw_data, dict):
        return {}

    comp = component.strip().lower()
    norm = dict(raw_data)
    norm["component"] = comp
    norm["fetched_at"] = raw_data.get("fetched_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    if comp == "fuel":
        try:
            p_val = float(raw_data.get("price_lkr_per_litre", raw_data.get("price_lkr", 0)))
        except (ValueError, TypeError):
            p_val = 0.0
        norm["fuel_type"] = str(raw_data.get("fuel_type", "petrol")).strip().lower()
        norm["price_lkr_per_litre"] = round(p_val, 2)
        norm["status"] = raw_data.get("status", "live")

    elif comp == "hotel":
        try:
            p_val = float(raw_data.get("price_lkr_per_night", raw_data.get("total_lkr", 0)))
        except (ValueError, TypeError):
            p_val = 0.0
        norm["place"] = str(raw_data.get("place", raw_data.get("destination", ""))).strip()
        norm["hotel_name"] = str(raw_data.get("hotel_name", "")).strip()
        norm["hotel_tier"] = str(raw_data.get("hotel_tier", raw_data.get("tier", "mid-range"))).strip().lower()
        norm["price_lkr_per_night"] = round(p_val, 2)
        norm["currency"] = str(raw_data.get("currency", "LKR")).strip().upper()
        norm["availability_status"] = str(raw_data.get("availability_status", "available")).strip().lower()

    elif comp == "transport":
        try:
            af_val = float(raw_data.get("adult_fare_lkr", raw_data.get("total_cost_lkr", 0)))
        except (ValueError, TypeError):
            af_val = 0.0
        try:
            cf_val = float(raw_data.get("child_fare_lkr", 0))
        except (ValueError, TypeError):
            cf_val = 0.0

        norm["origin"] = str(raw_data.get("origin", "")).strip()
        norm["destination"] = str(raw_data.get("destination", "")).strip()
        norm["transport_mode"] = str(raw_data.get("transport_mode", "train")).strip().lower()
        norm["fare_class"] = str(raw_data.get("fare_class", "2nd class")).strip().lower()
        norm["adult_fare_lkr"] = round(af_val, 2)
        norm["child_fare_lkr"] = round(cf_val, 2)

    elif comp == "attractions":
        try:
            ef_val = float(raw_data.get("entrance_fee_lkr", raw_data.get("total_lkr", 0)))
        except (ValueError, TypeError):
            ef_val = 0.0

        norm["attraction"] = str(raw_data.get("attraction", raw_data.get("name", ""))).strip()
        norm["entrance_fee_lkr"] = round(ef_val, 2)
        norm["opening_time"] = str(raw_data.get("opening_time", "08:00")).strip()
        norm["closing_time"] = str(raw_data.get("closing_time", "17:00")).strip()
        norm["attraction_status"] = str(raw_data.get("attraction_status", raw_data.get("status", "open"))).strip().lower()

    elif comp == "route":
        try:
            d_val = float(raw_data.get("distance_km", 0))
        except (ValueError, TypeError):
            d_val = 0.0
        try:
            dur_val = float(raw_data.get("duration_minutes", 0))
        except (ValueError, TypeError):
            dur_val = 0.0

        norm["origin"] = str(raw_data.get("origin", "")).strip()
        norm["destination"] = str(raw_data.get("destination", "")).strip()
        norm["distance_km"] = round(d_val, 2)
        norm["duration_minutes"] = round(dur_val, 2)

    return norm


def validate_external_data(component: str, normalized_data: dict) -> Tuple[bool, List[str]]:
    """Validate normalized provider data against sanity bounds and payload completeness rules."""
    warnings: List[str] = []
    if not isinstance(normalized_data, dict) or not normalized_data:
        return False, ["Payload is empty or invalid."]

    comp = component.strip().lower()
    limits = SANITY_LIMITS.get(comp, {})

    if comp == "fuel":
        price = normalized_data.get("price_lkr_per_litre", 0)
        min_p = limits.get("min_price_lkr", 100.0)
        max_p = limits.get("max_price_lkr", 1000.0)
        if price < min_p or price > max_p:
            warnings.append(f"Fuel price ({price} LKR) is outside sanity limits [{min_p}, {max_p}].")

    elif comp == "hotel":
        price = normalized_data.get("price_lkr_per_night", 0)
        min_p = limits.get("min_price_lkr", 500.0)
        max_p = limits.get("max_price_lkr", 500000.0)
        if price < min_p or price > max_p:
            warnings.append(f"Hotel night price ({price} LKR) is outside sanity limits [{min_p}, {max_p}].")
        if normalized_data.get("currency") and normalized_data["currency"] != "LKR":
            warnings.append(f"Unsupported currency '{normalized_data['currency']}'. Only LKR is supported.")

    elif comp == "transport":
        fare = normalized_data.get("adult_fare_lkr", 0)
        min_f = limits.get("min_fare_lkr", 10.0)
        max_f = limits.get("max_fare_lkr", 50000.0)
        if fare < min_f or fare > max_f:
            warnings.append(f"Transport fare ({fare} LKR) is outside sanity limits [{min_f}, {max_f}].")

    elif comp == "attractions":
        fee = normalized_data.get("entrance_fee_lkr", 0)
        min_f = limits.get("min_fee_lkr", 0.0)
        max_f = limits.get("max_fee_lkr", 50000.0)
        if fee < min_f or fee > max_f:
            warnings.append(f"Attraction entrance fee ({fee} LKR) is outside sanity limits [{min_f}, {max_f}].")

    elif comp == "route":
        dist = normalized_data.get("distance_km", 0)
        min_d = limits.get("min_distance_km", 1.0)
        max_d = limits.get("max_distance_km", 2000.0)
        if dist < min_d or dist > max_d:
            warnings.append(f"Route distance ({dist} km) is outside sanity limits [{min_d}, {max_d}].")

    is_valid = len(warnings) == 0
    return is_valid, warnings


def compare_external_with_benchmark(
    component: str,
    accepted_data: dict,
    benchmark_data: dict
) -> dict:
    """Compare accepted external data against baseline research benchmark dataset."""
    comp = component.strip().lower()
    acc_val = 0.0
    bench_val = 0.0

    if comp == "fuel":
        acc_val = accepted_data.get("price_lkr_per_litre", 0.0)
        bench_val = benchmark_data.get("price_lkr_per_litre", 370.0)
    elif comp == "hotel":
        acc_val = accepted_data.get("price_lkr_per_night", 0.0)
        bench_val = benchmark_data.get("price_lkr_per_night", 15000.0)
    elif comp == "transport":
        acc_val = accepted_data.get("adult_fare_lkr", 0.0)
        bench_val = benchmark_data.get("adult_fare_lkr", 500.0)
    elif comp == "attractions":
        acc_val = accepted_data.get("entrance_fee_lkr", 0.0)
        bench_val = benchmark_data.get("entrance_fee_lkr", 3000.0)
    elif comp == "route":
        acc_val = accepted_data.get("distance_km", 0.0)
        bench_val = benchmark_data.get("distance_km", 100.0)

    diff = round(acc_val - bench_val, 2)
    pct_diff = 0.0 if bench_val == 0 else round((diff / bench_val) * 100.0, 2)

    return {
        "component": comp,
        "accepted_value": acc_val,
        "benchmark_value": bench_val,
        "difference": diff,
        "percentage_difference": pct_diff
    }


def select_best_available_data(
    component: str,
    live_fetch_fn=None,
    benchmark_fn=None,
    params: Optional[dict] = None
) -> dict:
    """Select best available component data using deterministic priority rules:
    
    1. Valid fresh live data
    2. Valid cached external data
    3. Valid recent benchmark data
    4. Existing research benchmark fallback
    """
    comp = component.strip().lower()

    # 1. Attempt Live Fetch (if provider enabled & API key available)
    providers = get_providers_for_component(comp)
    live_provider = next((p for p in providers if p.get("source_type") in ("official", "verified") and p.get("api_key")), None)

    if live_provider and live_fetch_fn:
        try:
            raw_live = live_fetch_fn(params or {})
            norm_live = normalize_external_data(comp, raw_live)
            ok, warns = validate_external_data(comp, norm_live)

            if ok:
                norm_live["source"] = live_provider["provider_name"]
                norm_live["source_type"] = live_provider["source_type"]
                norm_live["status"] = "live"

                # Cache fresh live entry
                save_cached_data(comp, norm_live, source=live_provider["provider_name"], ttl_seconds=live_provider.get("refresh_interval_days", 7) * 86400)
                return norm_live
            else:
                logger.warning(f"Live provider '{live_provider['provider_name']}' returned invalid payload for '{comp}': {warns}")
        except Exception as ex:
            logger.warning(f"Failed to fetch live data for component '{comp}': {ex}")

    # 2. Attempt Fresh Cached External Data
    if is_cache_fresh(comp):
        cached_entry = load_cached_data(comp)
        if cached_entry and cached_entry.get("data"):
            norm_cache = normalize_external_data(comp, cached_entry["data"])
            ok, warns = validate_external_data(comp, norm_cache)

            if ok:
                norm_cache["status"] = "cached"
                norm_cache["source"] = cached_entry.get("source", "cached_provider")
                norm_cache["source_type"] = "verified"
                return norm_cache

    # 3. Fallback to Benchmark Dataset
    if benchmark_fn:
        try:
            raw_bench = benchmark_fn(params or {})
            norm_bench = normalize_external_data(comp, raw_bench)
            norm_bench["source"] = "Research Benchmark Estimate"
            norm_bench["source_type"] = "research_benchmark"
            norm_bench["status"] = "benchmark"
            return norm_bench
        except Exception as ex:
            logger.warning(f"Benchmark fetch failed for component '{comp}': {ex}")

    # Default Fallback Structure
    return {
        "component": comp,
        "status": "benchmark",
        "source": "Research Benchmark Estimate",
        "source_type": "research_benchmark"
    }


def fetch_fuel_prices(params: Optional[dict] = None) -> dict:
    """Fetch normalized fuel pricing data with safe benchmark fallback."""
    def benchmark_fuel(p):
        return {"price_lkr_per_litre": 370.0, "fuel_type": (p or {}).get("fuel_type", "petrol")}

    def live_fuel(p):
        # Simulated live provider call check
        key = (p or {}).get("api_key")
        if not key:
            raise ValueError("No API key available for live fuel provider.")
        return {"price_lkr_per_litre": 370.0, "fuel_type": "petrol"}

    return select_best_available_data("fuel", live_fetch_fn=live_fuel, benchmark_fn=benchmark_fuel, params=params)


def fetch_hotel_prices(place: str, tier: Optional[str] = "mid-range") -> dict:
    """Fetch normalized hotel pricing data with safe benchmark fallback."""
    t_clean = str(tier).strip().lower() if tier else "mid-range"
    def benchmark_hotel(p):
        prices = {"budget": 10000.0, "mid-range": 25000.0, "premium": 50000.0}
        return {
            "place": place,
            "hotel_name": f"{place} Benchmark Resort",
            "hotel_tier": t_clean,
            "price_lkr_per_night": prices.get(t_clean, 25000.0)
        }

    return select_best_available_data("hotel", benchmark_fn=benchmark_hotel, params={"place": place, "tier": t_clean})


def fetch_public_transport_fares(origin: str, destination: str, mode: str = "train") -> dict:
    """Fetch normalized transit fare data with safe benchmark fallback."""
    def benchmark_transit(p):
        return {
            "origin": origin,
            "destination": destination,
            "transport_mode": mode,
            "adult_fare_lkr": 500.0,
            "child_fare_lkr": 250.0
        }

    return select_best_available_data("transport", benchmark_fn=benchmark_transit, params={"origin": origin, "destination": destination, "mode": mode})


def fetch_attraction_information(attraction_name: str) -> dict:
    """Fetch normalized attraction data with safe benchmark fallback."""
    def benchmark_attr(p):
        return {
            "attraction": attraction_name,
            "entrance_fee_lkr": 3000.0,
            "opening_time": "08:00",
            "closing_time": "17:00",
            "attraction_status": "open"
        }

    return select_best_available_data("attractions", benchmark_fn=benchmark_attr, params={"attraction": attraction_name})


def fetch_route_information(origin: str, destination: str) -> dict:
    """Fetch normalized route leg data with safe benchmark fallback."""
    def benchmark_route(p):
        return {
            "origin": origin,
            "destination": destination,
            "distance_km": 115.0,
            "duration_minutes": 150.0
        }

    return select_best_available_data("route", benchmark_fn=benchmark_route, params={"origin": origin, "destination": destination})


def build_real_time_data_summary(component_statuses: Dict[str, dict]) -> dict:
    """Build standardized prediction.real_time_data API response payload dictionary."""
    live_comps = [c for c, s in component_statuses.items() if s.get("status") == "live"]
    cached_comps = [c for c, s in component_statuses.items() if s.get("status") == "cached"]
    bench_comps = [c for c, s in component_statuses.items() if s.get("status") in ("benchmark", "fallback")]
    failed_comps = [c for c, s in component_statuses.items() if s.get("status") == "failed"]

    total = len(component_statuses)
    live_pct = (len(live_comps) / total * 100.0) if total > 0 else 0.0

    if live_pct == 100.0:
        overall_status = "fully_live"
    elif live_pct >= 60.0:
        overall_status = "mostly_live"
    elif live_pct > 0.0 or len(cached_comps) > 0:
        overall_status = "partially_live"
    elif len(bench_comps) > 0:
        overall_status = "benchmark_fallback"
    else:
        overall_status = "data_unavailable"

    warnings = []
    if bench_comps:
        warnings.append(f"Components {', '.join(bench_comps)} are operating on research benchmark data fallbacks.")

    if failed_comps:
        warnings.append(f"External data refresh failed for components {', '.join(failed_comps)}.")

    now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return {
        "status": overall_status,
        "components_evaluated": total,
        "live_components": live_comps,
        "cached_components": cached_comps,
        "benchmark_components": bench_comps,
        "failed_components": failed_comps,
        "last_refresh": now_iso,
        "sources": {c: {"source": s.get("source", "Research Benchmark"), "source_type": s.get("source_type", "research_benchmark"), "status": s.get("status", "benchmark")} for c, s in component_statuses.items()},
        "warnings": warnings
    }
