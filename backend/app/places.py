"""Nearby-venue lookup against live POI providers.

Stdlib only - `urllib.request`, not `requests`. The project deliberately keeps
its pure-Python layers dependency-free so the tests run without the ML stack,
and adding an HTTP library for two GET-shaped calls would break that for nothing.

Providers, selected by `FOODAI_PLACES_PROVIDER`:

* **overpass** (default) - OpenStreetMap via the Overpass API. No key, no
  billing, good Sri Lankan coverage for restaurants and bakeries. Rate-limited
  and occasionally slow, which is why results are cached and failures degrade.
* **google** - Google Places API (New) `places:searchNearby`. Richer: ratings,
  open-now, price level. Needs a key and is billed per call. The key is read
  server-side; putting it in a `VITE_*` variable would inline it into the
  published browser bundle.
* **static** - the bundled seed list only. Useful offline and in tests.
* **none** - disabled; the endpoint reports unavailable instead of guessing.

Three things this module is careful about.

**Honest confidence.** No POI provider knows a venue's menu. A returned venue is
labelled `named` (its name mentions the dish), `cuisine` (its cuisine tag
matches) or `category` (only its venue class fits). `category` is a guess and the
UI says so. Presenting all three with equal authority would be the real bug -
this is the same reasoning behind the health engine's negative keywords.

The halal flag is the same problem in a sharper form, which is why it is
tri-state: True and False are claims somebody made and None means nobody has
looked. It has exactly two sources, each with its own wording. A provider survey
- OpenStreetMap's `diet:halal` tag, see `parse_halal` - is the stronger one and
wins in both directions. Where no provider has surveyed a venue, the operator's
hand-compiled list in `data/halal_venues.py` can fill the gap, captioned as a
hand-written listing rather than a certification; see `apply_curated_halal` for
the precedence and why a disagreement is left as the provider found it. Google
Places has no halal field at all, so a Google-backed deployment shows only the
curated rows.

**Coordinate minimisation.** Incoming coordinates are rounded to
`coordinate_precision` decimals - 3 dp is about 110 m - before they are used as a
cache key or sent upstream. That is precise enough to find a restaurant and not
precise enough to identify a doorstep. Coordinates are never logged.

**Degradation, not failure.** A timeout or an upstream 429 falls back to the seed
list with `source: "seed"` set, and `GET /health` reports the provider's last
error. The project's stated position is that a visible downgrade beats a silent
one.
"""

from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass, replace
from typing import Sequence
from urllib.parse import quote_plus

from .data.halal_venues import (
    CURATED_LABEL,
    CURATED_NOTE,
    curated_halal_name,
)
from .data.venue_profiles import (
    BAKERY,
    CAFE,
    DEFAULT_SELECTORS,
    VenueProfile,
    profile_for,
)
from .data.venues_seed import SEED_VENUES, SRI_LANKA_CITIES

log = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0088

# Confidence levels, strongest first. Also the sort priority.
CONFIDENCE_NAMED = "named"
CONFIDENCE_CUISINE = "cuisine"
CONFIDENCE_CATEGORY = "category"
CONFIDENCE_ORDER = {CONFIDENCE_NAMED: 0, CONFIDENCE_CUISINE: 1, CONFIDENCE_CATEGORY: 2}

CONFIDENCE_REASONS = {
    CONFIDENCE_NAMED: "this place is known for the dish",
    CONFIDENCE_CUISINE: "serves this style of food",
    CONFIDENCE_CATEGORY: "this kind of place usually sells it",
}

# Per-evidence wording. The legend above groups venues; these say what actually
# matched, because "known for the dish" is a claim that should be attributable.
REASON_NAME_MATCH = "the name mentions this dish"
REASON_NOTE_MATCH = "listed as serving this dish"
REASON_CUISINE_MATCH = "serves this style of food"
REASON_CATEGORY_MATCH = "this kind of place usually sells it"
# `nearby()` has no dish to match against, so it cannot borrow any of the four
# above without implying an evidence check it never performed.
REASON_NO_DISH = "a nearby food venue; no dish was specified"

# Guards the values interpolated into Overpass QL. They come from our own
# constants, but validating means a future edit cannot introduce an injection.
_SAFE_TAG = re.compile(r"^[a-z_]+$")


class PlacesUnavailable(RuntimeError):
    """The live provider could not be reached or returned nothing usable."""


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    # Clamped before asin: floating-point error can push `a` a hair above 1.0 for
    # antipodal points, and math.asin would raise instead of returning half the
    # circumference.
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def coarsen(value: float, precision: int) -> float:
    """Round a coordinate down to `precision` decimals.

    Applied before the coordinate is cached or sent upstream. At 3 dp the
    resolution is roughly 110 m, so two users on the same street produce the same
    cache key and one upstream request instead of two.
    """
    return round(float(value), max(0, precision))


def validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    if not (-90.0 <= latitude <= 90.0):
        raise ValueError("latitude must be between -90 and 90")
    if not (-180.0 <= longitude <= 180.0):
        raise ValueError("longitude must be between -180 and 180")
    return float(latitude), float(longitude)


