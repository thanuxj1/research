import os
from typing import Dict, Any

# Configurable Sanity Bounds for External Data Validation
SANITY_LIMITS = {
    "fuel": {
        "min_price_lkr": 100.0,
        "max_price_lkr": 1000.0
    },
    "hotel": {
        "min_price_lkr": 500.0,
        "max_price_lkr": 500000.0
    },
    "transport": {
        "min_fare_lkr": 10.0,
        "max_fare_lkr": 50000.0
    },
    "attractions": {
        "min_fee_lkr": 0.0,
        "max_fee_lkr": 50000.0
    },
    "route": {
        "min_distance_km": 1.0,
        "max_distance_km": 2000.0
    }
}

# Configurable Provider Definitions (No hardcoded secrets!)
DATA_PROVIDERS: Dict[str, Any] = {
    "fuel": [
        {
            "provider_name": "Official Energy Regulatory API",
            "source_type": "official",
            "priority": 1,
            "enabled": True,
            "timeout_seconds": 5,
            "refresh_interval_days": 7,
            "reliability_score": 100.0,
            "api_key": os.environ.get("FUEL_API_KEY")
        },
        {
            "provider_name": "Research Benchmark Fuel Dataset",
            "source_type": "research_benchmark",
            "priority": 2,
            "enabled": True,
            "timeout_seconds": 1,
            "refresh_interval_days": 14,
            "reliability_score": 75.0,
            "api_key": None
        }
    ],
    "hotel": [
        {
            "provider_name": "Verified Sri Lanka Hotel Booking API",
            "source_type": "verified",
            "priority": 1,
            "enabled": True,
            "timeout_seconds": 5,
            "refresh_interval_days": 7,
            "reliability_score": 90.0,
            "api_key": os.environ.get("HOTEL_API_KEY")
        },
        {
            "provider_name": "Research Benchmark Hotel Dataset",
            "source_type": "research_benchmark",
            "priority": 2,
            "enabled": True,
            "timeout_seconds": 1,
            "refresh_interval_days": 30,
            "reliability_score": 75.0,
            "api_key": None
        }
    ],
    "transport": [
        {
            "provider_name": "Sri Lanka Railway & Transport Board API",
            "source_type": "official",
            "priority": 1,
            "enabled": True,
            "timeout_seconds": 5,
            "refresh_interval_days": 14,
            "reliability_score": 95.0,
            "api_key": os.environ.get("TRANSPORT_API_KEY")
        },
        {
            "provider_name": "Research Benchmark Fare Dataset",
            "source_type": "research_benchmark",
            "priority": 2,
            "enabled": True,
            "timeout_seconds": 1,
            "refresh_interval_days": 30,
            "reliability_score": 75.0,
            "api_key": None
        }
    ],
    "attractions": [
        {
            "provider_name": "Sri Lanka Tourism Development Authority API",
            "source_type": "official",
            "priority": 1,
            "enabled": True,
            "timeout_seconds": 5,
            "refresh_interval_days": 30,
            "reliability_score": 95.0,
            "api_key": os.environ.get("ATTRACTION_API_KEY")
        },
        {
            "provider_name": "Research Benchmark Attraction Dataset",
            "source_type": "research_benchmark",
            "priority": 2,
            "enabled": True,
            "timeout_seconds": 1,
            "refresh_interval_days": 90,
            "reliability_score": 75.0,
            "api_key": None
        }
    ],
    "route": [
        {
            "provider_name": "Geographic Distance Matrix API",
            "source_type": "verified",
            "priority": 1,
            "enabled": True,
            "timeout_seconds": 5,
            "refresh_interval_days": 30,
            "reliability_score": 90.0,
            "api_key": os.environ.get("ROUTE_API_KEY")
        },
        {
            "provider_name": "Research Benchmark Distance Dataset",
            "source_type": "research_benchmark",
            "priority": 2,
            "enabled": True,
            "timeout_seconds": 1,
            "refresh_interval_days": 30,
            "reliability_score": 75.0,
            "api_key": None
        }
    ]
}


def get_providers_for_component(component: str) -> list:
    """Return sorted list of enabled providers for a component ordered by priority."""
    comp_clean = component.strip().lower()
    providers = DATA_PROVIDERS.get(comp_clean, [])
    enabled_provs = [p for p in providers if p.get("enabled", True)]
    return sorted(enabled_provs, key=lambda x: x.get("priority", 99))
