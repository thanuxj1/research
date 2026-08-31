"""End-to-end pipeline tests for SearchService.

The bi-encoder and cross-encoder are stubbed, so the whole orchestrator - query
understanding, hard filtering, retrieval, RRF fusion, reranking, additive
scoring, MMR, response assembly - is exercised without the ML stack.

The stubs are deliberately crude (token overlap instead of real embeddings). The
point is to verify *wiring and contracts*: that filters are enforced, that the
reranker's output is actually blended in, that a missing reranker degrades
instead of raising, that the response shape is stable, and that the cache keys
on everything it should.
"""

from __future__ import annotations

import math
import unittest
from pathlib import Path

from app.config import Settings
from app.corpus import load_corpus
from app.search import SearchService

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"


class StubDense:
    """Token-overlap 'embeddings'. Deterministic and dependency-free."""

    def __init__(self, texts, fail: bool = False) -> None:
        self.vectors = [self._vectorize(t) for t in texts]
        self.backend = "stub"
        self.is_ready = not fail
        self.encode_calls = 0

    @staticmethod
    def _vectorize(text: str) -> dict:
        counts: dict[str, float] = {}
        for token in text.lower().split():
            token = "".join(ch for ch in token if ch.isalnum())
            if token:
                counts[token] = counts.get(token, 0.0) + 1.0
        norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
        return {k: v / norm for k, v in counts.items()}

    @staticmethod
    def _cosine(a: dict, b: dict) -> float:
        if len(a) > len(b):
            a, b = b, a
        return sum(value * b.get(key, 0.0) for key, value in a.items())

    def search(self, query: str, top_k: int):
        self.encode_calls += 1
        q = self._vectorize(query)
        scored = [(i, self._cosine(q, v)) for i, v in enumerate(self.vectors)]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored[:top_k]

    def similar_to(self, index: int, top_k: int):
        base = self.vectors[index]
        scored = [
            (i, self._cosine(base, v)) for i, v in enumerate(self.vectors) if i != index
        ]
        scored.sort(key=lambda kv: (-kv[1], kv[0]))
        return scored[:top_k]

    def similarity(self, left: int, right: int) -> float:
        return self._cosine(self.vectors[left], self.vectors[right])

    def stats(self) -> dict:
        return {"model": "stub", "backend": "stub", "documents": len(self.vectors)}


class StubReranker:
    """Scores by shared-token fraction; optionally simulates being unavailable."""

    def __init__(self, available: bool = True, error: str | None = None) -> None:
        self.enabled = available
        self._available = available
        self.load_error = error
        self.calls = 0
        self.last_batch_size = 0

    @property
    def is_available(self) -> bool:
        return self._available

    @property
    def is_loaded(self) -> bool:
        return self._available

    def warmup(self) -> bool:
        return self._available

    def score(self, query: str, documents):
        if not self._available:
            return None
        self.calls += 1
        self.last_batch_size = len(documents)
        q = {t for t in query.lower().split() if t}
        out = []
        for document in documents:
            tokens = {t for t in document.lower().split() if t}
            out.append(len(q & tokens) / (len(q) or 1))
        return out

    def stats(self) -> dict:
        return {"enabled": self.enabled, "available": self._available, "model": "stub"}


def build_service(rerank_available: bool = True, **overrides) -> SearchService:
    corpus = load_corpus(DATA_PATH)
    settings = Settings(**overrides) if overrides else Settings()
    service = SearchService(corpus, settings)
    service.dense = StubDense(corpus.dense_texts)  # type: ignore[assignment]
    service.reranker = StubReranker(available=rerank_available)  # type: ignore[assignment]
    return service


class ServiceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = build_service()

    def names(self, payload) -> list[str]:
        return [r["name"] for r in payload["results"]]