def nearest_city(latitude: float, longitude: float) -> tuple[str, float] | None:
    """Closest entry in `SRI_LANKA_CITIES`, for labelling a raw coordinate."""
    best: tuple[str, float] | None = None
    for name, lat, lon, _district in SRI_LANKA_CITIES:
        distance = haversine_km(latitude, longitude, lat, lon)
        if best is None or distance < best[1]:
            best = (name, distance)
    return best


def cities() -> list[dict[str, object]]:
    """The city catalogue, served by `GET /cities` for the client's picker."""
    return [
        {"name": name, "latitude": lat, "longitude": lon, "district": district}
        for name, lat, lon, district in SRI_LANKA_CITIES
    ]


def resolve_city(name: str) -> tuple[str, float, float] | None:
    """Look up a city's centroid by name, for the geolocation-denied path.

    Matching is case- and whitespace-insensitive, then falls back to a prefix
    match, because the client sends back a label a human may have retyped. It
    deliberately does *not* fuzzy-match: silently resolving "Kandi" to Kandy
    would be pleasant, but silently resolving an unrecognised string to the
    nearest-looking city would send someone to the wrong end of the island. An
    unknown city is an error the caller should surface.
    """
    wanted = " ".join(str(name).strip().lower().split())
    if not wanted:
        return None
    for city, lat, lon, _district in SRI_LANKA_CITIES:
        if city.lower() == wanted:
            return city, lat, lon
    prefixed = [c for c in SRI_LANKA_CITIES if c[0].lower().startswith(wanted)]
    if len(prefixed) == 1:
        city, lat, lon, _district = prefixed[0]
        return city, lat, lon
    return None


# ---------------------------------------------------------------------------
# Venue
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Venue:
    """One place, as returned to the client."""

    id: str
    name: str
    latitude: float
    longitude: float
    kind: str  # normalised venue class: restaurant, bakery, cafe, ...
    tier: str  # pricing tier, see pricing.VENUE_TIER_MULTIPLIERS
    source: str  # 'overpass' | 'google' | 'seed'
    cuisines: tuple[str, ...] = ()
    # Halal status, tri-state on purpose - True and False are claims, None means
    # nobody has surveyed it. Two sources, in that order of authority: a provider
    # survey (only OpenStreetMap has one, via `diet:halal`) and, where there is
    # no survey, the operator's hand-compiled list - see `apply_curated_halal`.
    # `halal_label` and `halal_note` say which of the two is speaking, so the two
    # provenances cannot be confused on screen. Nothing infers this from a venue's
    # name: that would be a claim about someone's kitchen derived from a string,
    # and it is the reason matching against the curated list is whole-name only.
    #
    # The client badges True only. False is stored because "surveyed and tagged
    # no" is genuinely different from "untagged" - a future halal filter needs
    # that difference to be honest about what it excluded - but it is not shown,
    # since a crowdsourced tag is thin evidence for a public negative claim about
    # a named business.
    halal: bool | None = None
    halal_label: str | None = None
    halal_note: str | None = None
    address: str | None = None
    city: str | None = None
    phone: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    open_now: bool | None = None
    rating: float | None = None
    rating_count: int | None = None
    note: str | None = None
    # Coordinates are neighbourhood-level rather than surveyed. True for seed
    # entries, which is what makes the client link to a name search instead of a
    # pin - a wrong pin is worse than one extra tap.
    approximate: bool = False
    # Filled in by VenueFinder, per dish and per user location.
    distance_km: float | None = None
    confidence: str = CONFIDENCE_CATEGORY
    reason: str = ""
    price_low: int | None = None
    price_high: int | None = None
    price_display: str | None = None

    @property
    def map_url(self) -> str:
        """A link the user's own map app can resolve.

        Approximate entries link to a *search* by name, so the map app finds the
        real location rather than trusting a coordinate from the seed file.
        Surveyed entries link to the point.
        """
        if self.approximate:
            terms = ", ".join(part for part in (self.name, self.city, "Sri Lanka") if part)
            return f"https://www.google.com/maps/search/?api=1&query={quote_plus(terms)}"
        return (
            f"https://www.openstreetmap.org/?mlat={self.latitude:.5f}"
            f"&mlon={self.longitude:.5f}#map=18/{self.latitude:.5f}/{self.longitude:.5f}"
        )

    @property
    def directions_url(self) -> str:
        if self.approximate:
            return self.map_url
        return (
            "https://www.google.com/maps/dir/?api=1&destination="
            f"{self.latitude:.5f},{self.longitude:.5f}"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "kind": self.kind,
            "tier": self.tier,
            "source": self.source,
            "cuisines": list(self.cuisines),
            "halal": self.halal,
            "halal_label": self.halal_label,
            "halal_note": self.halal_note,
            "address": self.address,
            "city": self.city,
            "phone": self.phone,
            "website": self.website,
            "opening_hours": self.opening_hours,
            "open_now": self.open_now,
            "rating": self.rating,
            "rating_count": self.rating_count,
            "note": self.note,
            "approximate": self.approximate,
            "distance_km": None if self.distance_km is None else round(self.distance_km, 2),
            "confidence": self.confidence,
            "reason": self.reason,
            "price_estimate": (
                None
                if self.price_low is None
                else {
                    "low": self.price_low,
                    "high": self.price_high,
                    "display": self.price_display,
                    "tier": self.tier,
                    "estimated": True,
                }
            ),
            "map_url": self.map_url,
            "directions_url": self.directions_url,
        }


