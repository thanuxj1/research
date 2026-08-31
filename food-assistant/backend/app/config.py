"""Runtime configuration.

Every tunable in the search pipeline is surfaced here so ranking behaviour can be
adjusted without touching pipeline code. Values are overridable via environment
variables, which keeps the container/12-factor story clean.

Deliberately dependency-free (stdlib only) so it can be imported by unit tests
that do not have the ML stack installed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_str(key: str, default: str) -> str:
    value = os.environ.get(key)
    return default if value is None or value == "" else value


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ[key])
    except (KeyError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ[key])
    except (KeyError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RetrievalSettings:
    """Stage 1 - candidate generation."""

    # Bi-encoder. BGE models are asymmetric: queries need an instruction prefix.
    embedding_model: str = field(
        default_factory=lambda: _env_str("FOODAI_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    )
    query_instruction: str = field(
        default_factory=lambda: _env_str(
            "FOODAI_QUERY_INSTRUCTION",
            "Represent this sentence for searching relevant passages: ",
        )
    )
    # Candidates pulled from each retriever before fusion. Generous, because the
    # corpus is small (155 docs) and recall is cheap.
    dense_top_k: int = field(default_factory=lambda: _env_int("FOODAI_DENSE_TOP_K", 60))
    sparse_top_k: int = field(default_factory=lambda: _env_int("FOODAI_SPARSE_TOP_K", 60))
    fuzzy_top_k: int = field(default_factory=lambda: _env_int("FOODAI_FUZZY_TOP_K", 15))
    # Minimum similarity for a fuzzy dish-name match to count as a typo hit.
    fuzzy_threshold: float = field(default_factory=lambda: _env_float("FOODAI_FUZZY_THRESHOLD", 0.82))
    # BM25 field weighting: the dish name is repeated this many times in the
    # sparse document so exact name hits outrank incidental description hits.
    name_field_weight: int = field(default_factory=lambda: _env_int("FOODAI_NAME_FIELD_WEIGHT", 3))
    tag_field_weight: int = field(default_factory=lambda: _env_int("FOODAI_TAG_FIELD_WEIGHT", 2))


@dataclass(frozen=True)
class FusionSettings:
    """Stage 2 - rank fusion."""

    # Reciprocal Rank Fusion smoothing constant (Cormack et al. 2009).
    rrf_k: int = field(default_factory=lambda: _env_int("FOODAI_RRF_K", 60))
    dense_weight: float = field(default_factory=lambda: _env_float("FOODAI_DENSE_WEIGHT", 1.0))
    sparse_weight: float = field(default_factory=lambda: _env_float("FOODAI_SPARSE_WEIGHT", 0.7))
    fuzzy_weight: float = field(default_factory=lambda: _env_float("FOODAI_FUZZY_WEIGHT", 0.4))
    # How many fused candidates continue to the cross-encoder.
    rerank_candidates: int = field(default_factory=lambda: _env_int("FOODAI_RERANK_CANDIDATES", 30))


@dataclass(frozen=True)
class RerankSettings:
    """Stage 3 - cross-encoder reranking."""

    enabled: bool = field(default_factory=lambda: _env_bool("FOODAI_RERANK_ENABLED", True))
    model: str = field(
        default_factory=lambda: _env_str("FOODAI_RERANK_MODEL", "BAAI/bge-reranker-base")
    )
    batch_size: int = field(default_factory=lambda: _env_int("FOODAI_RERANK_BATCH_SIZE", 32))
    # Blend of cross-encoder relevance vs first-stage fused rank. The cross-encoder
    # is far more accurate, but keeping a little first-stage signal stabilises
    # ties and protects against reranker overconfidence on short queries.
    weight: float = field(default_factory=lambda: _env_float("FOODAI_RERANK_WEIGHT", 0.75))


@dataclass(frozen=True)
class ScoringSettings:
    """Stage 4 - additive signal scoring.

    The original implementation multiplied penalties together, so three weak
    signals could annihilate a score (0.3 * 0.15 * 0.1 = 0.0045) and no single
    factor was attributable. These weights are additive contributions on a
    normalised [0, 1] relevance base, which keeps the final score bounded,
    monotonic in each signal, and fully explainable.
    """

    relevance_weight: float = field(default_factory=lambda: _env_float("FOODAI_W_RELEVANCE", 1.0))

    exact_name_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_EXACT_NAME", 0.55))
    partial_name_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_PARTIAL_NAME", 0.22))

    diet_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_DIET", 0.30))
    spice_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_SPICE", 0.26))
    meal_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_MEAL", 0.18))
    price_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_PRICE", 0.16))
    category_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_CATEGORY", 0.34))
    tag_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_TAG", 0.24))
    intent_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_INTENT", 0.20))
    # Weight of the numeric budget signal when a query states an amount ("under
    # 500 rupees"). Lives here with the other weights rather than in
    # PricingSettings: it is a ranking knob, not a property of the price table.
    budget_match_bonus: float = field(default_factory=lambda: _env_float("FOODAI_W_BUDGET", 0.28))

    # Soft violations. Hard violations are filtered out upstream instead.
    soft_violation_penalty: float = field(
        default_factory=lambda: _env_float("FOODAI_W_SOFT_VIOLATION", -0.30)
    )
    health_danger_penalty: float = field(
        default_factory=lambda: _env_float("FOODAI_W_HEALTH_DANGER", -0.55)
    )
    health_caution_penalty: float = field(
        default_factory=lambda: _env_float("FOODAI_W_HEALTH_CAUTION", -0.18)
    )


@dataclass(frozen=True)
class DiversitySettings:
    """Stage 5 - Maximal Marginal Relevance."""

    enabled: bool = field(default_factory=lambda: _env_bool("FOODAI_MMR_ENABLED", True))
    # 1.0 = pure relevance, 0.0 = pure diversity.
    lambda_: float = field(default_factory=lambda: _env_float("FOODAI_MMR_LAMBDA", 0.82))
    # Additional penalty applied per repeat of an already-selected category, to
    # stop a result page becoming six variations of kottu.
    category_repeat_penalty: float = field(
        default_factory=lambda: _env_float("FOODAI_MMR_CATEGORY_PENALTY", 0.06)
    )


@dataclass(frozen=True)
class PricingSettings:
    """Numeric price estimates in LKR.

    Additive to the dataset's `price_range` column, never a replacement: that
    column is a feature of the pickled XGBoost model and an ordinal in the NLU
    layer. See `pricing.py`.
    """

    enabled: bool = field(default_factory=lambda: _env_bool("FOODAI_PRICING_ENABLED", True))
    # Optional CSV override: name,low,typical,high,unit,confidence.
    table_path: str = field(default_factory=lambda: _env_str("FOODAI_PRICE_TABLE", ""))
    # Uniform multiplier so the whole table can be re-based without editing 155
    # rows. Bands are still derived from the unadjusted figures, so inflation
    # cannot reshuffle dishes between Low/Medium/High.
    inflation: float = field(default_factory=lambda: _env_float("FOODAI_PRICE_INFLATION", 1.0))
    # Past this age every price is flagged `stale` and the UI badges it. A price
    # that is quietly two years old is worse than no price.
    stale_days: int = field(default_factory=lambda: _env_int("FOODAI_PRICE_STALE_DAYS", 365))
    as_of: str = field(default_factory=lambda: _env_str("FOODAI_PRICE_AS_OF", ""))
    currency: str = field(default_factory=lambda: _env_str("FOODAI_PRICE_CURRENCY", "LKR"))
    symbol: str = field(default_factory=lambda: _env_str("FOODAI_PRICE_SYMBOL", "Rs"))


@dataclass(frozen=True)
class PlacesSettings:
    """Nearby-venue lookup.

    Unlike prices, this stage really is live: `overpass` queries OpenStreetMap at
    request time and needs no API key, which is why it is the default. `google`
    is richer (ratings, opening hours) but needs a key and is billed.

    The key is read here, server-side, and never sent to the browser. A key in a
    Vite `VITE_*` variable would be inlined into the published bundle.
    """

    enabled: bool = field(default_factory=lambda: _env_bool("FOODAI_PLACES_ENABLED", True))
    # 'overpass' | 'google' | 'static' | 'none'
    provider: str = field(default_factory=lambda: _env_str("FOODAI_PLACES_PROVIDER", "overpass"))
    overpass_url: str = field(
        default_factory=lambda: _env_str(
            "FOODAI_OVERPASS_URL", "https://overpass-api.de/api/interpreter"
        )
    )
    google_api_key: str = field(default_factory=lambda: _env_str("FOODAI_GOOGLE_PLACES_KEY", ""))
    google_url: str = field(
        default_factory=lambda: _env_str(
            "FOODAI_GOOGLE_PLACES_URL", "https://places.googleapis.com/v1/places:searchNearby"
        )
    )
    # A slow external API must not hold a request open indefinitely; on timeout
    # the endpoint degrades to the bundled seed list instead of erroring.
    timeout_seconds: float = field(default_factory=lambda: _env_float("FOODAI_PLACES_TIMEOUT", 8.0))
    default_radius_km: float = field(
        default_factory=lambda: _env_float("FOODAI_PLACES_RADIUS_KM", 3.0)
    )
    max_radius_km: float = field(
        default_factory=lambda: _env_float("FOODAI_PLACES_MAX_RADIUS_KM", 25.0)
    )
    max_results: int = field(default_factory=lambda: _env_int("FOODAI_PLACES_MAX_RESULTS", 12))
    # Responses are cached on coarsened coordinates, which cuts external calls
    # and means two users on the same street share one upstream request.
    cache_ttl_seconds: int = field(default_factory=lambda: _env_int("FOODAI_PLACES_CACHE_TTL", 900))
    cache_size: int = field(default_factory=lambda: _env_int("FOODAI_PLACES_CACHE_SIZE", 256))
    # Decimal places retained on incoming coordinates. 3 dp is roughly 110 m -
    # enough to find a restaurant, not enough to identify a doorstep.
    coordinate_precision: int = field(
        default_factory=lambda: _env_int("FOODAI_PLACES_COORD_PRECISION", 3)
    )
    # Overpass asks for a contactable User-Agent in its usage policy.
    user_agent: str = field(
        default_factory=lambda: _env_str(
            "FOODAI_PLACES_USER_AGENT", "CeylonFoods/3.1 (+https://example.invalid/ceylon-foods)"
        )
    )
    # Fall back to the bundled seed venues when the live provider fails, rather
    # than returning an empty list that looks like "nothing near you".
    fallback_to_seed: bool = field(
        default_factory=lambda: _env_bool("FOODAI_PLACES_FALLBACK_SEED", True)
    )


@dataclass(frozen=True)
class FeedbackSettings:
    """Ratings and comments from the people using the recommender.

    Stored as JSON Lines in a file rather than in a database, because that is the
    whole of the requirement: append one record, read aggregates back. A file also
    keeps `feedback.py` stdlib-only, which is what lets the tests run with no
    services and no network.

    Nothing identifying is recorded - see the `feedback` module docstring. There
    is no setting to turn that off, deliberately: a switch for "also log the IP"
    is a switch someone eventually flips.
    """

    enabled: bool = field(default_factory=lambda: _env_bool("FOODAI_FEEDBACK_ENABLED", True))
    path: str = field(
        default_factory=lambda: _env_str("FOODAI_FEEDBACK_PATH", str(BASE_DIR / "feedback.jsonl"))
    )
    # Long enough for a paragraph of real detail, short enough that the file
    # cannot be inflated by one submission. The client shows this limit and
    # counts down to it, so the bound is visible before it is enforced.
    max_comment_chars: int = field(
        default_factory=lambda: _env_int("FOODAI_FEEDBACK_MAX_COMMENT", 600)
    )
    # A public unauthenticated append endpoint is a disk-filling primitive. Past
    # this size writes are refused with a clear error instead of continuing until
    # the volume is full and every other feature fails too.
    max_bytes: int = field(default_factory=lambda: _env_int("FOODAI_FEEDBACK_MAX_BYTES", 2_000_000))
    # Window in which an identical (rating, comment) is treated as the same
    # submission rather than a second one. Guards the realistic accident - a
    # double click, or a retry after a timeout that actually succeeded - not
    # deliberate abuse, which needs a rate limiter at the edge.
    duplicate_window_seconds: int = field(
        default_factory=lambda: _env_int("FOODAI_FEEDBACK_DEDUPE_SECONDS", 90)
    )


@dataclass(frozen=True)
class Settings:
    data_path: Path = field(
        default_factory=lambda: Path(
            _env_str("FOODAI_DATA_PATH", str(BASE_DIR / "sri_lankan_food_dataset.csv"))
        )
    )
    model_path: Path = field(
        default_factory=lambda: Path(
            _env_str("FOODAI_MODEL_PATH", str(BASE_DIR / "sri_lankan_food_model.pkl"))
        )
    )
    cache_dir: Path = field(
        default_factory=lambda: Path(_env_str("FOODAI_CACHE_DIR", str(BASE_DIR / ".cache")))
    )
    # Embeddings are cached to disk keyed by (model, corpus) hash so restarts do
    # not re-encode the corpus.
    embedding_cache_enabled: bool = field(
        default_factory=lambda: _env_bool("FOODAI_EMBEDDING_CACHE", True)
    )
    cors_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            o.strip() for o in _env_str("FOODAI_CORS_ORIGINS", "*").split(",") if o.strip()
        )
    )
    search_cache_size: int = field(default_factory=lambda: _env_int("FOODAI_SEARCH_CACHE_SIZE", 512))
    max_top_k: int = field(default_factory=lambda: _env_int("FOODAI_MAX_TOP_K", 50))

    retrieval: RetrievalSettings = field(default_factory=RetrievalSettings)
    fusion: FusionSettings = field(default_factory=FusionSettings)
    rerank: RerankSettings = field(default_factory=RerankSettings)
    scoring: ScoringSettings = field(default_factory=ScoringSettings)
    diversity: DiversitySettings = field(default_factory=DiversitySettings)
    pricing: PricingSettings = field(default_factory=PricingSettings)
    places: PlacesSettings = field(default_factory=PlacesSettings)
    feedback: FeedbackSettings = field(default_factory=FeedbackSettings)

    def as_dict(self) -> dict[str, Any]:
        """Flattened view, used by the /config debug endpoint.

        `places.google_api_key` is redacted: /config is unauthenticated, and a
        debug endpoint is a poor place to leak a billable credential.
        """
        redacted = {"places.google_api_key"}
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if hasattr(value, "__dataclass_fields__"):
                for sub in fields(value):
                    key = f"{f.name}.{sub.name}"
                    if key in redacted:
                        out[key] = "***set***" if getattr(value, sub.name) else ""
                    else:
                        out[key] = getattr(value, sub.name)
            elif isinstance(value, Path):
                out[f.name] = str(value)
            else:
                out[f.name] = value
        return out


settings = Settings()
