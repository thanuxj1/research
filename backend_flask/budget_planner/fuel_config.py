"""
Fuel Configuration Module for Sri Lanka Tourism Intelligent Budget Planner.

Provides documented benchmark assumptions for vehicle fuel efficiencies (km/L) 
and corresponding fuel types used when direct user-specified efficiency is not provided.
"""

from typing import Dict, Tuple

# Benchmark vehicle fuel efficiencies (km per liter) in Sri Lankan driving conditions.
# Note: These values serve as baseline estimates unless overridden by user input.
VEHICLE_EFFICIENCY: Dict[str, float] = {
    "private car": 15.0,
    "car": 15.0,
    "motorcycle": 35.0,
    "bike": 35.0,
    "van": 10.0,
    "suv": 10.0,
    "tuktuk": 25.0,
    "three wheeler": 25.0,
}

# Fuel type mapping per transport mode
VEHICLE_FUEL_TYPE: Dict[str, str] = {
    "private car": "petrol_92",
    "car": "petrol_92",
    "motorcycle": "petrol_92",
    "bike": "petrol_92",
    "van": "diesel",
    "suv": "petrol_92",
    "tuktuk": "petrol_92",
    "three wheeler": "petrol_92",
}

# Transport modes classified as public transit where fuel is not directly calculated
PUBLIC_TRANSPORT_MODES = {"bus", "train", "public transport", "public"}


def is_public_transport(transport_mode: str) -> bool:
    """Check if the given transport mode is public transit."""
    if not transport_mode:
        return False
    return transport_mode.strip().lower() in PUBLIC_TRANSPORT_MODES


def get_vehicle_defaults(transport_mode: str) -> Tuple[float, str]:
    """Retrieve default efficiency (km/L) and fuel type for a transport mode.
    
    Raises KeyError if the transport mode is unknown and not public transit.
    """
    if not transport_mode:
        raise ValueError("Transport mode must be a non-empty string")

    mode_norm = transport_mode.strip().lower()

    if mode_norm in VEHICLE_EFFICIENCY:
        return VEHICLE_EFFICIENCY[mode_norm], VEHICLE_FUEL_TYPE[mode_norm]

    raise KeyError(f"Unknown transport mode: '{transport_mode}'")
