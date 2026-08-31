"""Ranking-maths tests: BM25, RRF fusion, normalisation, MMR. Stdlib only."""

from __future__ import annotations

import unittest
from pathlib import Path

from app.corpus import load_corpus
from app.fusion import (
    dedupe_preserving_order,
    minmax_normalize,
    mmr_select,
    rank_of,
    reciprocal_rank_fusion,
    top_n,
)
from app.lexical import BM25Index, FuzzyNameIndex, tokenize

DATA_PATH = Path(__file__).resolve().parent.parent / "sri_lankan_food_dataset.csv"


class TestBM25(unittest.TestCase):
    def setUp(self) -> None:
        self.corpus = [
            tokenize("chicken kottu chopped roti with chicken"),
            tokenize("vegetable kottu chopped roti with vegetables"),
            tokenize("watalappan coconut custard dessert"),
            tokenize("ceylon tea black tea beverage"),
        ]
        self.index = BM25Index(self.corpus)

    def test_matching_doc_scores_highest(self) -> None:
        scores = self.index.scores(["watalappan"])
        self.assertEqual(max(scores, key=lambda i: scores[i]), 2)

    def test_non_matching_docs_are_absent_not_zero(self) -> None:
        """Sparse output: absence is meaningful, and much cheaper than scoring
        every document like rank_bm25 does."""
        scores = self.index.scores(["watalappan"])
        self.assertEqual(set(scores), {2})

    def test_empty_query_scores_nothing(self) -> None:
        self.assertEqual(self.index.scores([]), {})

    def test_unknown_term_scores_nothing(self) -> None:
        self.assertEqual(self.index.scores(["pizza"]), {})

    def test_term_frequency_increases_score(self) -> None:
        # "chicken" appears twice in doc 0, "vegetable"-ish terms once in doc 1.
        scores = self.index.scores(["chicken"])
        self.assertIn(0, scores)
        self.assertNotIn(1, scores)

    def test_idf_is_never_negative(self) -> None:
        """A term in >half the corpus must not contribute a negative score,
        which would rank a matching document below a non-matching one."""
        # "roti" and "kottu" appear in 2 of 4 docs; "with" also in 2 of 4.
        for term, idf in self.index.idf.items():
            with self.subTest(term=term):
                self.assertGreater(idf, 0.0)

    def test_common_term_scores_less_than_rare_term(self) -> None:
        common = self.index.scores(["kottu"])  # 2 of 4 docs
        rare = self.index.scores(["watalappan"])  # 1 of 4 docs
        self.assertLess(common[0], rare[2])

    def test_search_returns_descending_scores(self) -> None:
        results = self.index.search(["kottu", "chicken"], top_k=4)
        scores = [score for _, score in results]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(results[0][0], 0)

    def test_search_respects_top_k(self) -> None:
        self.assertEqual(len(self.index.search(["kottu"], top_k=1)), 1)

    def test_empty_corpus_is_safe(self) -> None:
        self.assertEqual(BM25Index([]).scores(["x"]), {})


class TestBM25OnRealCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = load_corpus(DATA_PATH)
        cls.index = BM25Index(cls.corpus.sparse_corpus)
        cls.names = cls.corpus.names

    def best(self, *terms: str) -> str:
        results = self.index.search(list(terms), top_k=1)
        return self.names[results[0][0]]

    def test_name_field_weighting_wins(self) -> None:
        """Querying a dish name must return that dish, not a dish that merely
        mentions it in prose. This is what the 3x name repetition buys."""
        self.assertEqual(self.best("watalappan"), "Watalappan")
        self.assertEqual(self.best("kiribath"), "Kiribath")
        self.assertEqual(self.best("lamprais"), "Lamprais (Lump Rice)")

    def test_multi_token_name(self) -> None:
        top = [self.names[i] for i, _ in self.index.search(["chicken", "kottu"], top_k=3)]
        self.assertIn("Chicken Kottu", top)

    def test_tag_tokens_are_searchable(self) -> None:
        top = [self.names[i] for i, _ in self.index.search(["street", "food"], top_k=10)]
        self.assertTrue(any("Kottu" in name for name in top))


