"""Structured recommendation (the /recommend endpoint).

Two substantive bugs in the original implementation are fixed here.

**1. The model score was meaningless.**

    proba = model.predict_proba(X)[0]
    score = float(proba.max())

`predict_proba` returns a distribution over all 155 dish classes. `.max()` is the
probability of *the single most likely dish*, which is the same number regardless
of which row is being scored - it never references the row's own class. Ranking by
it ordered dishes by an almost-constant value, so the visible ordering came from
the multiplicative soft filters underneath, not from the model. The fix reads
`proba[class_index_of(dish)]`: the probability the model assigns to *that dish*.

**2. It called the model 155 times per request.**

The loop invoked `predict_proba` once per dish. Because the features are built
from the *user's* preferences, there is only one distinct feature row to predict:
one call yields the probability of every dish at once. 155 calls -> 1.

The recommender also degrades to a purely rule-based score if the pickled model
cannot be loaded, so the endpoint keeps working rather than returning zeros - the
original silently swallowed prediction errors into `score = 0.0`.
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Sequence

from . import health
from .config import Settings
from .corpus import Corpus, Dish
from .nlu import Constraints
from .ranking import allowed_indices

log = logging.getLogger(__name__)

FEATURE_COLUMNS = ("category", "is_veg", "meal_time", "spicy_level", "price_range")

# Weight of the learned signal against the deterministic preference match.
MODEL_WEIGHT = 0.45
RULE_WEIGHT = 0.55


class OrdinalEncoder:
    """Alphabetically-sorted label encoding.

    Reproduces `sklearn.preprocessing.LabelEncoder`, which sorts its classes, so
    the integer codes match what the model was trained on. Implemented directly
    to avoid depending on sklearn purely for a dict lookup, and to make the
    encoding explicit and inspectable.
    """

    def __init__(self, values: Sequence[str]) -> None:
        self.classes: list[str] = sorted({str(v) for v in values})
        self._lookup = {value: index for index, value in enumerate(self.classes)}

    def encode(self, value: str, default: int = 0) -> int:
        return self._lookup.get(str(value), default)

    def __contains__(self, value: object) -> bool:
        return str(value) in self._lookup

    def __len__(self) -> int:
        return len(self.classes)


class Recommender:
    def __init__(
        self,
        corpus: Corpus,
        settings: Settings,
        price_book: object | None = None,
    ) -> None:
        self.corpus = corpus
        self.settings = settings
        # Duck-typed and optional, matching SearchService: /recommend results are
        # rendered by the same card component as /search results, so they need the
        # same price block or the UI would show a price on one tab and not the other.
        self.price_book = price_book
        self._model = None
        self.load_error: str | None = None

        # Feature values must be the *raw CSV* spellings the model was trained on
        # (is_veg is "TRUE"/"FALSE" in the file, not Python booleans).
        self.encoders: dict[str, OrdinalEncoder] = {
            "category": OrdinalEncoder([d.category for d in corpus]),
            "is_veg": OrdinalEncoder(["TRUE", "FALSE"]),
            "meal_time": OrdinalEncoder([d.meal_time for d in corpus]),
            "spicy_level": OrdinalEncoder([d.spicy_level for d in corpus]),
            "price_range": OrdinalEncoder([d.price_range for d in corpus]),
        }
        self.target = OrdinalEncoder([d.name for d in corpus])
        self._class_index = {name: i for i, name in enumerate(self.target.classes)}

        # Most common value per column, used to fill unstated preferences.
        self._defaults = {
            "category": _mode([d.category for d in corpus]),
            "is_veg": "TRUE",
            "meal_time": _mode([d.meal_time for d in corpus]),
            "spicy_level": _mode([d.spicy_level for d in corpus]),
            "price_range": _mode([d.price_range for d in corpus]),
        }

    # -- lifecycle ---------------------------------------------------------
    def load(self) -> bool:
        path = Path(self.settings.model_path)
        if not path.exists():
            self.load_error = f"model file not found: {path}"
            log.warning("%s - /recommend will use rule-based scoring only", self.load_error)
            return False
        try:
            with path.open("rb") as fh:
                self._model = pickle.load(fh)
            log.info("Loaded recommendation model from %s", path)
            return True
        except Exception as exc:
            self._model = None
            self.load_error = f"{type(exc).__name__}: {exc}"
            log.warning(
                "Could not load %s (%s) - /recommend will use rule-based scoring only",
                path,
                self.load_error,
            )
            return False

    @property
    def model_available(self) -> bool:
        return self._model is not None

    def stats(self) -> dict[str, object]:
        return {
            "model_loaded": self.model_available,
            "error": self.load_error,
            "classes": len(self.target),
            "mode": "hybrid (model + rules)" if self.model_available else "rules only",
        }

    # -- inference ---------------------------------------------------------
    def _class_probabilities(self, preferences: dict[str, str]) -> dict[str, float] | None:
        """P(dish | preferences) for every dish, from a single predict_proba call."""
        if self._model is None:
            return None
        try:
            import numpy as np

            row = [self.encoders[column].encode(preferences[column]) for column in FEATURE_COLUMNS]
            features = np.array([row], dtype="float32")
            proba = self._model.predict_proba(features)[0]

            classes = getattr(self._model, "classes_", None)
            out: dict[str, float] = {}
            if classes is not None:
                # Map the model's own class labels back to dish names. Labels may
                # be encoded integers or the names themselves depending on how
                # the model was fitted.
                for position, label in enumerate(classes):
                    if position >= len(proba):
                        break
                    name = self._label_to_name(label)
                    if name is not None:
                        out[name] = float(proba[position])
            else:
                for name, index in self._class_index.items():
                    if index < len(proba):
                        out[name] = float(proba[index])
            return out or None
        except Exception as exc:
            log.warning("predict_proba failed (%s); falling back to rules", exc)
            self._model = None
            self.load_error = f"{type(exc).__name__}: {exc}"
            return None

    def _label_to_name(self, label: object) -> str | None:
        if isinstance(label, str):
            return label if label in self._class_index else None
        try:
            index = int(label)
        except (TypeError, ValueError):
            return None
        if 0 <= index < len(self.target.classes):
            return self.target.classes[index]
        return None

    def recommend(
        self,
        category: str | None = None,
        is_veg: str | None = None,
        meal_time: str | None = None,
        spicy_level: str | None = None,
        price_range: str | None = None,
        top_k: int = 8,
        health_conditions: Sequence[str] = (),
        strict_allergens: bool = False,
        explain: bool = False,
    ) -> dict:
        stated: dict[str, str] = {}
        if category:
            stated["category"] = category
        if is_veg is not None:
            stated["is_veg"] = "TRUE" if str(is_veg).strip().lower() in {"true", "1", "yes"} else "FALSE"
        if meal_time:
            stated["meal_time"] = meal_time
        if spicy_level:
            stated["spicy_level"] = spicy_level
        if price_range:
            stated["price_range"] = price_range

        preferences = {**self._defaults, **stated}
        probabilities = self._class_probabilities(preferences)

        # Hard filters mirror /search so the two endpoints cannot disagree about
        # what is safe to show.
        constraints = Constraints(diet="veg" if stated.get("is_veg") == "TRUE" else None)
        strict_tags = health.allergen_tags_for(health_conditions) if strict_allergens else set()
        survivors, filter_report = allowed_indices(
            self.corpus.dishes, constraints, sorted(strict_tags)
        )

        max_probability = max(probabilities.values()) if probabilities else 0.0

        scored: list[tuple[float, Dish, dict]] = []
        for index in survivors:
            dish = self.corpus[index]
            rule_score, matched, total_stated = self._rule_score(dish, stated)

            if probabilities and max_probability > 0:
                # Normalise by the batch maximum so the learned signal is
                # comparable to the rule score. `probabilities[dish.name]` is the
                # probability of *this* dish - the bug fix.
                model_score = probabilities.get(dish.name, 0.0) / max_probability
                combined = MODEL_WEIGHT * model_score + RULE_WEIGHT * rule_score
            else:
                model_score = None
                combined = rule_score

            warnings = health.evaluate(dish.tags, dish.spicy_level, list(health_conditions))
            severity = health.worst_severity(warnings)
            if severity == "danger":
                combined += self.settings.scoring.health_danger_penalty
            elif severity == "caution":
                combined += self.settings.scoring.health_caution_penalty

            payload = dish.public_dict(
                None if self.price_book is None else self.price_book.get(dish.name)
            )
            payload["score"] = round(combined, 4)
            payload["warnings"] = [w.as_dict() for w in warnings]
            payload["health_severity"] = severity
            if explain:
                payload["explanation"] = {
                    "model_score": None if model_score is None else round(model_score, 4),
                    "rule_score": round(rule_score, 4),
                    "matched_preferences": matched,
                    "stated_preferences": total_stated,
                    "source": "model + rules" if model_score is not None else "rules only",
                }
            scored.append((combined, dish, payload))

        scored.sort(key=lambda item: (-item[0], item[1].name))
        results = [payload for _, _, payload in scored[:top_k]]

        return {
            "results": results,
            "total": len(results),
            "preferences": stated,
            "filters": filter_report.as_dict(),
            "engine": self.stats(),
        }

    def _rule_score(self, dish: Dish, stated: dict[str, str]) -> tuple[float, list[str], int]:
        """Fraction of stated preferences the dish satisfies.

        With nothing stated every dish scores 1.0, leaving the learned signal (or
        alphabetical order) to decide - which is the honest behaviour for an
        empty request.
        """
        if not stated:
            return 1.0, [], 0

        matched: list[str] = []
        for column, wanted in stated.items():
            actual = self._dish_value(dish, column)
            if column == "meal_time":
                # "Any" satisfies any requested meal.
                if wanted.lower() in actual.lower() or actual.lower() == "any":
                    matched.append(column)
            elif actual.lower() == wanted.lower():
                matched.append(column)

        return len(matched) / len(stated), matched, len(stated)

    @staticmethod
    def _dish_value(dish: Dish, column: str) -> str:
        if column == "is_veg":
            return "TRUE" if dish.is_veg else "FALSE"
        return str(getattr(dish, column))


def _mode(values: Sequence[str]) -> str:
    tally: dict[str, int] = {}
    for value in values:
        tally[value] = tally.get(value, 0) + 1
    if not tally:
        return "Unknown"
    return max(tally.items(), key=lambda kv: (kv[1], kv[0]))[0]
