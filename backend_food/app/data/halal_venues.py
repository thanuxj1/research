"""Venues listed as halal by hand, and the wording that qualifies that listing.

Why this file exists at all
---------------------------
Until now the only halal signal in the project was OpenStreetMap's `diet:halal`
tag (`places.parse_halal`). That was a deliberate limit: `places.SeedProvider`
still says in its own docstring that marking a named restaurant halal "from
memory rather than from a source" would be inventing a fact about somebody's
business, and it is right. Nothing here weakens that rule - it adds a *second
source* and keeps it labelled as what it is.

The source for every row below is the app operator: these are venues the
operator listed by name. That is a real provenance, and it is a different one
from a mapper's tag, so it gets its own label and its own note rather than
borrowing `HALAL_LABELS`. The badge a user sees must never imply an inspection
that nobody performed - see `CURATED_LABEL`.

Matching, and why it is strict
------------------------------
A venue is matched on its **whole normalised name** - never a substring. That
matters more than it looks. Two of these names are short and generic: a
substring rule would badge "Fabulous Kitchen" from `Fab`, and "Shanmugas Hotel
Ltd" is fine but "Shanmugas Bar" may be an unrelated business. Full-name
equality can only ever fail *closed*: a live provider that spells a name
differently produces no badge, which is the safe direction for a claim like
this one.

`ALIASES` exists because providers do spell the same business differently
("Pilawoos" for "Hotel De Pilawoos"). Every alias must name the *same*
business and must itself be a complete venue name, so it is still full-name
equality and never a prefix another business could carry.
"""

from __future__ import annotations

import re
import unicodedata

# The badge caption and the sentence that qualifies it.
#
# Wording is the server's job here for the same reason the venue disclaimer and
# the confidence legend are: the caveat has to travel with the claim, and three
# real bugs in this project were a server-side caveat that never reached the
# screen. The label says "Halal" without a grade because this source cannot
# distinguish an entirely halal kitchen from one where halal food is available
# alongside food that is not - `diet:halal` can, which is why `only` and `yes`
# keep separate labels over in `places.HALAL_LABELS`. Claiming the stronger of
# the two from a hand-written list would be the overclaim.
CURATED_LABEL = "Halal"
CURATED_NOTE = (
    "Listed as halal in this app's own venue list, which is compiled by hand "
    "and is not a certification or an inspection. Halal practice can also "
    "change with a change of owner or kitchen - confirm with the venue."
)

# name -> the alternative complete names a provider might return for it.
#
# Keep this conservative. An entry here says "these strings are the same
# business"; getting that wrong prints a dietary claim over somebody else's
# restaurant. When unsure, leave the alias out and accept a missing badge.
ALIASES: dict[str, tuple[str, ...]] = {
    "Hotel De Pilawoos": ("Pilawoos", "Pilawoos Hotel"),
    "Anna Pooram Vegetarian Restaurant": ("Anna Pooram",),
    "Upali's by Nawaloka": ("Upalis by Nawaloka", "Upali's"),
    "Balaji Dosai": ("Hotel Balaji Dosai",),
}

# The list itself, as given by the operator.
CURATED_HALAL_VENUES: tuple[str, ...] = (
    "Kandy Muslim Hotel",
    "Hotel De Pilawoos",
    "Upali's by Nawaloka",
    "Shanmugas",
    "Balaji Dosai",
    "Anna Pooram Vegetarian Restaurant",
    "Fab",
)

# Anything that is not a letter, a digit or a space. Apostrophes ("Upali's"),
# ampersands, hyphens and full stops are the ones that actually differ between
# providers, so they are removed rather than mapped.
_NOISE = re.compile(r"[^a-z0-9 ]+")
_SPACES = re.compile(r"\s+")


def normalise_name(name: object) -> str:
    """A venue name reduced to what two spellings of it have in common.

    Unicode is folded to NFKD and stripped of combining marks first, so a name
    carrying an accent or a non-breaking space from a provider still matches the
    plain form written here. Case, punctuation and repeated spaces then go. The
    result is only ever compared for equality - it is not a search key.
    """
    text = unicodedata.normalize("NFKD", str(name or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = _NOISE.sub(" ", text.lower())
    return _SPACES.sub(" ", text).strip()


def _build_index() -> dict[str, str]:
    """normalised name (and alias) -> the canonical name from the list above."""
    index: dict[str, str] = {}
    for canonical in CURATED_HALAL_VENUES:
        for spelling in (canonical, *ALIASES.get(canonical, ())):
            key = normalise_name(spelling)
            if key:
                index[key] = canonical
    return index


HALAL_NAME_INDEX: dict[str, str] = _build_index()


def curated_halal_name(name: object) -> str | None:
    """The canonical listed name for `name`, or None if it is not listed.

    Returns the canonical spelling rather than a bool so a caller can report
    *which* row matched - useful when an alias is what fired.
    """
    return HALAL_NAME_INDEX.get(normalise_name(name))
