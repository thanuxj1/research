"""Dense (bi-encoder) retrieval.

Responsibilities:

* Load the sentence encoder and embed the corpus, with a disk cache so restarts
  do not re-encode. The original startup re-encoded all 155 documents on every
  boot, which dominated cold-start time.
* Apply the BGE **query instruction prefix**. BGE is an asymmetric model: the
  model card requires queries (not documents) to be prefixed with
  "Represent this sentence for searching relevant passages: ". The original code
  omitted it entirely, leaving measurable retrieval accuracy on the table for
  zero cost.
* Expose document-document similarity, which MMR diversification needs.

On FAISS: at 155 documents an exact `IndexFlatIP` is a dense matrix product with
extra indirection, so NumPy is used by default and FAISS is engaged only once the
corpus is large enough for it to matter. Both paths are exact - `IndexFlatIP` on
L2-normalised vectors and `embeddings @ query` compute the same cosine
similarities - so the switch cannot change results.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Sequence

try:  # pragma: no cover - exercised by environment, not by tests
    import numpy as np
except ImportError:  # pragma: no cover
    # Guarded so that `app.search` remains importable, and therefore
    # integration-testable with a stub retriever, in environments without the
    # numeric stack. Every method that touches numpy checks `_require_numpy`.
    np = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

# Below this corpus size, exact NumPy matmul beats FAISS once index construction
# and call overhead are counted.
FAISS_MIN_CORPUS = 5_000

CACHE_VERSION = 1


class DenseRetriever:
    def __init__(
        self,
        model_name: str,
        query_instruction: str = "",
        cache_dir: Path | None = None,
        cache_enabled: bool = True,
    ) -> None:
        self.model_name = model_name
        self.query_instruction = query_instruction
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.cache_enabled = cache_enabled and self.cache_dir is not None

        self._model = None
        self._embeddings: np.ndarray | None = None
        self._faiss_index = None
        self.backend: str = "uninitialised"

    # -- lifecycle ---------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        return self._embeddings is not None

    @property
    def dimension(self) -> int:
        return 0 if self._embeddings is None else int(self._embeddings.shape[1])

    @staticmethod
    def _require_numpy() -> None:
        if np is None:
            raise RuntimeError(
                "numpy is required for dense retrieval; install backend/requirements.txt"
            )

    def build(self, texts: Sequence[str]) -> None:
        """Embed `texts` (cache-aware) and build the search index."""
        self._require_numpy()
        if not texts:
            raise ValueError("cannot build a dense index over an empty corpus")

        fingerprint = self._fingerprint(texts)
        embeddings = self._load_cached(fingerprint)

        if embeddings is None:
            model = self._load_model()
            log.info("Encoding %d documents with %s", len(texts), self.model_name)
            raw = model.encode(
                list(texts),
                batch_size=32,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            embeddings = np.asarray(raw, dtype="float32")
            self._store_cached(fingerprint, embeddings)
        else:
            log.info("Loaded %d cached embeddings", embeddings.shape[0])

        if embeddings.shape[0] != len(texts):
            raise RuntimeError(
                f"embedding count {embeddings.shape[0]} != corpus size {len(texts)}"
            )

        # Re-normalise defensively: cosine via inner product is only valid on
        # unit vectors, and a cache written by an older build may not be normed.
        embeddings = _l2_normalize(embeddings)
        self._embeddings = embeddings
        self._build_index(embeddings)

    def _build_index(self, embeddings: np.ndarray) -> None:
        if len(embeddings) >= FAISS_MIN_CORPUS:
            try:
                import faiss  # type: ignore[import-not-found]

                index = faiss.IndexFlatIP(embeddings.shape[1])
                index.add(embeddings)
                self._faiss_index = index
                self.backend = "faiss:IndexFlatIP"
                return
            except ImportError:
                log.info("faiss unavailable; using exact NumPy search")
        self._faiss_index = None
        self.backend = "numpy:exact"

    def _load_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            log.info("Loading embedding model %s", self.model_name)
            self._model = SentenceTransformer(self.model_name)
        return self._model

    # -- query -------------------------------------------------------------
    def encode_query(self, query: str) -> np.ndarray:
        """Embed a query, applying the asymmetric instruction prefix."""
        self._require_numpy()
        model = self._load_model()
        text = f"{self.query_instruction}{query}" if self.query_instruction else query
        vector = model.encode(
            [text],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vector, dtype="float32").reshape(1, -1)

    def search(self, query: str, top_k: int) -> list[tuple[int, float]]:
        """Top-k (doc_index, cosine_similarity), descending."""
        return self.search_vector(self.encode_query(query), top_k)

    def search_vector(self, vector: np.ndarray, top_k: int) -> list[tuple[int, float]]:
        if self._embeddings is None:
            raise RuntimeError("dense index has not been built")
        top_k = max(1, min(top_k, len(self._embeddings)))

        if self._faiss_index is not None:
            scores, indices = self._faiss_index.search(vector, top_k)
            return [
                (int(i), float(s))
                for i, s in zip(indices[0], scores[0])
                if i >= 0
            ]

        similarities = (self._embeddings @ vector[0]).astype("float32")
        # argpartition is O(n) versus a full O(n log n) sort.
        if top_k < len(similarities):
            candidate_idx = np.argpartition(-similarities, top_k - 1)[:top_k]
        else:
            candidate_idx = np.arange(len(similarities))
        ordered = candidate_idx[np.argsort(-similarities[candidate_idx], kind="stable")]
        return [(int(i), float(similarities[i])) for i in ordered]

    def similar_to(self, index: int, top_k: int) -> list[tuple[int, float]]:
        """More-like-this: nearest neighbours of a corpus document, self excluded."""
        if self._embeddings is None:
            raise RuntimeError("dense index has not been built")
        if not 0 <= index < len(self._embeddings):
            raise IndexError(index)
        vector = self._embeddings[index : index + 1]
        results = self.search_vector(vector, min(top_k + 1, len(self._embeddings)))
        return [(i, score) for i, score in results if i != index][:top_k]

    def similarity(self, left: int, right: int) -> float:
        """Cosine similarity between two corpus documents (used by MMR)."""
        if self._embeddings is None:
            return 0.0
        return float(self._embeddings[left] @ self._embeddings[right])

    # -- cache -------------------------------------------------------------
    def _fingerprint(self, texts: Sequence[str]) -> str:
        digest = hashlib.sha256()
        digest.update(f"v{CACHE_VERSION}\x00{self.model_name}\x00".encode())
        for text in texts:
            digest.update(text.encode("utf-8"))
            digest.update(b"\x00")
        return digest.hexdigest()[:32]

    def _cache_path(self, fingerprint: str) -> Path | None:
        if self.cache_dir is None:
            return None
        return self.cache_dir / f"embeddings-{fingerprint}.npz"

    def _load_cached(self, fingerprint: str) -> np.ndarray | None:
        if not self.cache_enabled:
            return None
        path = self._cache_path(fingerprint)
        if path is None or not path.exists():
            return None
        try:
            # allow_pickle=False: never execute pickled objects from a cache file.
            with np.load(path, allow_pickle=False) as payload:
                return np.asarray(payload["embeddings"], dtype="float32")
        except Exception as exc:  # corrupt or truncated cache
            log.warning("Ignoring unreadable embedding cache %s: %s", path, exc)
            return None

    def _store_cached(self, fingerprint: str, embeddings: np.ndarray) -> None:
        if not self.cache_enabled:
            return
        path = self._cache_path(fingerprint)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            # Write then rename, so a crash mid-write cannot leave a torn file
            # that a later boot would try to read.
            temp = path.with_suffix(".npz.tmp")
            np.savez_compressed(temp, embeddings=embeddings)
            temp.replace(path)
            log.info("Cached embeddings at %s", path)
        except Exception as exc:
            log.warning("Could not write embedding cache: %s", exc)

    def stats(self) -> dict[str, object]:
        return {
            "model": self.model_name,
            "backend": self.backend,
            "documents": 0 if self._embeddings is None else int(self._embeddings.shape[0]),
            "dimension": self.dimension,
            "query_instruction": bool(self.query_instruction),
        }


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype("float32")