# ---------------------------------------------------------------------------
# Tier inference
# ---------------------------------------------------------------------------
_OSM_KIND_TO_TIER: dict[str, str] = {
    "restaurant": "casual",
    "fast_food": "street",
    "cafe": "cafe",
    "bakery": "bakery",
    "confectionery": "bakery",
    "pastry": "bakery",
    "ice_cream": "cafe",
    "food_court": "canteen",
    "marketplace": "street",
    "convenience": "street",
    "supermarket": "canteen",
    "greengrocer": "street",
    "deli": "cafe",
    "tea": "street",
    "coffee": "cafe",
    "beverages": "street",
}


def infer_tier(kind: str, tags: dict[str, str]) -> str:
    """Best guess at a venue's price tier from its tags.

    A restaurant attached to a hotel, or one carrying a star rating, is priced
    very differently from a rice-packet shop with the same `amenity=restaurant`.
    """
    if tags.get("tourism") in {"hotel", "resort", "guest_house"} or "stars" in tags:
        return "hotel"
    if tags.get("amenity") == "restaurant" and tags.get("cuisine") in {
        "international", "fine_dining", "french", "italian", "japanese",
    }:
        return "tourist"
    return _OSM_KIND_TO_TIER.get(kind, "casual")


def _split_cuisines(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(part.strip().lower() for part in raw.split(";") if part.strip())


# OpenStreetMap's `diet:halal`, and the only halal signal this module has.
#
# The tag has two positive values that mean different things: `only` says the
# whole kitchen is halal, `yes` says halal food is available alongside food that
# may not be. Collapsing them into one badge would overclaim for every venue
# carrying `yes`, so each gets its own label and its own sentence.
#
# Everything else is deliberately *not* a positive: `no` is recorded as a real
# negative, and `limited`, a blank, a typo or - overwhelmingly the common case -
# no tag at all becomes None, meaning nobody has surveyed this. `limited` is the
# interesting one: it is real information that cannot be rendered as a binary
# badge without lying in one direction or the other, so it stays unknown rather
# than being promoted.
#
# The wording lives here, not in the client, for the same reason the venue
# disclaimer and the confidence legend do: it is a claim about someone's kitchen
# and the caveat has to travel with it. Three real bugs in this project were a
# server caveat that never reached the screen.
HALAL_LABELS = {
    "only": (
        "Halal only",
        "Tagged in OpenStreetMap as an entirely halal kitchen. That tag is a "
        "mapper's contribution, not a certification - confirm with the venue.",
    ),
    "yes": (
        "Halal available",
        "Tagged in OpenStreetMap as serving halal food alongside food that may "
        "not be. That tag is a mapper's contribution, not a certification - "
        "confirm with the venue.",
    ),
}


def parse_halal(raw: object) -> tuple[bool | None, str | None, str | None]:
    """`diet:halal` -> (halal, badge label, the note that qualifies it).

    Tri-state like `open_now`: True and False are claims, None is "not surveyed".
    The label and note come back only for the positive values, because they exist
    to caption a badge and the negative case is never badged - see `Venue.halal`.
    """
    value = str(raw or "").strip().lower()
    if value in HALAL_LABELS:
        label, note = HALAL_LABELS[value]
        return True, label, note
    if value == "no":
        return False, None, None
    return None, None, None


def apply_curated_halal(venue: Venue) -> Venue:
    """Fill in the halal flag from the operator's list, if nothing surveyed it.

    Two rules, and the second is the one worth arguing about.

    **A provider survey wins, in both directions.** If OpenStreetMap tagged this
    venue `diet:halal`, that tag is kept even when the curated list disagrees -
    including when the tag is `no` and the list says halal, which leaves the venue
    unbadged. That is the same stance the pricing layer takes when the CSV band
    and the LKR table disagree: report the disagreement, never quietly reconcile
    it. Someone surveyed the place; a hand-written list is not grounds to overrule
    them, and printing a halal badge over an explicit `diet:halal=no` is the one
    outcome here with a real cost to a real user.

    **The curated claim is captioned as itself.** It gets `CURATED_LABEL` and
    `CURATED_NOTE`, not the `diet:halal` wording, so the badge never implies a
    survey or a certification that nobody performed.

    Applied once at the provider boundary in `_fetch`, which is why it reaches
    every provider (overpass, google and the seed fallback) and both `find()` and
    `nearby()` without either of them knowing about it.
    """
    if venue.halal is not None:
        return venue
    if curated_halal_name(venue.name) is None:
        return venue
    return replace(
        venue,
        halal=True,
        halal_label=CURATED_LABEL,
        halal_note=CURATED_NOTE,
    )


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
class TTLCache:
    """Small time-bounded LRU.

    Lock-guarded because FastAPI dispatches sync handlers onto a threadpool, so
    concurrent searches share this object. The project has already been bitten
    once by unsynchronised per-request state (README bug 17).
    """

    def __init__(self, max_size: int = 256, ttl_seconds: int = 900) -> None:
        self.max_size = max(1, max_size)
        self.ttl = max(0, ttl_seconds)
        self._data: "OrderedDict[tuple, tuple[float, list[Venue]]]" = OrderedDict()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: tuple) -> list[Venue] | None:
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                self.misses += 1
                return None
            stored_at, value = entry
            if self.ttl and now - stored_at > self.ttl:
                del self._data[key]
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return list(value)

    def put(self, key: tuple, value: Sequence[Venue]) -> None:
        with self._lock:
            self._data[key] = (time.monotonic(), list(value))
            self._data.move_to_end(key)
            while len(self._data) > self.max_size:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def stats(self) -> dict[str, object]:
        with self._lock:
            return {
                "entries": len(self._data),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl,
                "hits": self.hits,
                "misses": self.misses,
            }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def _http_json(
    url: str,
    *,
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 8.0,
) -> dict:
    """One JSON request. Every failure mode becomes PlacesUnavailable.

    Callers must not have to distinguish a DNS failure from a 429 from malformed
    JSON: all three mean "no live results this time, degrade".
    """
    request = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except Exception:  # pragma: no cover - best-effort diagnostics only
            pass
        raise PlacesUnavailable(f"HTTP {exc.code} from provider: {detail}") from exc
    except urllib.error.URLError as exc:
        raise PlacesUnavailable(f"cannot reach provider: {exc.reason}") from exc
    except TimeoutError as exc:
        raise PlacesUnavailable("provider timed out") from exc
    except OSError as exc:
        raise PlacesUnavailable(f"network error: {exc}") from exc

    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PlacesUnavailable(f"provider returned unparseable JSON: {exc}") from exc
    if not isinstance(decoded, dict):
        raise PlacesUnavailable("provider returned an unexpected payload shape")
    return decoded


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------
class SeedProvider:
    """The bundled list. Always available, never live.

    Seed rows carry no halal flag of their own. They name real Sri Lankan
    restaurants, and marking one halal from memory rather than from a source would
    be inventing a fact about a named business - so `Venue.halal` stays None here.
    A venue on the operator's curated list is badged one layer up, in
    `VenueFinder._fetch`, from that list and captioned as coming from it; keeping
    the two apart is what stops "this row happens to be in the seed file" from
    becoming the evidence. Everything the operator did not list reads as unknown,
    which is the point of the tri-state.
    """

    name = "seed"
    live = False

    def available(self) -> bool:
        return True

    def search(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        selectors: Sequence[tuple[str, str]],
    ) -> list[Venue]:
        wanted = {value for _key, value in selectors}
        out: list[Venue] = []
        for index, row in enumerate(SEED_VENUES):
            name, lat, lon, tier, kind, city, cuisines, note = row
            if wanted and kind not in wanted:
                continue
            if haversine_km(latitude, longitude, lat, lon) > radius_km:
                continue
            out.append(
                Venue(
                    id=f"seed:{index}",
                    name=name,
                    latitude=lat,
                    longitude=lon,
                    kind=kind,
                    tier=tier,
                    source="seed",
                    cuisines=cuisines,
                    city=city,
                    note=note,
                    approximate=True,
                )
            )
        return out


