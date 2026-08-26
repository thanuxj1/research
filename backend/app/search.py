"""The search pipeline orchestrator.

Stages, in order:

  0. Query understanding      nlu.QueryAnalyzer
  1. Hard constraint filter   ranking.allowed_indices
  2. Candidate generation     dense (bi-encoder) + BM25 + fuzzy names
  3. Rank fusion              Reciprocal Rank Fusion
  4. Cross-encoder rerank     optional, degrades gracefully
  5. Additive signal scoring  ranking.score_dish
  6. MMR diversification      fusion.mmr_select
  7. Response assembly        including the explanation payload

Stages 0, 1, 3, 5 and 6 are pure-Python and covered by the unit tests. Stages 2
and 4 wrap the ML models.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Sequence

from . import health
from .config import Settings
from .corpus import Corpus, Dish
from .dense import DenseRetriever
from .fusion import minmax_normalize, mmr_select, reciprocal_rank_fusion, top_n
from .lexical import BM25Index, FuzzyNameIndex
from .nlu import AnalyzedQuery, QueryAnalyzer
from .ranking import ScoredDish, allowed_indices, score_dish
from .reranker import CrossEncoderReranker

log = logging.getLogger(__name__)


class SearchService:
    def __init__(
        self,
        corpus: Corpus,
        settings: Settings,
        price_book: object | None = None,
    ) -> None:
        self.corpus = corpus
        self.settings = settings
        # Optional and duck-typed (`.get(name) -> Price | None`) so the pipeline
        # runs unchanged with pricing disabled, and so the existing service tests
        # can keep constructing SearchService(corpus, settings).
        self.price_book = price_book

        self.analyzer = QueryAnalyzer(
            dish_names=corpus.names,
            extra_vocabulary=corpus.vocabulary_texts(),
            fuzzy_threshold=settings.retrieval.fuzzy_threshold,
        )
        self.bm25 = BM25Index(corpus.sparse_corpus)
        self.fuzzy = FuzzyNameIndex(corpus.names)
        self.dense = DenseRetriever(
            model_name=settings.retrieval.embedding_model,
            query_instruction=settings.retrieval.query_instruction,
            cache_dir=settings.cache_dir,
            cache_enabled=settings.embedding_cache_enabled,
        )
        self.reranker = CrossEncoderReranker(
            model_name=settings.rerank.model,
            batch_size=settings.rerank.batch_size,
            enabled=settings.rerank.enabled,
        )
        self._cache: "OrderedDict[tuple, dict]" = OrderedDict()
        # Set by build() if the embedding model could not be loaded.
        self.dense_error: str | None = None

    # -- lifecycle ---------------------------------------------------------
    def build(self) -> None:
        """Build the dense index and warm the reranker.

        Neither is fatal. BM25 and the fuzzy name index are pure Python and always
        available, so a missing or broken ML stack degrades search quality instead
        of taking the API down. `GET /health` reports which stages are live.
        """
        try:
            self.dense.build(self.corpus.dense_texts)
        except Exception as exc:
            self.dense_error = f"{type(exc).__name__}: {exc}"
            log.error(
                "Dense retrieval unavailable (%s). Serving lexical-only results.",
                self.dense_error,
            )
        if self.settings.rerank.enabled:
            self.reranker.warmup()

    @property
    def is_ready(self) -> bool:
        """True once the corpus is queryable at all - lexical retrieval suffices."""
        return len(self.corpus) > 0

    @property
    def mode(self) -> str:
        if self.dense.is_ready and self.reranker.is_available:
            return "hybrid + cross-encoder"
        if self.dense.is_ready:
            return "hybrid (no reranker)"
        return "lexical only"

    def stats(self) -> dict[str, object]:
        return {
            "documents": len(self.corpus),
            "mode": self.mode,
            "dense": {**self.dense.stats(), "error": self.dense_error},
            "reranker": self.reranker.stats(),
            "sparse": {
                "algorithm": "BM25 Okapi (in-process inverted index)",
                "terms": len(self.bm25.postings),
                "avg_doc_length": round(self.bm25.avg_doc_length, 2),
            },
            "cache_entries": len(self._cache),
            "pricing": None if self.price_book is None else self.price_book.stats(),
        }

    # -- search ------------------------------------------------------------
    def search(
        self,
        query: str,
        top_k: int = 8,
        health_conditions: Sequence[str] = (),
        strict_allergens: bool = False,
        explain: bool = False,
        rerank: bool = True,
        diversify: bool = True,
    ) -> dict:
        cache_key = (
            query.strip().lower(),
            top_k,
            tuple(sorted(health_conditions)),
            strict_allergens,
            explain,
            rerank,
            diversify,
        )
        cached = self._cache.get(cache_key)
        if cached is not None:
            self._cache.move_to_end(cache_key)
            return {**cached, "cached": True}

        started = time.perf_counter()
        analyzed = self.analyzer.analyze(query)

        # Stage 1: hard filters.
        strict_tags = (
            health.allergen_tags_for(health_conditions) if strict_allergens else set()
        )
        survivors, filter_report = allowed_indices(
            self.corpus.dishes, analyzed.constraints, sorted(strict_tags)
        )

        if not survivors:
            payload = self._empty_response(analyzed, filter_report, started, explain)
            self._remember(cache_key, payload)
            return payload

        # Stages 2-3: retrieve and fuse.
        candidates, fused, retriever_scores, retriever_sources = self._retrieve(
            analyzed, survivors
        )

        # Stages 4-5: rerank and score.
        scored = self._score(
            analyzed=analyzed,
            candidates=candidates,
            fused=fused,
            retriever_scores=retriever_scores,
            retriever_sources=retriever_sources,
            health_conditions=health_conditions,
            rerank=rerank,
        )

        # Stage 6: diversify, then cut to top_k.
        ordered = self._finalize(scored, top_k, diversify)

        payload = {
            "query": analyzed.raw,
            "results": [
                item.as_dict(
                    include_explanation=explain, price=self._price_for(item.dish)
                )
                for item in ordered
            ],
            "total": len(ordered),
            "candidates_considered": len(candidates),
            "understanding": analyzed.as_dict(),
            "filters": filter_report.as_dict(),
            "pipeline": self._pipeline_report(rerank, diversify),
            "took_ms": round((time.perf_counter() - started) * 1000, 2),
            "cached": False,
        }
        self._remember(cache_key, payload)
        return payload

    # -- stages ------------------------------------------------------------
    def _retrieve(
        self, analyzed: AnalyzedQuery, survivors: set[int]
    ) -> tuple[list[int], dict[int, float], dict[str, dict[int, float]], dict[int, set[str]]]:
        """Union of dense, sparse and fuzzy candidates, fused with RRF.

        Retrieval runs over the full corpus and the hard-filter set is applied to
        the results, rather than the reverse. Filtering the *index* per request
        would mean rebuilding it per request; at 155 documents post-filtering is
        both simpler and cheaper.
        """
        retrieval = self.settings.retrieval
        fusion_cfg = self.settings.fusion

        rankings: dict[str, list[int]] = {}
        raw_scores: dict[str, dict[int, float]] = {}

        # Over-fetch, because post-filtering will discard some of what we pull.
        overfetch = 2 if survivors and len(survivors) < len(self.corpus) else 1

        if self.dense.is_ready:
            dense_hits = self.dense.search(
                analyzed.dense_query, retrieval.dense_top_k * overfetch
            )
            dense_kept = [(i, s) for i, s in dense_hits if i in survivors]
            rankings["dense"] = [i for i, _ in dense_kept][: retrieval.dense_top_k]
            raw_scores["dense"] = dict(dense_kept)

        if analyzed.sparse_tokens:
            sparse_hits = self.bm25.search(
                analyzed.sparse_tokens, retrieval.sparse_top_k * overfetch
            )
            sparse_kept = [(i, s) for i, s in sparse_hits if i in survivors]
            rankings["sparse"] = [i for i, _ in sparse_kept][: retrieval.sparse_top_k]
            raw_scores["sparse"] = dict(sparse_kept)

        fuzzy_hits = self.fuzzy.search(
            analyzed.corrected or analyzed.normalized,
            retrieval.fuzzy_top_k,
            threshold=retrieval.fuzzy_threshold,
        )
        fuzzy_kept = [(h.index, h.score) for h in fuzzy_hits if h.index in survivors]
        if fuzzy_kept:
            rankings["fuzzy"] = [i for i, _ in fuzzy_kept]
            raw_scores["fuzzy"] = dict(fuzzy_kept)

        fused = reciprocal_rank_fusion(
            rankings,
            weights={
                "dense": fusion_cfg.dense_weight,
                "sparse": fusion_cfg.sparse_weight,
                "fuzzy": fusion_cfg.fuzzy_weight,
            },
            k=fusion_cfg.rrf_k,
        )

        # A dish the user named explicitly must reach the reranker even if
        # neither retriever surfaced it.
        for match in analyzed.name_matches:
            dish = self.corpus.get(match.name)
            if dish is not None and dish.index in survivors:
                fused.setdefault(dish.index, 0.0)

        candidates = top_n(fused, self.settings.fusion.rerank_candidates)

        # Guarantee enough candidates to fill a page: with heavy filtering the
        # retrievers can return very few, and a purely constraint-driven query
        # ("vegetarian") may match no distinctive text at all.
        if len(candidates) < self.settings.fusion.rerank_candidates:
            existing = set(candidates)
            for index in sorted(survivors):
                if index not in existing:
                    candidates.append(index)
                    if len(candidates) >= self.settings.fusion.rerank_candidates:
                        break

        sources: dict[int, set[str]] = {}
        for source, ranking in rankings.items():
            for index in ranking:
                sources.setdefault(index, set()).add(source)

        # Returned rather than stashed on `self`: FastAPI dispatches sync handlers
        # onto a threadpool, so per-request state on the service would race
        # between concurrent searches.
        return candidates, fused, raw_scores, sources

    def _score(
        self,
        analyzed: AnalyzedQuery,
        candidates: Sequence[int],
        fused: dict[int, float],
        retriever_scores: dict[str, dict[int, float]],
        retriever_sources: dict[int, set[str]],
        health_conditions: Sequence[str],
        rerank: bool,
    ) -> list[ScoredDish]:
        if not candidates:
            return []

        base = minmax_normalize({i: fused.get(i, 0.0) for i in candidates})

        rerank_scores: list[float] | None = None
        if rerank and self.reranker.is_available:
            documents = [self.corpus[i].dense_text for i in candidates]
            rerank_scores = self.reranker.score(analyzed.corrected or analyzed.raw, documents)

        name_kinds = {
            self.corpus.get(m.name).index: m.kind  # type: ignore[union-attr]
            for m in analyzed.name_matches
            if self.corpus.get(m.name) is not None
        }

        weight = self.settings.rerank.weight
        scored: list[ScoredDish] = []

        for position, index in enumerate(candidates):
            dish: Dish = self.corpus[index]
            first_stage = base.get(index, 0.0)

            if rerank_scores is not None:
                cross = rerank_scores[position]
                relevance = weight * cross + (1.0 - weight) * first_stage
            else:
                cross = None
                relevance = first_stage

            warnings = health.evaluate(dish.tags, dish.spicy_level, list(health_conditions))
            total, signals, severity = score_dish(
                dish=dish,
                relevance=relevance,
                constraints=analyzed.constraints,
                settings=self.settings.scoring,
                name_match_kind=name_kinds.get(index),
                warnings=warnings,
                price_book=self.price_book,
            )

            scored.append(
                ScoredDish(
                    dish=dish,
                    score=total,
                    relevance=relevance,
                    signals=signals,
                    warnings=warnings,
                    health_severity=severity,
                    rerank_score=cross,
                    dense_score=retriever_scores.get("dense", {}).get(index),
                    sparse_score=retriever_scores.get("sparse", {}).get(index),
                    retrievers=tuple(sorted(retriever_sources.get(index, set()))),
                )
            )

        scored.sort(key=lambda item: (-item.score, item.dish.name))
        return scored

    def _finalize(
        self, scored: Sequence[ScoredDish], top_k: int, diversify: bool
    ) -> list[ScoredDish]:
        if not scored:
            return []
        diversity = self.settings.diversity
        if not (diversify and diversity.enabled) or len(scored) <= 1:
            return list(scored[:top_k])

        by_index = {item.dish.index: item for item in scored}
        relevance = {item.dish.index: item.score for item in scored}
        order = [item.dish.index for item in scored]

        selected = mmr_select(
            candidates=order,
            relevance=relevance,
            similarity=self.dense.similarity if self.dense.is_ready else (lambda a, b: 0.0),
            k=top_k,
            lambda_=diversity.lambda_,
            group_of=lambda index: by_index[index].dish.category,
            group_penalty=diversity.category_repeat_penalty,
        )
        return [by_index[index] for index in selected]

    # -- other endpoints ---------------------------------------------------
    def autocomplete(self, prefix: str, limit: int = 8) -> list[dict[str, object]]:
        """Typeahead over dish names, with a fuzzy fallback for typos."""
        cleaned = prefix.strip()
        if not cleaned:
            return []
        hits = self.fuzzy.prefix_search(cleaned, limit)
        if len(hits) < limit:
            seen = {h.index for h in hits}
            for hit in self.fuzzy.search(cleaned, limit, threshold=0.7):
                if hit.index not in seen:
                    hits.append(hit)
                    if len(hits) >= limit:
                        break
        out: list[dict[str, object]] = []
        for hit in hits[:limit]:
            dish = self.corpus[hit.index]
            out.append(
                {
                    "name": dish.name,
                    "category": dish.category,
                    "spicy_level": dish.spicy_level,
                    "is_veg": "True" if dish.is_veg else "False",
                    "score": round(hit.score, 3),
                }
            )
        return out

    def similar(
        self,
        name: str,
        top_k: int = 6,
        health_conditions: Sequence[str] = (),
    ) -> dict:
        """More-like-this over the dense index."""
        dish = self.corpus.get(name)
        if dish is None:
            raise KeyError(name)
        if not self.dense.is_ready:
            raise RuntimeError("dense index is not built")

        results = []
        for index, similarity in self.dense.similar_to(dish.index, top_k):
            neighbour = self.corpus[index]
            warnings = health.evaluate(
                neighbour.tags, neighbour.spicy_level, list(health_conditions)
            )
            payload = neighbour.public_dict(self._price_for(neighbour))
            payload["score"] = round(float(similarity), 4)
            payload["warnings"] = [w.as_dict() for w in warnings]
            payload["health_severity"] = health.worst_severity(warnings)
            results.append(payload)

        return {
            "source": dish.public_dict(self._price_for(dish)),
            "results": results,
            "total": len(results),
        }

    # -- helpers -----------------------------------------------------------
    def _price_for(self, dish: Dish) -> object | None:
        """This dish's price, or None when pricing is off or the table is partial."""
        if self.price_book is None:
            return None
        return self.price_book.get(dish.name)

    def _pipeline_report(self, rerank: bool, diversify: bool) -> dict[str, object]:
        reranked = rerank and self.reranker.is_available
        return {
            "stages": [
                "query_understanding",
                "hard_filters",
                "hybrid_retrieval",
                "rrf_fusion",
                "cross_encoder_rerank" if reranked else "cross_encoder_skipped",
                "additive_scoring",
                "mmr_diversification" if (diversify and self.settings.diversity.enabled) else "mmr_skipped",
            ],
            "reranked": reranked,
            "rerank_unavailable_reason": None if reranked else self.reranker.load_error,
            "dense_backend": self.dense.backend,
        }

    def _empty_response(
        self, analyzed: AnalyzedQuery, filter_report, started: float, explain: bool
    ) -> dict:
        return {
            "query": analyzed.raw,
            "results": [],
            "total": 0,
            "candidates_considered": 0,
            "understanding": analyzed.as_dict(),
            "filters": filter_report.as_dict(),
            "pipeline": self._pipeline_report(False, False),
            "took_ms": round((time.perf_counter() - started) * 1000, 2),
            "cached": False,
            "message": "Every dish was excluded by your filters. Try relaxing them.",
        }

    def _remember(self, key: tuple, payload: dict) -> None:
        limit = self.settings.search_cache_size
        if limit <= 0:
            return
        self._cache[key] = payload
        self._cache.move_to_end(key)
        while len(self._cache) > limit:
            self._cache.popitem(last=False)

    def clear_cache(self) -> None:
        self._cache.clear()
