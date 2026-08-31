"""Stage 3: cross-encoder reranking.

This is the single largest accuracy gain in the pipeline and the piece the
original implementation lacked entirely.

A bi-encoder embeds the query and each document *independently*, so the two never
interact and the model cannot tell that "mild" attaches to "curry" rather than to
"dessert" elsewhere in the document. A cross-encoder concatenates the pair and
runs full attention across both, which resolves exactly those attachment and
compositionality questions - at a cost that only makes sense on a small candidate
set, which is what stages 1-2 produce.

The reranker is strictly optional. It loads lazily, and any failure (missing
package, no model weights on disk, no network on first run) degrades to
first-stage fused ranking rather than failing the request. `/health` reports
which mode is live so a silent downgrade is observable.
"""

from __future__ import annotations

import logging
import math
from typing import Sequence

log = logging.getLogger(__name__)


class CrossEncoderReranker:
    def __init__(
        self,
        model_name: str,
        batch_size: int = 32,
        enabled: bool = True,
    ) -> None:
        self.model_name = model_name
        self.batch_size = batch_size
        self.enabled = enabled
        self._model = None
        self._load_failed = False
        self.load_error: str | None = None

    @property
    def is_available(self) -> bool:
        return self.enabled and not self._load_failed

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def warmup(self) -> bool:
        """Eagerly load the model. Returns True on success.

        Called during startup so the first user request does not pay the model
        download/load latency.
        """
        if not self.enabled:
            return False
        return self._ensure_model() is not None

    def _ensure_model(self):
        if self._model is not None or self._load_failed:
            return self._model
        try:
            from sentence_transformers import CrossEncoder

            log.info("Loading cross-encoder %s", self.model_name)
            self._model = CrossEncoder(self.model_name)
            self.load_error = None
        except Exception as exc:
            # Broad by design: a reranker that cannot load must not take the API
            # down with it.
            self._load_failed = True
            self.load_error = f"{type(exc).__name__}: {exc}"
            log.warning(
                "Cross-encoder unavailable (%s). Falling back to first-stage ranking.",
                self.load_error,
            )
        return self._model

    def score(self, query: str, documents: Sequence[str]) -> list[float] | None:
        """Relevance in (0, 1) per document, or None if reranking is unavailable.

        `None` is deliberately distinct from a list of zeros: the caller must be
        able to tell "reranker declined" from "reranker judged everything
        irrelevant".
        """
        if not documents or not self.is_available:
            return None
        model = self._ensure_model()
        if model is None:
            return None
        try:
            pairs = [(query, document) for document in documents]
            raw = model.predict(pairs, batch_size=self.batch_size, show_progress_bar=False)
        except Exception as exc:
            log.warning("Cross-encoder scoring failed: %s", exc)
            self._load_failed = True
            self.load_error = f"{type(exc).__name__}: {exc}"
            return None

        # bge-reranker emits unbounded logits; squash them into (0, 1) so they
        # can be blended with the normalised first-stage score.
        return [_sigmoid(float(value)) for value in _flatten(raw)]

    def stats(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "model": self.model_name,
            "loaded": self.is_loaded,
            "available": self.is_available,
            "error": self.load_error,
        }


def _sigmoid(value: float) -> float:
    # Branch to avoid overflow in exp() for large-magnitude logits.
    if value >= 0.0:
        return 1.0 / (1.0 + math.exp(-value))
    exponential = math.exp(value)
    return exponential / (1.0 + exponential)


def _flatten(values) -> list[float]:
    """Accept a 1-D array, a list, or an (n, 1) array from predict()."""
    out: list[float] = []
    for value in values:
        if hasattr(value, "__len__") and not isinstance(value, (str, bytes)):
            out.extend(float(v) for v in value)
        else:
            out.append(float(value))
    return out
