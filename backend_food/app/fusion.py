"""Rank fusion, score normalisation and MMR diversification.

Stdlib only, so the ranking maths is unit-testable without the ML stack.

Why Reciprocal Rank Fusion instead of the original weighted score sum:

The previous implementation computed `0.65 * dense + 0.35 * bm25_norm` over the
union of both candidate sets, reading dense scores from a dict built only from
the dense top-40:

    fused = alpha * sem_map.get(i, 0.0) + (1 - alpha) * bm25_norm[i]

Any document found by BM25 but outside the dense top-40 therefore contributed
`0.0` for 65% of its score. A perfect lexical match could not outrank a mediocre
semantic one. It also normalised BM25 by dividing by the batch maximum, which
makes scores depend on the rest of the result set rather than on the query.

RRF sidesteps both problems: it consumes only *ranks*, so the two retrievers'
incomparable score scales never have to be reconciled, and a document missing
from one list simply receives no contribution from it instead of a zero that
drags a weighted mean down.
"""

from __future__ import annotations

from typing import Callable, Hashable, Iterable, Mapping, Sequence, TypeVar

T = TypeVar("T", bound=Hashable)


def reciprocal_rank_fusion(
    ranked_lists: Mapping[str, Sequence[T]],
    weights: Mapping[str, float] | None = None,
    k: int = 60,
) -> dict[T, float]:
    """Weighted RRF: score(d) = sum_r weight_r / (k + rank_r(d)).

    `ranked_lists` maps a retriever name to its results in descending relevance.
    Ranks are 1-based. Documents absent from a list contribute nothing from it.
    """
    if k <= 0:
        raise ValueError("k must be positive")
    scores: dict[T, float] = {}
    for source, ranking in ranked_lists.items():
        weight = 1.0 if weights is None else weights.get(source, 1.0)
        if weight == 0.0:
            continue
        for position, doc in enumerate(ranking, start=1):
            scores[doc] = scores.get(doc, 0.0) + weight / (k + position)
    return scores


def minmax_normalize(scores: Mapping[T, float]) -> dict[T, float]:
    """Rescale to [0, 1]. A degenerate (all-equal) input maps to all 1.0."""
    if not scores:
        return {}
    values = list(scores.values())
    lo, hi = min(values), max(values)
    if hi - lo <= 1e-12:
        return {key: 1.0 for key in scores}
    span = hi - lo
    return {key: (value - lo) / span for key, value in scores.items()}


def top_n(scores: Mapping[T, float], n: int) -> list[T]:
    """Highest-scoring n keys. Ties break deterministically on the key."""
    return [
        key
        for key, _ in sorted(scores.items(), key=lambda kv: (-kv[1], _tiebreak(kv[0])))[:n]
    ]


def _tiebreak(key: object) -> tuple[int, str]:
    """Stable, type-agnostic secondary sort key."""
    if isinstance(key, int):
        return (0, f"{key:012d}")
    return (1, str(key))


def mmr_select(
    candidates: Sequence[T],
    relevance: Mapping[T, float],
    similarity: Callable[[T, T], float],
    k: int,
    lambda_: float = 0.8,
    group_of: Callable[[T], object] | None = None,
    group_penalty: float = 0.0,
) -> list[T]:
    """Maximal Marginal Relevance selection (Carbonell & Goldstein, 1998).

    Greedily picks the candidate maximising

        lambda * relevance(d)
          - (1 - lambda) * max_{s in selected} similarity(d, s)
          - group_penalty * (number of already-selected items sharing d's group)

    The group term is a domain addition: embedding similarity alone still happily
    returns six kottu variants, because they genuinely are all relevant and only
    moderately similar in vector space. Penalising category repeats makes the
    first page span the menu.

    `lambda_ >= 1.0` short-circuits to pure relevance ordering.
    """
    if k <= 0 or not candidates:
        return []
    if not 0.0 <= lambda_ <= 1.0:
        raise ValueError("lambda_ must be in [0, 1]")

    pool = list(candidates)
    if lambda_ >= 1.0 and group_penalty == 0.0:
        return sorted(pool, key=lambda d: (-relevance.get(d, 0.0), _tiebreak(d)))[:k]

    selected: list[T] = []
    group_counts: dict[object, int] = {}

    while pool and len(selected) < k:
        best: T | None = None
        best_score = float("-inf")
        for candidate in pool:
            score = lambda_ * relevance.get(candidate, 0.0)
            if selected:
                redundancy = max(similarity(candidate, chosen) for chosen in selected)
                score -= (1.0 - lambda_) * redundancy
            if group_of is not None and group_penalty:
                score -= group_penalty * group_counts.get(group_of(candidate), 0)
            # Deterministic tie-breaking: first candidate wins, and `pool`
            # preserves the caller's (relevance-sorted) order.
            if score > best_score:
                best_score = score
                best = candidate
        if best is None:
            break
        selected.append(best)
        pool.remove(best)
        if group_of is not None:
            group = group_of(best)
            group_counts[group] = group_counts.get(group, 0) + 1

    return selected


def rank_of(ranking: Sequence[T]) -> dict[T, int]:
    """Map document -> 1-based rank."""
    return {doc: position for position, doc in enumerate(ranking, start=1)}


def dedupe_preserving_order(items: Iterable[T]) -> list[T]:
    seen: set[T] = set()
    out: list[T] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