class OverpassProvider:
    """OpenStreetMap via Overpass. Keyless, so it is the default."""

    name = "overpass"
    live = True

    def __init__(self, url: str, timeout: float, user_agent: str) -> None:
        self.url = url
        self.timeout = timeout
        self.user_agent = user_agent

    def available(self) -> bool:
        return bool(self.url)

    def build_query(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        selectors: Sequence[tuple[str, str]],
        limit: int = 80,
    ) -> str:
        """Overpass QL for the requested venue classes.

        `["name"]` is required on every selector: an unnamed restaurant node
        cannot be shown to a user, and excluding them upstream keeps the response
        small enough to stay inside Overpass's fair-use limits.

        Both `node` and `way` are queried because larger premises are mapped as
        building outlines, and `out center` gives those a usable point.
        """
        radius_m = int(max(50.0, radius_km * 1000))
        clauses: list[str] = []
        for key, value in selectors:
            if not (_SAFE_TAG.match(key) and _SAFE_TAG.match(value)):
                continue
            around = f"(around:{radius_m},{latitude},{longitude})"
            clauses.append(f'  node["{key}"="{value}"]["name"]{around};')
            clauses.append(f'  way["{key}"="{value}"]["name"]{around};')
        if not clauses:
            raise PlacesUnavailable("no valid venue selectors")
        body = "\n".join(clauses)
        timeout_s = int(max(5, min(60, self.timeout * 3)))
        return f"[out:json][timeout:{timeout_s}];\n(\n{body}\n);\nout body center {limit};"

    def search(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        selectors: Sequence[tuple[str, str]],
    ) -> list[Venue]:
        query = self.build_query(latitude, longitude, radius_km, selectors)
        payload = _http_json(
            self.url,
            data=urllib.parse.urlencode({"data": query}).encode("utf-8"),
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=self.timeout,
        )
        return self.parse(payload)

    @staticmethod
    def parse(payload: dict) -> list[Venue]:
        """Elements -> Venues. Unusable elements are skipped, not fatal."""
        elements = payload.get("elements")
        if not isinstance(elements, list):
            return []

        out: list[Venue] = []
        for element in elements:
            if not isinstance(element, dict):
                continue
            tags = element.get("tags")
            if not isinstance(tags, dict):
                continue
            name = str(tags.get("name") or "").strip()
            if not name:
                continue

            # Nodes carry lat/lon directly; ways get a `center` from `out center`.
            latitude = element.get("lat")
            longitude = element.get("lon")
            if latitude is None or longitude is None:
                centre = element.get("center")
                if isinstance(centre, dict):
                    latitude = centre.get("lat")
                    longitude = centre.get("lon")
            try:
                latitude = float(latitude)  # type: ignore[arg-type]
                longitude = float(longitude)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                continue

            kind = str(tags.get("amenity") or tags.get("shop") or "restaurant")
            address_parts = [
                tags.get("addr:housenumber"),
                tags.get("addr:street"),
                tags.get("addr:suburb"),
            ]
            address = " ".join(str(p) for p in address_parts if p) or None
            halal, halal_label, halal_note = parse_halal(tags.get("diet:halal"))

            out.append(
                Venue(
                    id=f"osm:{element.get('type', 'node')}/{element.get('id', '')}",
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    kind=kind,
                    tier=infer_tier(kind, tags),
                    source="overpass",
                    cuisines=_split_cuisines(tags.get("cuisine")),
                    halal=halal,
                    halal_label=halal_label,
                    halal_note=halal_note,
                    address=address,
                    city=(str(tags.get("addr:city")) if tags.get("addr:city") else None),
                    phone=(
                        str(tags.get("phone") or tags.get("contact:phone"))
                        if (tags.get("phone") or tags.get("contact:phone"))
                        else None
                    ),
                    website=(
                        str(tags.get("website") or tags.get("contact:website"))
                        if (tags.get("website") or tags.get("contact:website"))
                        else None
                    ),
                    opening_hours=(
                        str(tags.get("opening_hours")) if tags.get("opening_hours") else None
                    ),
                )
            )
        return out


