import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# In-Memory Cache Store for Data Freshness & Provider Fallbacks
_CACHE_STORE: Dict[str, dict] = {}


def save_cached_data(
    component: str,
    data: Any,
    source: str = "external_provider",
    ttl_seconds: int = 86400
) -> dict:
    """Save component data payload into cache store with TTL expiration."""
    comp_clean = component.strip().lower()
    now_ts = time.time()
    expires_at = now_ts + ttl_seconds

    entry = {
        "component": comp_clean,
        "data": data,
        "source": source,
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts)),
        "fetched_timestamp": now_ts,
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires_at)),
        "expires_timestamp": expires_at,
        "ttl_seconds": ttl_seconds,
        "status": "cached"
    }

    _CACHE_STORE[comp_clean] = entry
    logger.debug(f"Cached data for component '{comp_clean}' from source '{source}' with TTL {ttl_seconds}s.")
    return entry


def load_cached_data(component: str) -> Optional[dict]:
    """Retrieve cached entry for component if available."""
    comp_clean = component.strip().lower()
    return _CACHE_STORE.get(comp_clean)


def is_cache_fresh(component: str) -> bool:
    """Check whether cached entry for component exists and is not expired."""
    entry = load_cached_data(component)
    if not entry:
        return False
    now_ts = time.time()
    return now_ts <= entry.get("expires_timestamp", 0)


def get_cache_age(component: str) -> Optional[float]:
    """Get age of cached entry in seconds."""
    entry = load_cached_data(component)
    if not entry:
        return None
    now_ts = time.time()
    return max(0.0, round(now_ts - entry.get("fetched_timestamp", now_ts), 2))


def invalidate_cache(component: Optional[str] = None) -> None:
    """Invalidate cache entry for a specific component or clear all entries."""
    global _CACHE_STORE
    if component:
        comp_clean = component.strip().lower()
        _CACHE_STORE.pop(comp_clean, None)
    else:
        _CACHE_STORE.clear()
