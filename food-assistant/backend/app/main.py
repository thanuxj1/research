"""FastAPI application.

Uses the `lifespan` context manager rather than the deprecated
`@app.on_event("startup")` hook the original relied on.

The app is intentionally resilient about its own dependencies. The corpus, BM25
index, fuzzy matcher, query analyzer, health engine and rule-based recommender
are all pure Python, so the API serves useful results even when the embedding
model, the cross-encoder or the pickled XGBoost model are unavailable. Whatever
is degraded is reported by `GET /health` instead of failing silently.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import feedback as feedback_module
from . import health as health_module
from . import places as places_module
from . import pricing as pricing_module
from .config import settings
from .corpus import load_corpus
from .pricing import PriceBook
from .recommend import Recommender
from .schemas import (
    FeedbackRequest,
    HealthCheckRequest,
    NearbyRequest,
    RecommendRequest,
    SearchRequest,
    SimilarRequest,
)
from .search import SearchService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
log = logging.getLogger("foodai")

state: dict[str, object] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Loading corpus from %s", settings.data_path)
    corpus = load_corpus(
        settings.data_path,
        name_weight=settings.retrieval.name_field_weight,
        tag_weight=settings.retrieval.tag_field_weight,
    )
    log.info("Loaded %d dishes", len(corpus))

    price_book = _build_price_book(corpus)
    venue_finder = places_module.VenueFinder(settings, price_book=price_book)

    service = SearchService(corpus, settings, price_book=price_book)
    service.build()

    recommender = Recommender(corpus, settings, price_book=price_book)
    recommender.load()

    state["corpus"] = corpus
    state["search"] = service
    state["recommender"] = recommender
    state["prices"] = price_book
    state["venues"] = venue_finder
    # Built here rather than at import time so the log path is opened by the
    # running server, not by every `import app.main` in a test collector. The API
    # version goes in with each record: a 2-star rating is uninterpretable without
    # knowing which ranking produced it.
    state["feedback"] = feedback_module.store_from_settings(settings, api_version=app.version)
    if state["feedback"] is None:
        log.info("Feedback collection disabled (FOODAI_FEEDBACK_ENABLED=0)")
    else:
        log.info("Feedback log: %s", settings.feedback.path)
    log.info("Ready. Search mode: %s", service.mode)

    yield

    state.clear()


def _build_price_book(corpus) -> PriceBook | None:
    """Load the price table, or return None when pricing is switched off.

    A malformed `FOODAI_PRICE_TABLE` degrades to the bundled table rather than
    taking the API down - consistent with how a missing embedding model is
    handled - and the reason is logged and surfaced by /health.

    Band disagreements between the numeric prices and the dataset's
    Low/Medium/High column are logged at startup. They are not fatal: the CSV
    column stays authoritative for ranking (it is an XGBoost feature), and the
    numbers stay authoritative for display. But a drift of more than a handful
    means one of the two needs updating, and a silent divergence is exactly the
    bug this cross-check exists to catch.
    """
    if not settings.pricing.enabled:
        log.info("Pricing disabled (FOODAI_PRICING_ENABLED=0)")
        return None

    kwargs: dict[str, object] = {
        "inflation": settings.pricing.inflation,
        "stale_days": settings.pricing.stale_days,
        "currency": settings.pricing.currency,
        "symbol": settings.pricing.symbol,
    }
    if settings.pricing.as_of:
        kwargs["as_of"] = settings.pricing.as_of

    if settings.pricing.table_path:
        from pathlib import Path

        from .pricing import load_price_table

        try:
            kwargs["table"] = load_price_table(Path(settings.pricing.table_path))
            log.info("Loaded price overrides from %s", settings.pricing.table_path)
        except (OSError, ValueError) as exc:
            log.error(
                "Could not read FOODAI_PRICE_TABLE=%s (%s). Using the bundled table.",
                settings.pricing.table_path,
                exc,
            )

    book = PriceBook(**kwargs)  # type: ignore[arg-type]

    missing = book.missing(corpus.names)
    if missing:
        log.warning(
            "%d dishes have no price and will render without one (e.g. %s)",
            len(missing),
            ", ".join(missing[:3]),
        )
    mismatches = book.band_mismatches(corpus)
    if mismatches:
        log.warning(
            "%d dishes disagree with the dataset price_range column (e.g. %s)",
            len(mismatches),
            ", ".join(str(m.get("dish")) for m in mismatches[:3]),
        )
    if book.stale:
        log.warning(
            "Price table is %d days old (as_of=%s); results are badged stale.",
            book.age_days,
            book.as_of,
        )
    return book


app = FastAPI(
    title="Sri Lankan Food AI",
    version="3.0",
    description=(
        "Multi-stage semantic search over Sri Lankan cuisine: query understanding, "
        "hybrid dense + BM25 retrieval, reciprocal rank fusion, cross-encoder "
        "reranking, explainable additive scoring, and MMR diversification."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_search() -> SearchService:
    service = state.get("search")
    if service is None:
        raise HTTPException(status_code=503, detail="Search service is still starting up")
    return service  # type: ignore[return-value]


def get_recommender() -> Recommender:
    recommender = state.get("recommender")
    if recommender is None:
        raise HTTPException(status_code=503, detail="Recommender is still starting up")
    return recommender  # type: ignore[return-value]


def get_corpus():
    corpus = state.get("corpus")
    if corpus is None:
        raise HTTPException(status_code=503, detail="Corpus is still loading")
    return corpus


def get_prices() -> PriceBook:
    """The price book, or 503 when pricing is disabled.

    Disabled pricing is a 503 rather than an empty 200: a client that asked for
    prices and got `{"prices": []}` would render "no prices available" as if the
    dishes were unpriced, when in fact the feature is switched off. The
    distinction is visible in /health.
    """
    book = state.get("prices")
    if book is None:
        raise HTTPException(
            status_code=503,
            detail="Pricing is disabled on this server (FOODAI_PRICING_ENABLED=0)",
        )
    return book  # type: ignore[return-value]


def get_venues():
    finder = state.get("venues")
    if finder is None:
        raise HTTPException(status_code=503, detail="Venue lookup is still starting up")
    if not finder.is_available:  # type: ignore[union-attr]
        raise HTTPException(
            status_code=503,
            detail=(
                "Venue lookup is unavailable: no provider is configured and the "
                "seed fallback is disabled."
            ),
        )
    return finder


def get_feedback() -> feedback_module.FeedbackStore:
    """The feedback log, or 503 when collection is switched off.

    Only POST uses this. GET /feedback answers with `enabled: false` instead, so
    the panel can render an honest "switched off" rather than an error - the 503
    is reserved for the case where someone has actually typed something and needs
    to know it did not land.
    """
    store = state.get("feedback")
    if store is None:
        raise HTTPException(
            status_code=503,
            detail=feedback_module.COPY["disabled_note"],
        )
    return store  # type: ignore[return-value]


def _resolve_location(request: NearbyRequest) -> tuple[float, float, str | None]:
    """Coordinates for a request, from the browser or from the city fallback.

    Returns `(latitude, longitude, resolved_city)`. Explicit coordinates win over
    a city name when both are sent: the browser fix is more precise than a
    centroid, and a stale city stored in `localStorage` should not override a
    live position.
    """
    if request.latitude is not None and request.longitude is not None:
        return request.latitude, request.longitude, None

    resolved = places_module.resolve_city(request.city or "")
    if resolved is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown city: {request.city!r}. See GET /cities for valid names.",
        )
    city, lat, lon = resolved
    return lat, lon, city


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------
@app.post("/search", tags=["search"])
def search(request: SearchRequest) -> dict:
    """Multi-stage semantic search.

    Returns results plus a `understanding` block showing how the query was
    parsed (corrections, detected constraints, negations) and a `pipeline` block
    showing which stages actually ran.
    """
    service = get_search()
    return service.search(
        query=request.query,
        top_k=request.top_k,
        health_conditions=request.health_conditions,
        strict_allergens=request.strict_allergens,
        explain=request.explain,
        rerank=request.rerank,
        diversify=request.diversify,
    )


@app.get("/search", tags=["search"])
def search_get(
    q: str = Query(..., min_length=1, max_length=400),
    top_k: int = Query(8, ge=1, le=settings.max_top_k),
    explain: bool = Query(False),
) -> dict:
    """GET form of /search, convenient for debugging and shareable links."""
    return get_search().search(query=q, top_k=top_k, explain=explain)


@app.get("/autocomplete", tags=["search"])
def autocomplete(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(8, ge=1, le=20),
) -> dict:
    """Dish-name typeahead with a fuzzy fallback for misspellings."""
    return {"query": q, "suggestions": get_search().autocomplete(q, limit)}


@app.post("/similar", tags=["search"])
def similar(request: SimilarRequest) -> dict:
    """More-like-this over the dense index."""
    try:
        return get_search().similar(
            request.name, request.top_k, request.health_conditions
        )
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown dish: {request.name}")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/similar/{name}", tags=["search"])
def similar_get(name: str, top_k: int = Query(6, ge=1, le=settings.max_top_k)) -> dict:
    try:
        return get_search().similar(name, top_k)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown dish: {name}")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------
@app.post("/recommend", tags=["recommend"])
def recommend(request: RecommendRequest) -> dict:
    """Structured recommendation from explicit preferences."""
    return get_recommender().recommend(
        category=request.category,
        is_veg=request.is_veg,
        meal_time=request.meal_time,
        spicy_level=request.spicy_level,
        price_range=request.price_range,
        top_k=request.top_k,
        health_conditions=request.health_conditions,
        strict_allergens=request.strict_allergens,
        explain=request.explain,
    )


# ---------------------------------------------------------------------------
# Health profile
# ---------------------------------------------------------------------------
@app.get("/conditions", tags=["health"])
def conditions() -> dict:
    """Supported health conditions.

    The frontend renders this list rather than hardcoding it. The original app
    duplicated the condition catalogue *and* the warning rules on the client,
    and the two copies had already drifted from the server's.
    """
    return {"conditions": health_module.catalog()}


@app.post("/health-check", tags=["health"])
def health_check(request: HealthCheckRequest) -> dict:
    """Warnings for specific dishes against specific conditions."""
    corpus = get_corpus()
    results = []
    unknown: list[str] = []

    for name in request.foods:
        dish = corpus.get(name)
        if dish is None:
            unknown.append(name)
            continue
        warnings = health_module.evaluate(dish.tags, dish.spicy_level, request.conditions)
        results.append(
            {
                "food_name": dish.name,
                "severity": health_module.worst_severity(warnings),
                "warnings": [w.as_dict() for w in warnings],
            }
        )

    return {"results": results, "unknown_foods": unknown}


# ---------------------------------------------------------------------------
# Catalogue / metadata
# ---------------------------------------------------------------------------
@app.get("/facets", tags=["catalogue"])
def facets() -> dict:
    """Facet values with counts, for filter controls."""
    return get_corpus().facets()


@app.get("/options", tags=["catalogue"], deprecated=True)
def options() -> dict:
    """Flat facet lists.

    Retained for compatibility with the original client. New code should call
    `/facets`, which returns counts as well.
    """
    corpus = get_corpus()
    data = corpus.facets()
    return {
        "categories": [item["value"] for item in data["categories"]],
        "meal_times": [item["value"] for item in data["meal_times"]],
        "spicy_levels": [item["value"] for item in data["spicy_levels"]],
        "price_ranges": [item["value"] for item in data["price_ranges"]],
        "veg_options": [["Vegetarian", "True"], ["Non-Vegetarian", "False"]],
    }


@app.get("/dishes", tags=["catalogue"])
def dishes(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    category: Optional[str] = None,
) -> dict:
    """Browse the catalogue."""
    corpus = get_corpus()
    book = state.get("prices")
    items = [d for d in corpus if category is None or d.category == category]
    window = items[offset : offset + limit]
    return {
        "results": [
            d.public_dict(None if book is None else book.get(d.name))  # type: ignore[union-attr]
            for d in window
        ],
        "total": len(items),
        "limit": limit,
        "offset": offset,
    }


@app.get("/dishes/{name}", tags=["catalogue"])
def dish_detail(name: str) -> dict:
    dish = get_corpus().get(name)
    if dish is None:
        raise HTTPException(status_code=404, detail=f"Unknown dish: {name}")
    book = state.get("prices")
    price = None if book is None else book.get(dish.name)  # type: ignore[union-attr]
    return dish.public_dict(price)


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------
@app.get("/prices", tags=["prices"])
def prices(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Every dish's price estimate, plus the table's provenance.

    Not on the client's critical path: every endpoint that returns a dish already
    embeds that dish's price via `Dish.public_dict(price)`, so a card is never
    waiting on a second request and cannot render before its own price arrives.
    This endpoint is the operator's view - whole-table provenance, `unpriced`, and
    `band_mismatches` against the CSV's `price_range` column - and the answer to
    "what does the table currently say" without walking 155 dishes. `meta` carries
    `as_of` and `stale`; the client badges staleness from the same figures
    reported by `GET /health`.
    """
    book = get_prices()
    corpus = get_corpus()
    dishes = list(corpus)[offset : offset + limit]
    items = []
    for dish in dishes:
        price = book.get(dish.name)
        items.append(
            {
                "name": dish.name,
                "category": dish.category,
                "price": None if price is None else price.as_dict(),
            }
        )
    return {
        "results": items,
        "total": len(corpus),
        "limit": limit,
        "offset": offset,
        "meta": book.stats(),
        "unpriced": book.missing(corpus.names),
        # Surfaced rather than buried: where the numbers and the dataset's
        # Low/Medium/High column disagree, both are shown so the drift is
        # inspectable instead of being quietly reconciled in one direction.
        "band_mismatches": book.band_mismatches(corpus),
    }