# OSM selector -> Google Places (New) `includedTypes` value.
_GOOGLE_TYPES: dict[tuple[str, str], str] = {
    ("amenity", "restaurant"): "restaurant",
    ("amenity", "fast_food"): "fast_food_restaurant",
    ("amenity", "cafe"): "cafe",
    ("amenity", "ice_cream"): "ice_cream_shop",
    ("amenity", "food_court"): "restaurant",
    ("amenity", "marketplace"): "market",
    ("shop", "bakery"): "bakery",
    ("shop", "confectionery"): "candy_store",
    ("shop", "pastry"): "bakery",
    ("shop", "convenience"): "convenience_store",
    ("shop", "supermarket"): "supermarket",
    ("shop", "greengrocer"): "grocery_store",
    ("shop", "deli"): "deli",
    ("shop", "tea"): "tea_house",
    ("shop", "coffee"): "coffee_shop",
    ("shop", "beverages"): "juice_shop",
}

# Google's priceLevel enum -> our pricing tiers.
_GOOGLE_PRICE_TIER = {
    "PRICE_LEVEL_FREE": "street",
    "PRICE_LEVEL_INEXPENSIVE": "street",
    "PRICE_LEVEL_MODERATE": "casual",
    "PRICE_LEVEL_EXPENSIVE": "tourist",
    "PRICE_LEVEL_VERY_EXPENSIVE": "hotel",
}

_GOOGLE_TYPE_TO_KIND = {
    "bakery": "bakery",
    "cafe": "cafe",
    "coffee_shop": "cafe",
    "tea_house": "cafe",
    "ice_cream_shop": "ice_cream",
    "candy_store": "confectionery",
    "convenience_store": "convenience",
    "supermarket": "supermarket",
    "grocery_store": "greengrocer",
    "fast_food_restaurant": "fast_food",
    "juice_shop": "beverages",
    "deli": "deli",
    "market": "marketplace",
    "restaurant": "restaurant",
}

_GOOGLE_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.primaryType",
        "places.nationalPhoneNumber",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.currentOpeningHours.openNow",
    )
)