class TestResponseShape(ServiceTestCase):
    def test_top_level_keys(self) -> None:
        payload = self.service.search("mild vegetarian breakfast", top_k=5)
        for key in (
            "query", "results", "total", "candidates_considered",
            "understanding", "filters", "pipeline", "took_ms", "cached",
        ):
            self.assertIn(key, payload)

    def test_result_keys(self) -> None:
        payload = self.service.search("crab", top_k=3)
        self.assertTrue(payload["results"])
        for key in (
            "name", "description", "category", "is_veg", "meal_time",
            "spicy_level", "price_range", "tags", "score", "warnings",
            "health_severity",
        ):
            self.assertIn(key, payload["results"][0])

    def test_response_is_json_serializable(self) -> None:
        import json

        json.dumps(self.service.search("spicy seafood", top_k=5, explain=True))

    def test_respects_top_k(self) -> None:
        self.assertEqual(len(self.service.search("curry", top_k=3)["results"]), 3)
        self.assertEqual(len(self.service.search("curry", top_k=10)["results"]), 10)

    def test_scores_are_descending(self) -> None:
        payload = self.service.search("traditional dessert", top_k=8, diversify=False)
        scores = [r["score"] for r in payload["results"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_explain_adds_signal_breakdown(self) -> None:
        payload = self.service.search("mild vegetarian curry", top_k=3, explain=True)
        explanation = payload["results"][0]["explanation"]
        self.assertIn("signals", explanation)
        self.assertIn("relevance", explanation)
        total = sum(s["contribution"] for s in explanation["signals"])
        self.assertAlmostEqual(total, payload["results"][0]["score"], places=3)

    def test_explain_omitted_by_default(self) -> None:
        payload = self.service.search("curry", top_k=2)
        self.assertNotIn("explanation", payload["results"][0])


class TestConstraintEnforcement(ServiceTestCase):
    def test_vegetarian_query_returns_only_vegetarian(self) -> None:
        payload = self.service.search("vegetarian curry", top_k=10)
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertEqual(result["is_veg"], "True")

    def test_no_seafood_excludes_seafood(self) -> None:
        payload = self.service.search("curry without seafood", top_k=15)
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertNotIn("seafood", result["tags"])

    def test_drinks_query_returns_drinks(self) -> None:
        payload = self.service.search("something cold to drink", top_k=8)
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertEqual(result["category"], "Drinks")

    def test_not_spicy_returns_mild_dishes(self) -> None:
        payload = self.service.search("food that is not spicy", top_k=10)
        for result in payload["results"]:
            self.assertIn(result["spicy_level"], ("None", "Low"))

    def test_filters_are_reported(self) -> None:
        payload = self.service.search("vegetarian food", top_k=5)
        self.assertIn("vegetarian only", payload["filters"]["applied"])
        self.assertEqual(payload["filters"]["removed"], 55)

    def test_impossible_filter_combination_returns_message(self) -> None:
        # Vegetarian, but excluding every plant staple in the corpus.
        payload = self.service.search(
            "vegetarian without coconut without gluten without rice without dairy "
            "without egg without nuts without soy",
            top_k=5,
        )
        if not payload["results"]:
            self.assertIn("message", payload)
            self.assertEqual(payload["total"], 0)

    def test_understanding_is_exposed(self) -> None:
        payload = self.service.search("cheap mild vegetarian breakfast", top_k=5)
        constraints = payload["understanding"]["constraints"]
        self.assertEqual(constraints["diet"], "veg")
        self.assertEqual(constraints["price_ceiling"], 0)
        self.assertEqual(constraints["meal_times"], ["Breakfast"])


class TestLookupQueries(ServiceTestCase):
    def test_exact_name_ranks_first(self) -> None:
        for name in ("Watalappan", "Chicken Kottu", "Kiribath", "Lamprais (Lump Rice)"):
            with self.subTest(dish=name):
                payload = self.service.search(name, top_k=5)
                self.assertEqual(payload["results"][0]["name"], name)

    def test_misspelt_name_still_ranks_first(self) -> None:
        payload = self.service.search("watalapan", top_k=5)
        self.assertEqual(payload["results"][0]["name"], "Watalappan")

    def test_named_dish_is_injected_into_candidates(self) -> None:
        """A dish the user named must reach scoring even when the stub retriever
        ranks it poorly."""
        payload = self.service.search("Kola Kenda", top_k=5)
        self.assertIn("Kola Kenda", self.names(payload))


class TestRerankStage(ServiceTestCase):
    def test_reranker_is_called_with_the_candidate_set(self) -> None:
        service = build_service(rerank_available=True)
        service.search("spicy fish curry", top_k=5)
        self.assertEqual(service.reranker.calls, 1)  # type: ignore[attr-defined]
        self.assertGreater(service.reranker.last_batch_size, 5)  # type: ignore[attr-defined]

    def test_reranking_can_be_disabled_per_request(self) -> None:
        service = build_service(rerank_available=True)
        payload = service.search("spicy fish curry", top_k=5, rerank=False)
        self.assertEqual(service.reranker.calls, 0)  # type: ignore[attr-defined]
        self.assertFalse(payload["pipeline"]["reranked"])
        self.assertIn("cross_encoder_skipped", payload["pipeline"]["stages"])

    def test_unavailable_reranker_degrades_gracefully(self) -> None:
        service = build_service(rerank_available=False)
        payload = service.search("spicy fish curry", top_k=5)
        self.assertTrue(payload["results"])
        self.assertFalse(payload["pipeline"]["reranked"])

    def test_rerank_changes_ordering(self) -> None:
        """Confirms the cross-encoder score is genuinely blended in, rather than
        computed and discarded."""
        with_rerank = build_service(rerank_available=True)
        without = build_service(rerank_available=False)
        query = "sweet coconut dessert with jaggery"
        a = self.names(with_rerank.search(query, top_k=8, diversify=False))
        b = self.names(without.search(query, top_k=8, diversify=False))
        self.assertNotEqual(a, b)

    def test_pipeline_reports_stages(self) -> None:
        payload = self.service.search("curry", top_k=3)
        self.assertIn("query_understanding", payload["pipeline"]["stages"])
        self.assertIn("rrf_fusion", payload["pipeline"]["stages"])
        self.assertIn("additive_scoring", payload["pipeline"]["stages"])


class TestDiversification(ServiceTestCase):
    def test_mmr_spreads_categories(self) -> None:
        query = "traditional sri lankan food"
        diverse = self.service.search(query, top_k=8, diversify=True)
        focused = self.service.search(query, top_k=8, diversify=False)
        diverse_categories = {r["category"] for r in diverse["results"]}
        focused_categories = {r["category"] for r in focused["results"]}
        self.assertGreaterEqual(len(diverse_categories), len(focused_categories))

    def test_diversify_preserves_result_count(self) -> None:
        payload = self.service.search("kottu", top_k=6, diversify=True)
        self.assertEqual(len(payload["results"]), 6)

    def test_no_duplicate_results(self) -> None:
        names = self.names(self.service.search("rice and curry", top_k=12))
        self.assertEqual(len(names), len(set(names)))


class TestHealthIntegration(ServiceTestCase):
    def test_warnings_are_attached(self) -> None:
        payload = self.service.search(
            "crab curry", top_k=3, health_conditions=["seafood_allergy"]
        )
        top = payload["results"][0]
        self.assertEqual(top["health_severity"], "danger")
        self.assertTrue(top["warnings"])
        self.assertIn("condition_label", top["warnings"][0])

    def test_flagged_dishes_rank_lower(self) -> None:
        query = "seafood curry"
        unfiltered = self.names(self.service.search(query, top_k=10))
        with_profile = self.names(
            self.service.search(query, top_k=10, health_conditions=["seafood_allergy"])
        )
        self.assertNotEqual(unfiltered, with_profile)

    def test_strict_allergens_removes_dishes_entirely(self) -> None:
        payload = self.service.search(
            "seafood curry",
            top_k=10,
            health_conditions=["seafood_allergy"],
            strict_allergens=True,
        )
        for result in payload["results"]:
            self.assertNotIn("seafood", result["tags"])
        self.assertTrue(payload["filters"]["applied"])

    def test_no_profile_means_no_warnings(self) -> None:
        payload = self.service.search("crab curry", top_k=3)
        self.assertEqual(payload["results"][0]["warnings"], [])
        self.assertIsNone(payload["results"][0]["health_severity"])


class TestCaching(ServiceTestCase):
    def test_repeat_query_is_served_from_cache(self) -> None:
        service = build_service()
        first = service.search("mild curry", top_k=5)
        second = service.search("mild curry", top_k=5)
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(
            [r["name"] for r in first["results"]], [r["name"] for r in second["results"]]
        )

    def test_cache_key_includes_options(self) -> None:
        """Different options must not collide on one cache entry."""
        service = build_service()
        service.search("mild curry", top_k=5)
        for kwargs in (
            {"top_k": 6},
            {"top_k": 5, "explain": True},
            {"top_k": 5, "diversify": False},
            {"top_k": 5, "health_conditions": ["diabetes"]},
            {"top_k": 5, "strict_allergens": True},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertFalse(service.search("mild curry", **kwargs)["cached"])

    def test_cache_is_case_insensitive(self) -> None:
        service = build_service()
        service.search("Mild Curry", top_k=5)
        self.assertTrue(service.search("mild curry", top_k=5)["cached"])

    def test_cache_eviction(self) -> None:
        service = build_service(search_cache_size=2)
        service.search("a curry", top_k=3)
        service.search("b dessert", top_k=3)
        service.search("c drink", top_k=3)
        self.assertLessEqual(len(service._cache), 2)

    def test_clear_cache(self) -> None:
        service = build_service()
        service.search("mild curry", top_k=5)
        service.clear_cache()
        self.assertFalse(service.search("mild curry", top_k=5)["cached"])


class TestAutocomplete(ServiceTestCase):
    def test_prefix_suggestions(self) -> None:
        suggestions = self.service.autocomplete("chick", limit=5)
        self.assertTrue(suggestions)
        self.assertTrue(any(s["name"].startswith("Chicken") for s in suggestions))

    def test_suggestion_shape(self) -> None:
        suggestion = self.service.autocomplete("watal", limit=1)[0]
        for key in ("name", "category", "spicy_level", "is_veg", "score"):
            self.assertIn(key, suggestion)

    def test_typo_fallback(self) -> None:
        self.assertTrue(self.service.autocomplete("kotu", limit=5))

    def test_blank_input(self) -> None:
        self.assertEqual(self.service.autocomplete("   ", limit=5), [])

    def test_respects_limit(self) -> None:
        self.assertLessEqual(len(self.service.autocomplete("a", limit=3)), 3)


class TestSimilar(ServiceTestCase):
    def test_returns_neighbours_excluding_self(self) -> None:
        payload = self.service.similar("Chicken Kottu", top_k=5)
        self.assertEqual(payload["source"]["name"], "Chicken Kottu")
        self.assertEqual(len(payload["results"]), 5)
        self.assertNotIn("Chicken Kottu", [r["name"] for r in payload["results"]])

    def test_unknown_dish_raises_keyerror(self) -> None:
        with self.assertRaises(KeyError):
            self.service.similar("Pizza Margherita", top_k=3)

    def test_case_insensitive_lookup(self) -> None:
        payload = self.service.similar("chicken kottu", top_k=3)
        self.assertEqual(payload["source"]["name"], "Chicken Kottu")

    def test_warnings_attached(self) -> None:
        payload = self.service.similar("Crab Curry", top_k=5, health_conditions=["seafood_allergy"])
        self.assertTrue(any(r["warnings"] for r in payload["results"]))


class TestDegradedMode(unittest.TestCase):
    def test_search_works_without_dense_retrieval(self) -> None:
        """No embedding model: BM25 + fuzzy must still serve results."""
        corpus = load_corpus(DATA_PATH)
        service = SearchService(corpus, Settings())
        service.dense = StubDense(corpus.dense_texts, fail=True)  # type: ignore[assignment]
        service.reranker = StubReranker(available=False)  # type: ignore[assignment]

        payload = service.search("watalappan", top_k=5)
        self.assertTrue(payload["results"])
        self.assertEqual(payload["results"][0]["name"], "Watalappan")
        self.assertEqual(service.mode, "lexical only")

    def test_constraints_still_enforced_without_dense(self) -> None:
        corpus = load_corpus(DATA_PATH)
        service = SearchService(corpus, Settings())
        service.dense = StubDense(corpus.dense_texts, fail=True)  # type: ignore[assignment]
        service.reranker = StubReranker(available=False)  # type: ignore[assignment]
        payload = service.search("vegetarian curry", top_k=8)
        self.assertTrue(payload["results"])
        for result in payload["results"]:
            self.assertEqual(result["is_veg"], "True")

    def test_stats_reports_mode(self) -> None:
        service = build_service(rerank_available=True)
        self.assertIn("mode", service.stats())
        self.assertIn("documents", service.stats())


if __name__ == "__main__":
    unittest.main(verbosity=2)