@app.get("/prices/{name}", tags=["prices"])
def price_detail(name: str) -> dict:
    """One dish's price, including the per-venue-tier breakdown.

    The tier estimates are derived by multiplier from the typical price, not
    observed per venue. That is stated in the payload because a figure labelled
    "hotel" looks researched, and this one is arithmetic.
    """
    book = get_prices()
    dish = get_corpus().get(name)
    if dish is None:
        raise HTTPException(status_code=404, detail=f"Unknown dish: {name}")
    price = book.get(dish.name)
    if price is None:
        raise HTTPException(status_code=404, detail=f"No price estimate for: {dish.name}")

    tiers = {}
    for tier in pricing_module.VENUE_TIER_MULTIPLIERS:
        low, high = price.for_tier(tier)
        tiers[tier] = {
            "low": low,
            "high": high,
            "multiplier": pricing_module.VENUE_TIER_MULTIPLIERS[tier],
        }
    return {
        "dish": dish.name,
        "price": price.as_dict(),
        "by_venue_tier": tiers,
        "tier_note": (
            "Tier figures scale the typical price by a fixed multiplier; they are "
            "arithmetic, not per-venue observations."
        ),
    }


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------
@app.get("/cities", tags=["places"])
def cities() -> dict:
    """City centroids for the picker shown when geolocation is denied.

    Served rather than bundled in the client for the same reason as
    /conditions: two copies of a list drift, and the server's is the one the
    venue lookup actually resolves against.
    """
    return {"cities": places_module.cities()}