class GooglePlacesProvider:
    """Google Places API (New), `places:searchNearby`.

    Written against the documented request/response shape. `available()` is False
    without a key, so misconfiguration surfaces as a degraded stage in
    `GET /health` rather than as a 500 at request time.
    """

    name = "google"
    live = True

    def __init__(self, url: str, api_key: str, timeout: float, max_results: int = 20) -> None:
        self.url = url
        self.api_key = api_key
        self.timeout = timeout
        self.max_results = max(1, min(20, max_results))  # API caps at 20

    def available(self) -> bool:
        return bool(self.url and self.api_key)

    def build_body(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        selectors: Sequence[tuple[str, str]],
    ) -> dict:
        types = [
            _GOOGLE_TYPES[selector] for selector in selectors if selector in _GOOGLE_TYPES
        ]
        if not types:
            types = ["restaurant"]
        return {
            "includedTypes": sorted(set(types)),
            "maxResultCount": self.max_results,
            "rankPreference": "DISTANCE",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    # The API caps the radius at 50 km.
                    "radius": float(min(50_000.0, max(1.0, radius_km * 1000))),
                }
            },
        }

    def search(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        selectors: Sequence[tuple[str, str]],
    ) -> list[Venue]:
        if not self.available():
            raise PlacesUnavailable("Google Places is selected but no API key is configured")
        body = self.build_body(latitude, longitude, radius_km, selectors)
        payload = _http_json(
            self.url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": self.api_key,
                "X-Goog-FieldMask": _GOOGLE_FIELD_MASK,
            },
            timeout=self.timeout,
        )
        return self.parse(payload)

    @staticmethod
    def parse(payload: dict) -> list[Venue]:
        places = payload.get("places")
        if not isinstance(places, list):
            return []

        out: list[Venue] = []
        for place in places:
            if not isinstance(place, dict):
                continue
            display = place.get("displayName")
            name = ""
            if isinstance(display, dict):
                name = str(display.get("text") or "").strip()
            elif isinstance(display, str):
                name = display.strip()
            if not name:
                continue

            location = place.get("location")
            if not isinstance(location, dict):
                continue
            try:
                latitude = float(location["latitude"])
                longitude = float(location["longitude"])
            except (KeyError, TypeError, ValueError):
                continue

            types = [str(t) for t in place.get("types", []) if isinstance(t, str)]
            primary = str(place.get("primaryType") or "")
            kind = "restaurant"
            for candidate in [primary, *types]:
                if candidate in _GOOGLE_TYPE_TO_KIND:
                    kind = _GOOGLE_TYPE_TO_KIND[candidate]
                    break

            price_level = str(place.get("priceLevel") or "")
            tier = _GOOGLE_PRICE_TIER.get(price_level) or _OSM_KIND_TO_TIER.get(kind, "casual")

            hours = place.get("currentOpeningHours")
            open_now = hours.get("openNow") if isinstance(hours, dict) else None

            rating = place.get("rating")
            rating_count = place.get("userRatingCount")

            out.append(
                Venue(
                    id=f"google:{place.get('id', name)}",
                    name=name,
                    latitude=latitude,
                    longitude=longitude,
                    kind=kind,
                    tier=tier,
                    source="google",
                    # Google has no cuisine field; its `types` are the closest
                    # equivalent and feed the same cuisine matching. It has no
                    # halal field at all, and there is no `types` value that
                    # stands in for one, so `halal` is left at None here - see
                    # `Venue.halal`. Leaving it None is also what lets the curated
                    # list fill it in later: this provider never overrules that
                    # list because it never has an opinion to overrule it with.
                    cuisines=tuple(types),
                    address=(
                        str(place["formattedAddress"])
                        if place.get("formattedAddress")
                        else None
                    ),
                    phone=(
                        str(place["nationalPhoneNumber"])
                        if place.get("nationalPhoneNumber")
                        else None
                    ),
                    website=(str(place["websiteUri"]) if place.get("websiteUri") else None),
                    open_now=open_now if isinstance(open_now, bool) else None,
                    rating=float(rating) if isinstance(rating, (int, float)) else None,
                    rating_count=(
                        int(rating_count) if isinstance(rating_count, (int, float)) else None
                    ),
                )
            )
        return out


class NullProvider:
    """`FOODAI_PLACES_PROVIDER=none`. Reports unavailable rather than guessing."""

    name = "none"
    live = False

    def available(self) -> bool:
        return False

    def search(self, *args: object, **kwargs: object) -> list[Venue]:
        raise PlacesUnavailable("venue lookup is disabled")


