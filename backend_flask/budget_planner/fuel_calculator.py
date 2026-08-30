import csv
import logging
from pathlib import Path
from typing import Dict, Optional, Union

try:
    from .fuel_config import is_public_transport, get_vehicle_defaults
except ImportError:
    from fuel_config import is_public_transport, get_vehicle_defaults

logger = logging.getLogger(__name__)

DEFAULT_FUEL_PRICES_CSV = Path(__file__).resolve().parent / "fuel_prices.csv"

_FUEL_PRICES_CACHE: Optional[Dict[str, float]] = None


def load_fuel_prices(csv_path: Optional[Union[str, Path]] = None) -> Dict[str, float]:
    """Load Sri Lankan fuel price dataset from CSV into memory.
    
    Returns:
        dict: Mapping of fuel_type (lowercased) -> price_lkr_per_liter (float).
    """
    global _FUEL_PRICES_CACHE

    target_path = Path(csv_path) if csv_path else DEFAULT_FUEL_PRICES_CSV

    if not target_path.exists():
        logger.error(f"Fuel prices dataset not found at: {target_path}")
        raise FileNotFoundError(f"Fuel prices dataset missing: {target_path}")

    price_map: Dict[str, float] = {}

    with open(target_path, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):
            fuel_type = row.get("fuel_type", "").strip().lower()
            price_str = row.get("price_lkr_per_liter", "").strip()

            if not fuel_type or not price_str:
                continue

            try:
                price_val = float(price_str)
                if price_val < 0:
                    logger.warning(f"Negative fuel price at row {line_num}: {price_val}")
                    continue
                price_map[fuel_type] = price_val
            except ValueError:
                logger.warning(f"Invalid fuel price format at row {line_num}: '{price_str}'")
                continue

    _FUEL_PRICES_CACHE = price_map
    return price_map


def _get_fuel_prices_map() -> Dict[str, float]:
    global _FUEL_PRICES_CACHE
    if _FUEL_PRICES_CACHE is None:
        load_fuel_prices()
    return _FUEL_PRICES_CACHE  # type: ignore


def calculate_fuel_consumption(distance_km: float, vehicle_efficiency_km_per_liter: float) -> float:
    """Calculate required fuel consumption in liters.
    
    Formula:
        fuel_required_liters = distance_km / vehicle_efficiency_km_per_liter
    """
    if distance_km < 0:
        raise ValueError("Distance cannot be negative")

    if vehicle_efficiency_km_per_liter <= 0:
        raise ValueError("Vehicle efficiency must be a positive number greater than zero")

    return distance_km / vehicle_efficiency_km_per_liter


def calculate_fuel_cost(fuel_required_liters: float, fuel_price_lkr_per_liter: float) -> float:
    """Calculate total fuel cost in LKR.
    
    Formula:
        fuel_cost_lkr = fuel_required_liters * fuel_price_lkr_per_liter
    """
    if fuel_required_liters < 0:
        raise ValueError("Fuel required cannot be negative")

    if fuel_price_lkr_per_liter < 0:
        raise ValueError("Fuel price cannot be negative")

    return fuel_required_liters * fuel_price_lkr_per_liter


def calculate_route_fuel_cost(
    total_distance_km: float,
    transport_mode: str,
    custom_efficiency: Optional[float] = None
) -> dict:
    """Calculate fuel consumption and estimated fuel cost for a given route distance.
    
    Args:
        total_distance_km: Total trip distance in kilometers.
        transport_mode: Transport mode (e.g. "private car", "motorcycle", "van", "bus", "train").
        custom_efficiency: Optional user-provided vehicle efficiency (km/L).
        
    Returns:
        dict: Calculation result dictionary or error object.
    """
    try:
        if not transport_mode or not isinstance(transport_mode, str):
            return {
                "success": False,
                "error": "Transport mode must be a non-empty string"
            }

        # Check for public transport
        if is_public_transport(transport_mode):
            return {
                "success": True,
                "fuel_applicable": False,
                "transport_mode": transport_mode,
                "reason": "Fuel cost is not directly calculated for public transport."
            }

        if total_distance_km <= 0:
            return {
                "success": False,
                "error": "Total distance must be a positive number greater than zero"
            }

        # Handle custom vs default vehicle efficiency
        if custom_efficiency is not None:
            try:
                efficiency = float(custom_efficiency)
                if efficiency <= 0:
                    return {
                        "success": False,
                        "error": "Vehicle efficiency must be a positive number greater than zero"
                    }
            except (ValueError, TypeError):
                return {
                    "success": False,
                    "error": f"Invalid vehicle efficiency value: {custom_efficiency}"
                }
            
            # Lookup default fuel type for transport mode
            try:
                _, fuel_type = get_vehicle_defaults(transport_mode)
            except KeyError:
                fuel_type = "petrol_92"  # fallback default fuel type if custom mode specified
        else:
            try:
                efficiency, fuel_type = get_vehicle_defaults(transport_mode)
            except KeyError as ke:
                return {
                    "success": False,
                    "error": str(ke).strip("'")
                }

        # Retrieve fuel price
        fuel_prices = _get_fuel_prices_map()
        if fuel_type not in fuel_prices:
            return {
                "success": False,
                "error": f"Fuel price data missing for fuel type: '{fuel_type}'"
            }

        fuel_price = fuel_prices[fuel_type]

        liters_required = calculate_fuel_consumption(total_distance_km, efficiency)
        estimated_cost = calculate_fuel_cost(liters_required, fuel_price)

        liters_out = int(liters_required) if liters_required.is_integer() else round(liters_required, 2)
        cost_out = int(estimated_cost) if estimated_cost.is_integer() else round(estimated_cost, 2)

        return {
            "success": True,
            "fuel_applicable": True,
            "transport_mode": transport_mode,
            "total_distance_km": total_distance_km,
            "vehicle_efficiency_km_per_liter": efficiency,
            "fuel_required_liters": liters_out,
            "fuel_type": fuel_type,
            "fuel_price_lkr_per_liter": fuel_price,
            "estimated_fuel_cost_lkr": cost_out
        }

    except FileNotFoundError as fnf_err:
        return {
            "success": False,
            "error": str(fnf_err)
        }
    except Exception as ex:
        logger.exception("Failed to calculate route fuel cost")
        return {
            "success": False,
            "error": f"Fuel calculation failed: {str(ex)}"
        }
