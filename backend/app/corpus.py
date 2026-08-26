"""Corpus construction: dataset loading, tagging, and document generation.

Stdlib only (no pandas), which keeps the tagging pass unit-testable without the
ML stack installed. The heavy numeric work lives in `dense.py` / `recommend.py`.

Two documents are generated per dish, on purpose:

* `dense_text` - fluent prose for the bi-encoder. Sentence encoders are trained
  on natural language, so a readable sentence embeds far better than a bag of
  keywords. The original `build_search_text` produced keyword soup
  ("... vegetarian vegan plant-based. Meal time: Any. Spice: None. mild low
  spice not spicy gentle...") and fed it straight to the encoder.
* `sparse_tokens` - a weighted token bag for BM25, where the dish name and tags
  are repeated so exact name hits outrank incidental description hits. Term
  repetition is meaningless to an encoder but is exactly how you express field
  weighting to BM25.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .data.descriptions import FOOD_DESCRIPTIONS
from .data.taxonomy import (
    CATEGORY_TAGS,
    MEAL_TIMES,
    NONVEG_ONLY_TAGS,
    SPICE_ORDER,
    TAG_MATCHERS,
    TAG_NEGATIVE_MATCHERS,
    price_rank,
    spice_rank,
    tag_label,
)

_WORD_RE = re.compile(r"[a-z0-9]+")

DEFAULT_DESCRIPTION = "Traditional Sri Lankan food."

_TRUTHY = {"true", "1", "yes", "y", "t"}

SPICE_PHRASES: dict[str, str] = {
    "None": "carries no chilli heat at all",
    "Low": "is only mildly spiced and gentle on the palate",
    "Medium": "is moderately spicy",
    "High": "is very spicy and full of chilli heat",
    "Very High": "is extremely fiery",
}

PRICE_PHRASES: dict[str, str] = {
    "Low": "It is cheap and widely available.",
    "Medium": "It sits at a mid-range price.",
    "High": "It is one of the more expensive choices.",
}


@dataclass(frozen=True)
class Dish:
    index: int
    name: str
    category: str
    is_veg: bool
    meal_time: str  # raw dataset label, e.g. "Breakfast/Dinner"
    meal_times: frozenset[str]  # expanded, e.g. {"Breakfast", "Dinner"}
    spicy_level: str
    price_range: str
    description: str
    tags: frozenset[str]
    dense_text: str
    sparse_tokens: tuple[str, ...]

    @property
    def spice_rank(self) -> int:
        return spice_rank(self.spicy_level)

    @property
    def price_rank(self) -> int:
        return price_rank(self.price_range)

    def public_dict(self, price: object | None = None) -> dict[str, object]:
        """Shape returned by the API. `is_veg` stays a string for backwards
        compatibility with the existing client contract.

        `price` is an optional `pricing.Price`, taken as a duck-typed argument
        with an `as_dict()` rather than imported: `corpus` is the lowest layer
        here and importing `pricing` would invert that. It is a parameter rather
        than a `Dish` field because a price is not a property of the dish - it
        depends on the loaded price table, the inflation multiplier and today's
        date, none of which the corpus knows about. Keeping the key name in this
        one method is what stops /search, /dishes, /similar and /recommend from
        drifting into four different price shapes.
        """
        payload: dict[str, object] = {
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "is_veg": "True" if self.is_veg else "False",
            "meal_time": self.meal_time,
            "spicy_level": self.spicy_level,
            "price_range": self.price_range,
            "tags": sorted(self.tags),
            "tag_labels": [tag_label(t) for t in sorted(self.tags)],
        }
        # Always present, so the client can branch on null instead of on a
        # missing key - an absent price is a real state (custom table, pricing
        # disabled) and the UI has to render it.
        payload["price"] = price.as_dict() if price is not None else None
        return payload


class Corpus:
    """The in-memory dish collection plus its derived indexes."""

    def __init__(self, dishes: Sequence[Dish]) -> None:
        self.dishes: tuple[Dish, ...] = tuple(dishes)
        self._by_name: dict[str, Dish] = {d.name.lower(): d for d in self.dishes}

    def __len__(self) -> int:
        return len(self.dishes)

    def __iter__(self):
        return iter(self.dishes)

    def __getitem__(self, index: int) -> Dish:
        return self.dishes[index]

    def get(self, name: str) -> Dish | None:
        return self._by_name.get(name.strip().lower())

    @property
    def names(self) -> list[str]:
        return [d.name for d in self.dishes]

    @property
    def dense_texts(self) -> list[str]:
        return [d.dense_text for d in self.dishes]

    @property
    def sparse_corpus(self) -> list[list[str]]:
        return [list(d.sparse_tokens) for d in self.dishes]

    def facets(self) -> dict[str, object]:
        """Facet values with counts, for the UI's filter controls."""

        def counts(values: Iterable[str]) -> list[dict[str, object]]:
            tally: dict[str, int] = {}
            for value in values:
                tally[value] = tally.get(value, 0) + 1
            return [
                {"value": k, "count": v}
                for k, v in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
            ]

        tag_tally: dict[str, int] = {}
        for dish in self.dishes:
            for tag in dish.tags:
                tag_tally[tag] = tag_tally.get(tag, 0) + 1

        return {
            "categories": counts(d.category for d in self.dishes),
            "meal_times": counts(d.meal_time for d in self.dishes),
            "spicy_levels": [
                {"value": level, "count": sum(1 for d in self.dishes if d.spicy_level == level)}
                for level in ("None", "Low", "Medium", "High")
            ],
            "price_ranges": [
                {"value": level, "count": sum(1 for d in self.dishes if d.price_range == level)}
                for level in ("Low", "Medium", "High")
            ],
            "diets": [
                {"value": "True", "label": "Vegetarian", "count": sum(1 for d in self.dishes if d.is_veg)},
                {"value": "False", "label": "Non-Vegetarian", "count": sum(1 for d in self.dishes if not d.is_veg)},
            ],
            "tags": [
                {"value": tag, "label": tag_label(tag), "count": count}
                for tag, count in sorted(tag_tally.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "total": len(self.dishes),
        }

    def vocabulary_texts(self) -> list[str]:
        """Text used to seed the spell-checker vocabulary."""
        return [d.name for d in self.dishes] + [d.description for d in self.dishes]


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_corpus(
    data_path: Path,
    name_weight: int = 3,
    tag_weight: int = 2,
) -> Corpus:
    rows = _read_rows(data_path)
    dishes: list[Dish] = []
    for index, row in enumerate(rows):
        name = row["name"].strip()
        category = row.get("category", "Unknown").strip() or "Unknown"
        is_veg = str(row.get("is_veg", "")).strip().lower() in _TRUTHY
        meal_time = row.get("meal_time", "Any").strip() or "Any"
        spicy_level = _title(row.get("spicy_level", "Unknown"))
        price_range = _title(row.get("price_range", "Unknown"))
        description = FOOD_DESCRIPTIONS.get(name, DEFAULT_DESCRIPTION)

        tags = assign_tags(
            name=name,
            description=description,
            category=category,
            is_veg=is_veg,
            spicy_level=spicy_level,
        )
        meal_times = parse_meal_times(meal_time)

        dishes.append(
            Dish(
                index=index,
                name=name,
                category=category,
                is_veg=is_veg,
                meal_time=meal_time,
                meal_times=meal_times,
                spicy_level=spicy_level,
                price_range=price_range,
                description=description,
                tags=tags,
                dense_text=build_dense_text(
                    name=name,
                    description=description,
                    category=category,
                    is_veg=is_veg,
                    meal_times=meal_times,
                    meal_time=meal_time,
                    spicy_level=spicy_level,
                    price_range=price_range,
                ),
                sparse_tokens=build_sparse_tokens(
                    name=name,
                    description=description,
                    category=category,
                    is_veg=is_veg,
                    meal_time=meal_time,
                    spicy_level=spicy_level,
                    price_range=price_range,
                    tags=tags,
                    name_weight=name_weight,
                    tag_weight=tag_weight,
                ),
            )
        )
    return Corpus(dishes)


def _read_rows(data_path: Path) -> list[dict[str, str]]:
    with Path(data_path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"{data_path} has no header row")
        # Normalise headers the same way the original pandas pipeline did.
        mapping = {
            field: field.strip().lower().replace(" ", "_")
            for field in reader.fieldnames
        }
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {
                mapping[k]: ("" if v is None else v)
                for k, v in raw.items()
                if k in mapping
            }
            if row.get("name", "").strip():
                rows.append(row)
    return rows


def _title(value: str) -> str:
    cleaned = str(value).strip()
    return cleaned.title() if cleaned else "Unknown"


def parse_meal_times(meal_time: str) -> frozenset[str]:
    """Expand the dataset's compound labels into a set.

    "Any" -> all meals; "Breakfast/Dinner" -> {Breakfast, Dinner}.
    """
    label = meal_time.strip().lower()
    if not label or label in {"any", "unknown"}:
        return frozenset(MEAL_TIMES)
    found = {meal for meal in MEAL_TIMES if meal.lower() in label}
    return frozenset(found) if found else frozenset(MEAL_TIMES)


def assign_tags(
    name: str,
    description: str,
    category: str,
    is_veg: bool,
    spicy_level: str,
) -> frozenset[str]:
    """Keyword + rule tagging over "<name> <description>".

    All matching is word-boundary anchored, which fixes a class of false
    positives the original substring rules produced - most importantly
    `"egg" in "eggplant curry"`, which flagged *Eggplant Curry* and
    *Wambatu Moju (Eggplant Pickle)* as unsafe for egg allergies.
    """
    haystack = f"{name} {description}".lower()
    tags: set[str] = set()
    for tag, matcher in TAG_MATCHERS.items():
        # Blank out this tag's negative phrases first, so "creamy coconut milk"
        # cannot satisfy the dairy matcher via its "milk" keyword.
        negative = TAG_NEGATIVE_MATCHERS.get(tag)
        text = negative.sub(" ", haystack) if negative is not None else haystack
        if matcher.search(text):
            tags.add(tag)
    tags.update(CATEGORY_TAGS.get(category, ()))

    if is_veg:
        # A vegetarian dish cannot carry a meat/seafood tag, even if its
        # description draws a comparison (Polos Curry: "meat-like texture").
        tags -= NONVEG_ONLY_TAGS
        # Vegan = vegetarian minus dairy and egg. Derived, not keyword-matched.
        if not ({"dairy", "egg"} & tags):
            tags.add("vegan")
    else:
        tags.discard("vegan")
        tags.add("high_protein")

    # "Famous among tourists" appears in the description of several fiercely
    # spicy dishes (Crab Curry). Beginner-friendly requires actual mildness.
    if spicy_level and spice_rank(spicy_level) > SPICE_ORDER["Low"]:
        tags.discard("beginner_friendly")

    return frozenset(tags)


def build_dense_text(
    name: str,
    description: str,
    category: str,
    is_veg: bool,
    meal_times: frozenset[str],
    meal_time: str,
    spicy_level: str,
    price_range: str,
) -> str:
    """Fluent prose for the bi-encoder."""
    diet = "vegetarian" if is_veg else "non-vegetarian"
    spice = SPICE_PHRASES.get(spicy_level, "has an unspecified spice level")
    price = PRICE_PHRASES.get(price_range, "")

    if meal_times == frozenset(MEAL_TIMES):
        when = "It can be eaten at any time of day"
    else:
        ordered = [m for m in MEAL_TIMES if m in meal_times]
        when = "It is usually eaten at " + _join_human([m.lower() for m in ordered])

    return (
        f"{name} is a {diet} Sri Lankan {category.lower().rstrip('s')} dish. "
        f"{description} It {spice}. {when}. {price}"
    ).strip()


def build_sparse_tokens(
    name: str,
    description: str,
    category: str,
    is_veg: bool,
    meal_time: str,
    spicy_level: str,
    price_range: str,
    tags: frozenset[str],
    name_weight: int,
    tag_weight: int,
) -> tuple[str, ...]:
    """Weighted token bag for BM25.

    Repetition is how term-frequency models express field boosting: the name
    appears `name_weight` times so that querying "kottu" ranks the dishes named
    kottu above dishes that merely mention kottu in prose.
    """
    tokens: list[str] = []
    name_tokens = _WORD_RE.findall(name.lower())
    tokens.extend(name_tokens * max(1, name_weight))

    tag_tokens: list[str] = []
    for tag in sorted(tags):
        tag_tokens.extend(tag.split("_"))
    tokens.extend(tag_tokens * max(1, tag_weight))

    tokens.extend(_WORD_RE.findall(description.lower()))
    tokens.extend(_WORD_RE.findall(category.lower()))
    tokens.extend(_WORD_RE.findall(meal_time.lower()))
    tokens.append("vegetarian" if is_veg else "nonvegetarian")
    if is_veg:
        tokens.append("vegan")
    tokens.extend([spicy_level.lower(), "spice"])
    tokens.extend([price_range.lower(), "price"])
    return tuple(tokens)


def _join_human(items: Sequence[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " or " + items[-1]