def build_provider(settings: object) -> object:
    """Construct the configured provider from `settings.places`."""
    places = getattr(settings, "places", settings)
    if not getattr(places, "enabled", True):
        return NullProvider()

    choice = str(getattr(places, "provider", "overpass")).strip().lower()
    if choice == "google":
        return GooglePlacesProvider(
            url=places.google_url,
            api_key=places.google_api_key,
            timeout=places.timeout_seconds,
            max_results=places.max_results,
        )
    if choice in {"static", "seed"}:
        return SeedProvider()
    if choice in {"none", "off", "disabled"}:
        return NullProvider()
    if choice != "overpass":
        log.warning("Unknown FOODAI_PLACES_PROVIDER %r; falling back to overpass", choice)
    return OverpassProvider(
        url=places.overpass_url,
        timeout=places.timeout_seconds,
        user_agent=places.user_agent,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------
class VenueFinder:
    """Turns (dish, location) into a ranked, honestly-labelled venue list."""

    def __init__(
        self,
        settings: object,
        provider: object | None = None,
        price_book: object | None = None,
    ) -> None:
        self.settings = getattr(settings, "places", settings)
        self.provider = provider if provider is not None else build_provider(settings)
        self.price_book = price_book
        self.seed = SeedProvider()
        self.cache = TTLCache(
            max_size=getattr(self.settings, "cache_size", 256),
            ttl_seconds=getattr(self.settings, "cache_ttl_seconds", 900),
        )
        self.last_error: str | None = None
        self.provider_calls = 0
        self.fallbacks = 0

    # -- availability ------------------------------------------------------
    @property
    def is_available(self) -> bool:
        return bool(self.provider.available()) or bool(
            getattr(self.settings, "fallback_to_seed", True)
        )

    def stats(self) -> dict[str, object]:
        return {
            "provider": self.provider.name,
            "live": bool(getattr(self.provider, "live", False)),
            "available": self.provider.available(),
            "fallback_to_seed": bool(getattr(self.settings, "fallback_to_seed", True)),
            "last_error": self.last_error,
            # Upstream calls actually issued, i.e. cache misses. Named for the
            # provider rather than "live" because the seed provider serves these
            # too, and `live_calls: 7` next to `live: false` reads as a bug.
            "provider_calls": self.provider_calls,
            "seed_fallbacks": self.fallbacks,
            "cache": self.cache.stats(),
            "default_radius_km": getattr(self.settings, "default_radius_km", 3.0),
            "max_radius_km": getattr(self.settings, "max_radius_km", 25.0),
            "coordinate_precision": getattr(self.settings, "coordinate_precision", 3),
        }

    # -- retrieval ---------------------------------------------------------
    def _fetch(
        self,
        latitude: float,
        longitude: float,
        radius_km: float,
        profile: VenueProfile,
    ) -> tuple[list[Venue], bool]:
        """Provider results for a profile, cached. Returns (venues, degraded).

        Cached on the *selector set* rather than the dish, so all 22 Short Eats
        share one upstream request instead of issuing 22 near-identical ones.
        """
        key = (
            self.provider.name,
            latitude,
            longitude,
            round(radius_km, 2),
            profile.cache_key,
        )
        cached = self.cache.get(key)
        if cached is not None:
            return cached, False

        degraded = False
        venues: list[Venue] = []
        if self.provider.available():
            try:
                venues = self.provider.search(
                    latitude, longitude, radius_km, profile.selectors
                )
                self.provider_calls += 1
                self.last_error = None
            except PlacesUnavailable as exc:
                # Deliberately no coordinates in the log line.
                log.warning("Venue provider %s unavailable: %s", self.provider.name, exc)
                self.last_error = str(exc)
                degraded = True
        else:
            degraded = True
            self.last_error = self.last_error or f"{self.provider.name} is not configured"

        if not venues and degraded and getattr(self.settings, "fallback_to_seed", True):
            venues = self.seed.search(latitude, longitude, radius_km, profile.selectors)
            self.fallbacks += 1

        # The halal layer sits here, at the provider boundary, for two reasons: it
        # is the one point every provider and both public methods pass through, and
        # doing it before `put` means the cache stores the finished record rather
        # than a half-annotated one that has to be re-decorated on every hit.
        venues = [apply_curated_halal(v) for v in venues]

        # Failures are not cached, so a transient timeout does not pin a degraded
        # result for the whole TTL.
        if not degraded:
            self.cache.put(key, venues)
        return venues, degraded

    # -- annotation --------------------------------------------------------
    @staticmethod
    def _classify(venue: Venue, profile: VenueProfile) -> tuple[str, str]:
        """Why this venue was included, and how strong that evidence is.

        Name first: a signboard saying "Kottu" is the strongest thing a POI
        record can tell us. Then the curated `note`, which only seed entries
        carry - it is hand-written by us and does describe what the place sells,
        so ignoring it would rank the actual kottu institution below seven
        interchangeable restaurants. Then the cuisine tag, then bare category.
        """
        if profile.name_confidence(venue.name):
            return CONFIDENCE_NAMED, REASON_NAME_MATCH
        if venue.note and profile.name_confidence(venue.note):
            return CONFIDENCE_NAMED, REASON_NOTE_MATCH
        if profile.cuisine_confidence(venue.cuisines):
            return CONFIDENCE_CUISINE, REASON_CUISINE_MATCH
        return CONFIDENCE_CATEGORY, REASON_CATEGORY_MATCH

    def _annotate(
        self,
        venue: Venue,
        profile: VenueProfile,
        latitude: float,
        longitude: float,
    ) -> Venue:
        """Attach distance, honest confidence, and a tier-scaled price."""
        distance = haversine_km(latitude, longitude, venue.latitude, venue.longitude)
        confidence, reason = self._classify(venue, profile)

        price_low = price_high = None
        price_display = None
        if self.price_book is not None:
            price = self.price_book.get(profile.dish)
            if price is not None:
                price_low, price_high = price.for_tier(venue.tier)
                price_display = f"{price.symbol} {price_low:,} - {price_high:,}"

        return replace(
            venue,
            distance_km=distance,
            confidence=confidence,
            reason=reason,
            price_low=price_low,
            price_high=price_high,
            price_display=price_display,
        )

    @staticmethod
    def _sort_key(venue: Venue) -> tuple:
        """Confidence first, then distance.

        A place whose sign says "Kottu" 900 m away beats a generic restaurant
        200 m away, because the near one may well not sell the dish at all.
        Within a confidence level, distance decides.
        """
        return (
            CONFIDENCE_ORDER.get(venue.confidence, 3),
            round(venue.distance_km or 0.0, 3),
            venue.name.lower(),
        )

    # -- public API --------------------------------------------------------
    def find(
        self,
        dish: object,
        latitude: float,
        longitude: float,
        radius_km: float | None = None,
        limit: int | None = None,
    ) -> dict[str, object]:
        """Nearby venues for one dish, with the metadata to explain the answer."""
        latitude, longitude = validate_coordinates(latitude, longitude)
        precision = int(getattr(self.settings, "coordinate_precision", 3))
        latitude = coarsen(latitude, precision)
        longitude = coarsen(longitude, precision)

        max_radius = float(getattr(self.settings, "max_radius_km", 25.0))
        radius = float(radius_km or getattr(self.settings, "default_radius_km", 3.0))
        radius = max(0.1, min(max_radius, radius))
        cap = int(limit or getattr(self.settings, "max_results", 12))

        profile = profile_for(dish)
        raw, degraded = self._fetch(latitude, longitude, radius, profile)

        annotated = [self._annotate(v, profile, latitude, longitude) for v in raw]
        # The provider's radius is a circle around a coarsened point, so trim
        # anything the rounding pushed outside the radius the user asked for.
        annotated = [v for v in annotated if (v.distance_km or 0.0) <= radius * 1.05]
        annotated.sort(key=self._sort_key)
        selected = annotated[:cap]

        city = nearest_city(latitude, longitude)
        return {
            "dish": profile.dish,
            "category": profile.category,
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "coarsened_to_decimals": precision,
                "nearest_city": None if city is None else city[0],
                "nearest_city_km": None if city is None else round(city[1], 1),
            },
            "radius_km": round(radius, 2),
            "results": [v.as_dict() for v in selected],
            "total": len(selected),
            "matched_before_limit": len(annotated),
            "provider": self.provider.name,
            "degraded": degraded,
            "provider_error": self.last_error if degraded else None,
            "searched": [f"{k}={v}" for k, v in profile.selectors],
            "keywords": list(profile.keywords),
            "accompaniment_only": profile.accompaniment_only,
            "note": profile.note,
            "confidence_legend": dict(CONFIDENCE_REASONS),
            # Nothing here is a menu check - say so in the payload, not just the docs.
            "disclaimer": self._disclaimer(for_dish=True),
        }

    def _disclaimer(self, *, for_dish: bool) -> str:
        """The honesty note carried by every venue payload.

        Two phrasings, one place: a dish search can be wrong about the *dish*,
        while a dish-free nearby search can only be wrong about the venue. Built
        here rather than at each return site so the two cannot drift, and so
        neither response can ship without one - `/venues/nearby` originally did,
        which meant the caveat was a property of the endpoint you happened to
        call rather than of the data.
        """
        source = f"Venue listings come from {self.provider.name}"
        if for_dish:
            return (
                f"{source}; no provider publishes menus, so a match means the "
                "place is the right kind of venue, not a confirmed sighting of the dish."
            )
        return (
            f"{source}; the categories are the provider's own tags, so this is a "
            "list of nearby food places rather than a check of what any of them serves."
        )

    def nearby(
        self,
        latitude: float,
        longitude: float,
        radius_km: float | None = None,
        limit: int | None = None,
        selectors: Sequence[tuple[str, str]] | None = None,
    ) -> dict[str, object]:
        """Food venues near a point, independent of any one dish."""
        latitude, longitude = validate_coordinates(latitude, longitude)
        precision = int(getattr(self.settings, "coordinate_precision", 3))
        latitude = coarsen(latitude, precision)
        longitude = coarsen(longitude, precision)

        max_radius = float(getattr(self.settings, "max_radius_km", 25.0))
        radius = float(radius_km or getattr(self.settings, "default_radius_km", 3.0))
        radius = max(0.1, min(max_radius, radius))
        cap = int(limit or getattr(self.settings, "max_results", 12))

        chosen = tuple(selectors) if selectors else (*DEFAULT_SELECTORS, BAKERY, CAFE)
        profile = VenueProfile(
            dish="",
            category="",
            selectors=tuple(dict.fromkeys(chosen)),
            cuisines=frozenset(),
            name_patterns=(),
            keywords=(),
            tiers=("casual",),
        )
        raw, degraded = self._fetch(latitude, longitude, radius, profile)

        venues: list[Venue] = []
        for venue in raw:
            distance = haversine_km(latitude, longitude, venue.latitude, venue.longitude)
            if distance > radius * 1.05:
                continue
            # No dish, so no dish-specific evidence: every venue keeps the
            # dataclass default of `category` confidence. The reason says why
            # rather than being left empty - an unexplained "category" badge
            # reads as a judgement about a dish nobody asked about.
            venues.append(
                replace(venue, distance_km=distance, reason=REASON_NO_DISH)
            )
        venues.sort(key=lambda v: (v.distance_km or 0.0, v.name.lower()))

        city = nearest_city(latitude, longitude)
        return {
            "location": {
                "latitude": latitude,
                "longitude": longitude,
                "coarsened_to_decimals": precision,
                "nearest_city": None if city is None else city[0],
                "nearest_city_km": None if city is None else round(city[1], 1),
            },
            "radius_km": round(radius, 2),
            "results": [v.as_dict() for v in venues[:cap]],
            "total": min(len(venues), cap),
            "matched_before_limit": len(venues),
            "provider": self.provider.name,
            "degraded": degraded,
            "provider_error": self.last_error if degraded else None,
            # Same keys as `find()`: one client component can render either
            # payload, and neither can be served without its caveat.
            "confidence_legend": dict(CONFIDENCE_REASONS),
            "disclaimer": self._disclaimer(for_dish=False),
        }