@app.post("/venues/nearby", tags=["places"])
def venues_nearby(request: NearbyRequest) -> dict:
    """Food venues near a point, independent of any dish."""
    finder = get_venues()
    latitude, longitude, city = _resolve_location(request)
    try:
        payload = finder.nearby(  # type: ignore[union-attr]
            latitude=latitude,
            longitude=longitude,
            radius_km=request.radius_km,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    payload["resolved_from_city"] = city
    return payload


@app.post("/dishes/{name}/venues", tags=["places"])
def dish_venues(name: str, request: NearbyRequest) -> dict:
    """Where to eat a specific dish, nearest first.

    POST rather than GET despite being a read: the body carries the user's
    coordinates, and putting a live position in a URL would write it into access
    logs, `Referer` headers and browser history. The response is not cacheable by
    a shared cache for the same reason.
    """
    finder = get_venues()
    dish = get_corpus().get(name)
    if dish is None:
        raise HTTPException(status_code=404, detail=f"Unknown dish: {name}")

    latitude, longitude, city = _resolve_location(request)
    try:
        payload = finder.find(  # type: ignore[union-attr]
            dish=dish,
            latitude=latitude,
            longitude=longitude,
            radius_km=request.radius_km,
            limit=request.limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    payload["resolved_from_city"] = city
    book = state.get("prices")
    price = None if book is None else book.get(dish.name)  # type: ignore[union-attr]
    payload["price"] = None if price is None else price.as_dict()
    return payload


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------
@app.get("/feedback", tags=["feedback"])
def feedback_form() -> dict:
    """The form to draw, its rating scale, and the totals so far.

    The scale, the comment limit and the privacy note are served rather than
    hard-coded in the client for the same reason as /conditions and /cities: they
    are values this server enforces, and a client copy of an enforced value is a
    client copy that can be wrong. It answers 200 with `enabled: false` when
    collection is off, because the panel still has to render something true.
    """
    store = state.get("feedback")
    if store is None:
        return feedback_module.disabled_form()
    return store.form()  # type: ignore[union-attr]


@app.post("/feedback", tags=["feedback"])
def submit_feedback(request: FeedbackRequest) -> dict:
    """Record one rating, with an optional comment.

    Returns the sentence to show the user in `message`, written by the module
    that did the storing. The client renders it verbatim instead of printing its
    own "thanks, saved!", so a submission that was deduplicated, refused or
    dropped cannot be reported to the user as a success.
    """
    store = get_feedback()
    try:
        return store.submit(request.rating, request.comment)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except feedback_module.FeedbackUnavailable as exc:
        # 503 rather than 500: the log being full or the volume read-only is a
        # condition of this server, not a bug in the request. `str(exc)` is the
        # prepared sentence, which also promises that nothing was stored.
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/feedback/summary", tags=["feedback"])
def feedback_summary() -> dict:
    """Counts and the mean rating. Never comment text.

    Comments are written for the maintainers reading the log; this endpoint is
    unauthenticated, and free text submitted in the expectation of being read by
    the maintainers is not ours to republish. `test_feedback` asserts a submitted
    comment appears nowhere in this payload.
    """
    store = state.get("feedback")
    if store is None:
        raise HTTPException(status_code=503, detail=feedback_module.COPY["disabled_note"])
    return store.summary()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# Ops
# ---------------------------------------------------------------------------
@app.get("/health", tags=["ops"])
def health_status() -> dict:
    """Liveness plus which pipeline stages are actually available.

    A degraded stage (missing embedding model, unloadable reranker) is reported
    here rather than being hidden, so a silent quality downgrade is observable.
    """
    service = state.get("search")
    recommender = state.get("recommender")
    corpus = state.get("corpus")
    book = state.get("prices")
    finder = state.get("venues")
    notes = state.get("feedback")
    return {
        "status": "ok" if service is not None else "starting",
        "dishes": len(corpus) if corpus is not None else 0,
        "search": service.stats() if service is not None else None,  # type: ignore[union-attr]
        "recommender": recommender.stats() if recommender is not None else None,  # type: ignore[union-attr]
        # Each of these reports `enabled: false` rather than being omitted, so a
        # disabled feature is distinguishable from a broken one at a glance.
        "pricing": (
            {"enabled": False}
            if book is None
            else {"enabled": True, **book.stats()}  # type: ignore[union-attr]
        ),
        "places": (
            {"enabled": False}
            if finder is None
            else {"enabled": True, **finder.stats()}  # type: ignore[union-attr]
        ),
        # Counts and the log's size, never content. `accepting` going false here
        # is the early warning that the size ceiling is about to start refusing
        # submissions.
        "feedback": (
            {"enabled": False}
            if notes is None
            else {"enabled": True, **notes.stats()}  # type: ignore[union-attr]
        ),
    }


@app.get("/config", tags=["ops"])
def config() -> dict:
    """Effective ranking configuration, for tuning and reproducibility."""
    return {"settings": {k: str(v) for k, v in settings.as_dict().items()}}


@app.get("/", tags=["ops"])
def root() -> dict:
    return {
        "name": "Sri Lankan Food AI",
        "version": app.version,
        "docs": "/docs",
        "endpoints": [
            "POST /search",
            "GET /search?q=",
            "GET /autocomplete?q=",
            "POST /similar",
            "POST /recommend",
            "GET /conditions",
            "POST /health-check",
            "GET /facets",
            "GET /dishes",
            "GET /prices",
            "GET /prices/{name}",
            "GET /cities",
            "POST /venues/nearby",
            "POST /dishes/{name}/venues",
            "GET /feedback",
            "POST /feedback",
            "GET /feedback/summary",
            "GET /health",
        ],
    }
