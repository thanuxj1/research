"""Health-condition warning engine.

Rebuilt around the nutrition tags produced by the tagging pass in `corpus.py`
rather than per-condition keyword lists. The original design duplicated the same
keyword vocabulary three times (once in `HEALTH_RULES`, once again in the
frontend's `RULES` object, and a third time in the search heuristics), so the
three copies had already drifted apart.

Consequences of moving to tags:

* One tagging pass, one source of truth. The frontend no longer ships rules at
  all - it renders whatever the API returns.
* Word-boundary matching fixes real false positives. `"egg" in "eggplant curry"`
  is true as a substring, so *Eggplant Curry* and *Wambatu Moju* were previously
  flagged as unsafe for egg allergies. `\\begg\\b` does not match "eggplant".
* Conditions become declarative and trivially unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

from .data.taxonomy import SPICE_ORDER, spice_rank

Severity = Literal["danger", "caution"]

SEVERITY_RANK: dict[str, int] = {"caution": 1, "danger": 2}


@dataclass(frozen=True)
class HealthRule:
    """Fires when the dish carries `tag`, or when its spice meets `min_spice`."""

    severity: Severity
    message: str
    tag: str | None = None
    min_spice: str | None = None

    def matches(self, tags: frozenset[str], spicy_level: str) -> bool:
        if self.tag is not None and self.tag in tags:
            return True
        if self.min_spice is not None:
            return spice_rank(spicy_level) >= SPICE_ORDER[self.min_spice]
        return False


@dataclass(frozen=True)
class Condition:
    id: str
    label: str
    description: str
    # Allergies are absolute: they can be promoted to a hard filter that removes
    # results entirely, rather than merely ranking them down.
    is_allergy: bool
    rules: tuple[HealthRule, ...]


CONDITIONS: tuple[Condition, ...] = (
    Condition(
        id="diabetes",
        label="Diabetes",
        description="High-sugar and high-glycaemic foods are flagged",
        is_allergy=False,
        rules=(
            HealthRule("danger", "High sugar content - avoid if diabetic", tag="high_sugar"),
            HealthRule("caution", "High glycaemic index - keep portions small", tag="high_gi"),
        ),
    ),
    Condition(
        id="hypertension",
        label="High Blood Pressure",
        description="Salty, very spicy and fatty foods are flagged",
        is_allergy=False,
        rules=(
            HealthRule("danger", "High sodium - may raise blood pressure", tag="high_sodium"),
            HealthRule("caution", "High saturated fat - limit with hypertension", tag="high_saturated_fat"),
            HealthRule("caution", "Very spicy - may aggravate hypertension", min_spice="High"),
        ),
    ),
    Condition(
        id="high_cholesterol",
        label="High Cholesterol",
        description="Deep-fried and high-fat foods are flagged",
        is_allergy=False,
        rules=(
            HealthRule("danger", "Deep fried / high fat - avoid with high cholesterol", tag="deep_fried"),
            HealthRule("caution", "High saturated fat - limit portion size", tag="high_saturated_fat"),
        ),
    ),
    Condition(
        id="gout",
        label="Gout",
        description="High-purine meats, seafood and alcohol are flagged",
        is_allergy=False,
        rules=(
            HealthRule("danger", "High purine - can trigger gout flare-ups", tag="high_purine"),
            HealthRule("danger", "Alcohol - worsens gout", tag="alcohol"),
            HealthRule("caution", "Moderate purine - limit with gout", tag="lentil"),
        ),
    ),
    Condition(
        id="kidney_disease",
        label="Kidney Disease",
        description="High-sodium, high-protein and high-potassium foods are flagged",
        is_allergy=False,
        rules=(
            HealthRule("danger", "High sodium - harmful with kidney disease", tag="high_sodium"),
            HealthRule("caution", "High protein - limit portions with kidney disease", tag="high_protein"),
            HealthRule("caution", "High potassium - confirm with your doctor", tag="high_potassium"),
        ),
    ),
    Condition(
        id="gluten_intolerance",
        label="Gluten Intolerance",
        description="Wheat-based breads, rotis and pastries are flagged",
        is_allergy=True,
        rules=(
            HealthRule("danger", "Contains gluten (wheat) - avoid if coeliac", tag="gluten"),
            HealthRule("caution", "Rice-based, but cross-contamination is possible", tag="rice"),
        ),
    ),
    Condition(
        id="lactose_intolerance",
        label="Lactose Intolerance",
        description="Dairy-based foods and drinks are flagged",
        is_allergy=True,
        rules=(HealthRule("danger", "Contains dairy - avoid if lactose intolerant", tag="dairy"),),
    ),
    Condition(
        id="coconut_allergy",
        label="Coconut Allergy",
        description="Coconut-containing dishes are flagged",
        is_allergy=True,
        rules=(HealthRule("danger", "Contains coconut - do not eat if allergic", tag="coconut"),),
    ),
    Condition(
        id="seafood_allergy",
        label="Seafood Allergy",
        description="Fish, prawn, crab and cuttlefish dishes are flagged",
        is_allergy=True,
        rules=(HealthRule("danger", "Contains seafood - do not eat if allergic", tag="seafood"),),
    ),
    Condition(
        id="nut_allergy",
        label="Nut Allergy",
        description="Cashew, sesame and other nut dishes are flagged",
        is_allergy=True,
        rules=(HealthRule("danger", "Contains nuts - do not eat if allergic", tag="nuts"),),
    ),
    Condition(
        id="egg_allergy",
        label="Egg Allergy",
        description="Egg-containing dishes are flagged",
        is_allergy=True,
        rules=(HealthRule("danger", "Contains egg - do not eat if allergic", tag="egg"),),
    ),
)

CONDITIONS_BY_ID: dict[str, Condition] = {c.id: c for c in CONDITIONS}


@dataclass(frozen=True)
class Warning:
    condition: str
    condition_label: str
    severity: Severity
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "condition": self.condition,
            "condition_label": self.condition_label,
            "severity": self.severity,
            "message": self.message,
        }


def evaluate(
    tags: Iterable[str],
    spicy_level: str,
    condition_ids: Sequence[str],
) -> list[Warning]:
    """Warnings for one dish, de-duplicated by message, worst severity first."""
    tag_set = frozenset(tags)
    found: dict[str, Warning] = {}

    for condition_id in condition_ids:
        condition = CONDITIONS_BY_ID.get(condition_id)
        if condition is None:
            continue
        for rule in condition.rules:
            if not rule.matches(tag_set, spicy_level):
                continue
            key = f"{condition.id}:{rule.message}"
            existing = found.get(key)
            if existing is None or SEVERITY_RANK[rule.severity] > SEVERITY_RANK[existing.severity]:
                found[key] = Warning(
                    condition=condition.id,
                    condition_label=condition.label,
                    severity=rule.severity,
                    message=rule.message,
                )

    return sorted(
        found.values(),
        key=lambda w: (-SEVERITY_RANK[w.severity], w.condition_label),
    )


def worst_severity(warnings: Sequence[Warning]) -> Severity | None:
    if any(w.severity == "danger" for w in warnings):
        return "danger"
    if warnings:
        return "caution"
    return None


def allergen_tags_for(condition_ids: Sequence[str]) -> set[str]:
    """Tags that should be hard-excluded when strict allergy filtering is on."""
    out: set[str] = set()
    for condition_id in condition_ids:
        condition = CONDITIONS_BY_ID.get(condition_id)
        if condition is None or not condition.is_allergy:
            continue
        for rule in condition.rules:
            if rule.severity == "danger" and rule.tag:
                out.add(rule.tag)
    return out


def catalog() -> list[dict[str, object]]:
    """Condition metadata for the UI, so the frontend stops hardcoding it."""
    return [
        {
            "id": c.id,
            "label": c.label,
            "description": c.description,
            "is_allergy": c.is_allergy,
        }
        for c in CONDITIONS
    ]
