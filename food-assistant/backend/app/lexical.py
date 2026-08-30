"""Sparse retrieval: BM25 (Okapi) plus a fuzzy dish-name matcher.

BM25 is implemented here rather than pulled from `rank-bm25` for three reasons:

1. The corpus is 155 documents. The dependency buys nothing at this scale.
2. `rank_bm25.BM25Okapi.get_scores` scores the *entire* corpus for every query.
   An inverted index touches only documents containing a query term.
3. It makes sparse retrieval unit-testable in an environment without the ML
   stack installed, which is where most ranking regressions actually surface.

The implementation is the standard Okapi BM25 with the non-negative ("plus")
IDF variant, matching Robertson & Zaragoza (2009).
"""

from __future__ import annotations

import difflib
import math
import re
from dataclasses import dataclass
from typing import Iterable, Sequence

_WORD_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class BM25Index:
    """Okapi BM25 over a pre-tokenized corpus.

    Args:
        corpus: one token list per document. Repeated tokens are how callers
            express field weighting (see `corpus.build_sparse_tokens`).
        k1: term-frequency saturation. 1.5 is the usual default.
        b: length normalisation strength. 0.75 is the usual default.
    """

    def __init__(
        self,
        corpus: Sequence[Sequence[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.k1 = k1
        self.b = b
        self.doc_count = len(corpus)
        self.doc_lengths: list[int] = [len(doc) for doc in corpus]
        total = sum(self.doc_lengths)
        self.avg_doc_length = (total / self.doc_count) if self.doc_count else 0.0

        # term -> {doc_index: term_frequency}
        self.postings: dict[str, dict[int, int]] = {}
        for doc_index, tokens in enumerate(corpus):
            counts: dict[str, int] = {}
            for token in tokens:
                counts[token] = counts.get(token, 0) + 1
            for token, frequency in counts.items():
                self.postings.setdefault(token, {})[doc_index] = frequency

        # Precompute IDF. The +1 inside the log keeps IDF strictly positive, so a
        # term appearing in more than half the corpus cannot contribute a
        # negative score and push a matching document below a non-matching one.
        self.idf: dict[str, float] = {}
        for term, posting in self.postings.items():
            df = len(posting)
            self.idf[term] = math.log(1.0 + (self.doc_count - df + 0.5) / (df + 0.5))

    def scores(self, query_tokens: Iterable[str]) -> dict[int, float]:
        """Sparse map of doc_index -> BM25 score. Non-matching docs are absent."""
        out: dict[int, float] = {}
        if not self.doc_count or self.avg_doc_length <= 0:
            return out
        for term in query_tokens:
            posting = self.postings.get(term)
            if not posting:
                continue
            idf = self.idf[term]
            for doc_index, frequency in posting.items():
                length_norm = 1.0 - self.b + self.b * (
                    self.doc_lengths[doc_index] / self.avg_doc_length
                )
                contribution = idf * (frequency * (self.k1 + 1.0)) / (
                    frequency + self.k1 * length_norm
                )
                out[doc_index] = out.get(doc_index, 0.0) + contribution
        return out

    def search(self, query_tokens: Iterable[str], top_k: int) -> list[tuple[int, float]]:
        """Top-k (doc_index, score), descending. Ties break on doc_index."""
        scored = self.scores(query_tokens)
        ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[:top_k]


@dataclass(frozen=True)
class FuzzyHit:
    index: int
    name: str
    score: float


class FuzzyNameIndex:
    """Character-similarity matcher over dish names.

    Covers the gap BM25 leaves: a misspelt query token shares no exact term with
    the index, so "watalapan" or "kotu" scores zero on every document. The NLU
    layer already corrects tokens it recognises; this catches whole-name
    misspellings and prefix/typeahead queries.
    """

    def __init__(self, names: Sequence[str]) -> None:
        self.names = list(names)
        self._normalized = [_normalize_name(name) for name in self.names]

    def search(self, query: str, top_k: int, threshold: float = 0.8) -> list[FuzzyHit]:
        needle = _normalize_name(query)
        if len(needle) < 3:
            return []
        hits: list[FuzzyHit] = []
        for index, candidate in enumerate(self._normalized):
            if not candidate:
                continue
            score = _best_similarity(needle, candidate)
            if score >= threshold:
                hits.append(FuzzyHit(index=index, name=self.names[index], score=score))
        hits.sort(key=lambda h: (-h.score, h.index))
        return hits[:top_k]

    def prefix_search(self, prefix: str, limit: int) -> list[FuzzyHit]:
        """Typeahead: prefix matches first, then whole-word containment."""
        needle = _normalize_name(prefix)
        if not needle:
            return []
        starts: list[FuzzyHit] = []
        contains: list[FuzzyHit] = []
        for index, candidate in enumerate(self._normalized):
            if candidate.startswith(needle):
                starts.append(FuzzyHit(index, self.names[index], 1.0))
            elif re.search(rf"(?<!\w){re.escape(needle)}", candidate):
                contains.append(FuzzyHit(index, self.names[index], 0.75))
        starts.sort(key=lambda h: (len(self._normalized[h.index]), h.name))
        contains.sort(key=lambda h: (len(self._normalized[h.index]), h.name))
        return (starts + contains)[:limit]


def _normalize_name(name: str) -> str:
    """Lowercase, drop parenthetical glosses and punctuation.

    Dataset names carry translations - "Fish Bun (Malu Pan)",
    "Kir Kos (Jackfruit Curry)" - which otherwise dominate the character-level
    similarity ratio and mask the primary name.
    """
    lowered = name.lower()
    without_gloss = re.sub(r"\([^)]*\)", " ", lowered)
    return " ".join(_WORD_RE.findall(without_gloss))


def _best_similarity(needle: str, candidate: str) -> float:
    """Similarity against the full name and against its individual words.

    A single-word query should match the dish whose name *contains* that word
    closely ("kotu" -> "Chicken Kottu"), not only names of comparable length.
    """
    best = difflib.SequenceMatcher(None, needle, candidate).ratio()
    if " " in candidate and " " not in needle:
        for word in candidate.split():
            if len(word) < 3:
                continue
            best = max(best, difflib.SequenceMatcher(None, needle, word).ratio())
    return best
