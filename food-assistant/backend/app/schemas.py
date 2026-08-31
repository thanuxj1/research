"""Request/response models.

Request bodies are validated with Pydantic - that is where untrusted input
arrives and where validation earns its keep.

Responses are returned as plain dicts assembled by the service layer rather than
being re-validated through `response_model`. The response shapes are nested and
partly optional (`explanation` appears only when requested), and running every
response through a second validation pass would add a failure mode without
adding a guarantee: the dicts are built from typed dataclasses
(`Dish`, `ScoredDish`, `Warning`) that are already the source of truth. The
shapes are documented in the README and pinned by the service tests.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .feedback import MAX_RATING, MIN_RATING

MAX_TOP_K = 50


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=400, description="Natural-language query")
    top_k: int = Field(8, ge=1, le=MAX_TOP_K)
    health_conditions: List[str] = Field(
        default_factory=list,
        description="Condition ids from GET /conditions. Results are annotated and ranked down.",
    )
    strict_allergens: bool = Field(
        False,
        description="Remove dishes that conflict with allergy conditions instead of only warning.",
    )
    explain: bool = Field(False, description="Include the per-signal score breakdown.")
    rerank: bool = Field(True, description="Run the cross-encoder reranking stage.")
    diversify: bool = Field(True, description="Apply MMR diversification.")

    @field_validator("query")
    @classmethod
    def _strip_query(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query must not be blank")
        return stripped

    @field_validator("health_conditions")
    @classmethod
    def _dedupe_conditions(cls, value: List[str]) -> List[str]:
        seen: set[str] = set()
        out: List[str] = []
        for item in value:
            cleaned = item.strip()
            if cleaned and cleaned not in seen:
                seen.add(cleaned)
                out.append(cleaned)
        return out


class RecommendRequest(BaseModel):
    category: Optional[str] = None
    is_veg: Optional[str] = None
    meal_time: Optional[str] = None
    spicy_level: Optional[str] = None
    price_range: Optional[str] = None
    top_k: int = Field(8, ge=1, le=MAX_TOP_K)
    health_conditions: List[str] = Field(default_factory=list)
    strict_allergens: bool = False
    explain: bool = False

    @field_validator("category", "is_veg", "meal_time", "spicy_level", "price_range")
    @classmethod
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        """The UI submits "" for "Any"; treat it as absent."""
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class HealthCheckRequest(BaseModel):
    foods: List[str] = Field(..., description="Dish names to evaluate")
    conditions: List[str] = Field(default_factory=list)


class SimilarRequest(BaseModel):
    name: str = Field(..., min_length=1)
    top_k: int = Field(6, ge=1, le=MAX_TOP_K)
    health_conditions: List[str] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    """A rating of the recommender, with an optional comment.

    Only two fields, and that is the whole design. Anything else the browser
    could helpfully attach - the last query, the dishes on screen, a session id -
    would turn an opinion into a record about a person, and `feedback.py` exists
    on the promise that it does not do that. If a maintainer later needs to know
    *which* results a 2-star rating was about, the honest way to get it is to ask
    for it in the comment box, not to collect it quietly.

    `rating` is bounded here and re-checked in `FeedbackStore.submit`: this guards
    the HTTP edge, the store guards every other caller. The bounds are imported
    from `feedback` rather than written as 1 and 5, so widening the scale cannot
    leave this model quietly rejecting the new values. `comment` is bounded to a
    hard 2000 here while the store truncates at the configured limit (600 by
    default) - the outer bound stops a megabyte body being parsed at all, the
    inner one is the product decision about how long a comment should be.
    """

    rating: int = Field(
        ...,
        ge=MIN_RATING,
        le=MAX_RATING,
        description="1 (not useful) to 5 (very useful). Labels come from GET /feedback.",
    )
    comment: Optional[str] = Field(
        None, max_length=2000, description="Optional free text; truncated to the server limit."
    )

    @field_validator("comment")
    @classmethod
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class NearbyRequest(BaseModel):
    """Where the user is, for a venue lookup.

    Latitude and longitude are bounded here rather than trusted from the client.
    `places.validate_coordinates` re-checks them, and that is deliberate: this
    model guards the HTTP edge, while the service function guards every other
    caller (the city fallback, tests, a future scheduled job).

    Coordinates are *not* coarsened here. Rounding is done in the service, so
    that a single documented precision setting applies whichever way a request
    arrives, and so this model stays a faithful record of what the browser sent.
    """

    latitude: Optional[float] = Field(
        None, ge=-90.0, le=90.0, description="WGS84 latitude from navigator.geolocation"
    )
    longitude: Optional[float] = Field(
        None, ge=-180.0, le=180.0, description="WGS84 longitude"
    )
    city: Optional[str] = Field(
        None,
        max_length=80,
        description="Fallback when geolocation is denied - a name from GET /cities.",
    )
    radius_km: Optional[float] = Field(
        None, gt=0.0, le=200.0, description="Search radius; clamped to the server maximum."
    )
    limit: int = Field(12, ge=1, le=50)
    dish: Optional[str] = Field(
        None, max_length=120, description="Restrict to venues likely to serve this dish."
    )

    @field_validator("city", "dish")
    @classmethod
    def _blank_to_none(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def _require_a_location(self) -> "NearbyRequest":
        """Either both coordinates or a city - never one coordinate alone.

        A lone latitude is the signature of a client bug (a failed geolocation
        read that still submitted). Silently treating it as "no location" would
        return venues near Colombo and look like a working feature, so it is
        rejected loudly instead.
        """
        has_lat = self.latitude is not None
        has_lon = self.longitude is not None
        if has_lat != has_lon:
            raise ValueError("latitude and longitude must be provided together")
        if not has_lat and not self.city:
            raise ValueError("provide either latitude and longitude, or a city")
        return self