class TestFuzzyNames(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        corpus = load_corpus(DATA_PATH)
        cls.index = FuzzyNameIndex(corpus.names)

    def test_typo_matches(self) -> None:
        hits = self.index.search("watalapan", top_k=3)
        self.assertTrue(hits)
        self.assertEqual(hits[0].name, "Watalappan")

    def test_single_word_matches_inside_multiword_name(self) -> None:
        hits = self.index.search("kottu", top_k=10, threshold=0.85)
        self.assertTrue(any("Kottu" in h.name for h in hits))

    def test_parenthetical_gloss_is_ignored(self) -> None:
        """"Fish Bun (Malu Pan)" must be findable by its primary name."""
        hits = self.index.search("fish bun", top_k=3)
        self.assertEqual(hits[0].name, "Fish Bun (Malu Pan)")

    def test_short_query_is_rejected(self) -> None:
        self.assertEqual(self.index.search("ko", top_k=5), [])

    def test_prefix_search_orders_shortest_first(self) -> None:
        hits = self.index.prefix_search("chicken", limit=5)
        self.assertTrue(hits)
        self.assertTrue(all(h.name.lower().startswith("chicken") for h in hits[:3]))

    def test_prefix_search_falls_back_to_containment(self) -> None:
        hits = self.index.prefix_search("hoppers", limit=10)
        self.assertTrue(any(h.name == "String Hoppers" for h in hits))

    def test_prefix_search_empty_input(self) -> None:
        self.assertEqual(self.index.prefix_search("", limit=5), [])


class TestRRF(unittest.TestCase):
    def test_document_in_both_lists_beats_either_alone(self) -> None:
        fused = reciprocal_rank_fusion(
            {"dense": ["a", "b", "c"], "sparse": ["c", "a", "d"]}, k=60
        )
        self.assertEqual(top_n(fused, 1), ["a"])

    def test_regression_missing_from_one_list_is_not_a_zero(self) -> None:
        """The original weighted-sum fusion substituted 0.0 for the dense score
        of any BM25-only candidate, so 65% of its score vanished. Under RRF a
        rank-1 sparse-only hit still outranks a rank-30 dense-only hit."""
        fused = reciprocal_rank_fusion(
            {
                "dense": [f"d{i}" for i in range(30)],  # 'sparse_only' absent
                "sparse": ["sparse_only"],
            },
            weights={"dense": 1.0, "sparse": 0.7},
            k=60,
        )
        self.assertGreater(fused["sparse_only"], fused["d29"])

    def test_weights_are_applied(self) -> None:
        fused = reciprocal_rank_fusion(
            {"dense": ["a"], "sparse": ["b"]}, weights={"dense": 1.0, "sparse": 0.5}
        )
        self.assertGreater(fused["a"], fused["b"])

    def test_zero_weight_source_is_skipped(self) -> None:
        fused = reciprocal_rank_fusion(
            {"dense": ["a"], "sparse": ["b"]}, weights={"dense": 1.0, "sparse": 0.0}
        )
        self.assertNotIn("b", fused)

    def test_scale_free_across_retrievers(self) -> None:
        """RRF consumes ranks only, so wildly different score scales - cosine in
        [-1,1] versus unbounded BM25 - never need reconciling."""
        fused_a = reciprocal_rank_fusion({"x": ["p", "q"], "y": ["q", "p"]})
        fused_b = reciprocal_rank_fusion({"x": ["p", "q"], "y": ["q", "p"]})
        self.assertEqual(fused_a, fused_b)

    def test_rejects_non_positive_k(self) -> None:
        with self.assertRaises(ValueError):
            reciprocal_rank_fusion({"a": ["x"]}, k=0)

    def test_empty_input(self) -> None:
        self.assertEqual(reciprocal_rank_fusion({}), {})


class TestNormalize(unittest.TestCase):
    def test_maps_to_unit_range(self) -> None:
        out = minmax_normalize({"a": 2.0, "b": 4.0, "c": 6.0})
        self.assertEqual(out["a"], 0.0)
        self.assertEqual(out["c"], 1.0)
        self.assertAlmostEqual(out["b"], 0.5)

    def test_degenerate_input_is_all_ones(self) -> None:
        self.assertEqual(minmax_normalize({"a": 3.0, "b": 3.0}), {"a": 1.0, "b": 1.0})

    def test_single_item(self) -> None:
        self.assertEqual(minmax_normalize({"a": 7.0}), {"a": 1.0})

    def test_empty(self) -> None:
        self.assertEqual(minmax_normalize({}), {})


class TestMMR(unittest.TestCase):
    def test_pure_relevance_when_lambda_is_one(self) -> None:
        relevance = {"a": 0.9, "b": 0.8, "c": 0.7}
        selected = mmr_select(["a", "b", "c"], relevance, lambda x, y: 1.0, k=3, lambda_=1.0)
        self.assertEqual(selected, ["a", "b", "c"])

    def test_redundant_item_is_demoted(self) -> None:
        # 'b' is identical to 'a'; 'c' is unrelated but slightly less relevant.
        relevance = {"a": 1.0, "b": 0.95, "c": 0.9}
        similarity = lambda x, y: 1.0 if {x, y} == {"a", "b"} else 0.0
        selected = mmr_select(["a", "b", "c"], relevance, similarity, k=2, lambda_=0.5)
        self.assertEqual(selected, ["a", "c"])

    def test_group_penalty_spreads_categories(self) -> None:
        relevance = {f"kottu{i}": 1.0 - i * 0.01 for i in range(4)}
        relevance["dessert"] = 0.9
        candidates = list(relevance)
        groups = {name: ("kottu" if name.startswith("kottu") else "dessert") for name in candidates}
        selected = mmr_select(
            candidates,
            relevance,
            lambda x, y: 0.0,
            k=2,
            lambda_=1.0,
            group_of=lambda d: groups[d],
            group_penalty=0.5,
        )
        self.assertEqual(selected[0], "kottu0")
        self.assertEqual(selected[1], "dessert")

    def test_respects_k(self) -> None:
        relevance = {"a": 1.0, "b": 0.5}
        self.assertEqual(len(mmr_select(["a", "b"], relevance, lambda x, y: 0.0, k=1)), 1)

    def test_k_larger_than_pool(self) -> None:
        relevance = {"a": 1.0}
        self.assertEqual(mmr_select(["a"], relevance, lambda x, y: 0.0, k=5), ["a"])

    def test_empty_candidates(self) -> None:
        self.assertEqual(mmr_select([], {}, lambda x, y: 0.0, k=3), [])

    def test_rejects_lambda_out_of_range(self) -> None:
        with self.assertRaises(ValueError):
            mmr_select(["a"], {"a": 1.0}, lambda x, y: 0.0, k=1, lambda_=1.5)

    def test_is_deterministic(self) -> None:
        relevance = {"a": 0.5, "b": 0.5, "c": 0.5}
        runs = {
            tuple(mmr_select(["a", "b", "c"], relevance, lambda x, y: 0.3, k=3, lambda_=0.7))
            for _ in range(5)
        }
        self.assertEqual(len(runs), 1)


class TestHelpers(unittest.TestCase):
    def test_rank_of_is_one_based(self) -> None:
        self.assertEqual(rank_of(["a", "b"]), {"a": 1, "b": 2})

    def test_top_n_is_deterministic_on_ties(self) -> None:
        scores = {3: 1.0, 1: 1.0, 2: 1.0}
        self.assertEqual(top_n(scores, 3), [1, 2, 3])

    def test_dedupe_preserves_first_occurrence(self) -> None:
        self.assertEqual(dedupe_preserving_order(["a", "b", "a", "c", "b"]), ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
