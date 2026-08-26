"""Feedback on the recommender, from the people it recommends to.

A rating and an optional comment, appended to a JSON Lines file. Read back only
as aggregates.

What is deliberately *not* recorded
----------------------------------
No IP address, no `User-Agent`, no session or device identifier, no referrer, and
no link to what the person searched for. The stored record is the rating, the
comment they chose to type, the timestamp, and the API version that produced the
recommendations they were rating - and nothing else.

That is a design decision, not an oversight, and it has a cost worth naming: two
submissions cannot be told apart, so this data cannot answer "how many distinct
users are unhappy" and it cannot be used to reply to anyone. In exchange, a
feedback file that leaks is a list of opinions rather than a list of people, and
there is no setting to change that - a flag for "also log the IP" is a flag
somebody eventually turns on.

The API version *is* stored, because a 2-star rating is uninterpretable without
knowing which ranking produced it, and it says nothing about who submitted it.

Why a file
----------
The requirement is: append one record, read counts back. A file does that, and
doing it in the standard library is what keeps this module importable - and its
tests runnable - with no database, no services and no network, like `pricing`
and `config`.

Two things a file needs that a database would have given us. Writes are
lock-guarded, because FastAPI runs sync handlers on a threadpool and two
concurrent submissions would otherwise interleave into one corrupt line (README
bug 17 was this same mistake in another module). And a size ceiling, because an
unauthenticated append endpoint is otherwise a way to fill the disk and take the
rest of the app down with it.

Comments are stored JSON-encoded, so a comment containing newlines stays on one
physical line and cannot forge a second record. That is the property JSONL
depends on, and `test_feedback` pins it.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator

MIN_RATING = 1
MAX_RATING = 5

# Bytes a record costs on top of its comment: the uuid, the timestamp, the
# version, the key names and JSON's punctuation. Measured generously, because it
# is used to decide whether to *promise* room, and a promise that is optimistic
# by a byte is a promise broken.
RECORD_ENVELOPE_BYTES = 200

# The scale, in the server's words.
#
# The client renders these rather than inventing its own, for the same reason the
# venue disclaimer and the halal caption come from the server: the labels define
# what a "4" in the stored data actually means, and a second copy in the frontend
# would be free to drift until the number and its meaning disagreed. Anyone
# reading the file later needs the labels that were on screen at the time.
#
# Five points, odd, with a real middle: "Mixed" is a genuine answer for a
# recommender - some results useful, some not - and forcing that into a 2 or a 4
# would lose it.
RATING_SCALE: tuple[tuple[int, str], ...] = (
    (1, "Not useful"),
    (2, "Barely useful"),
    (3, "Mixed"),
    (4, "Useful"),
    (5, "Very useful"),
)

RATING_LABELS: dict[int, str] = dict(RATING_SCALE)

# Every user-facing string this feature shows, in one place, on the server.
#
# The two that matter most are `privacy_note` and `disabled_note`. The privacy
# note is a promise about what happens to the comment, and it has to be made by
# the code that actually does the storing, or it becomes a promise the frontend
# is making on the backend's behalf without being able to keep it. The disabled
# note exists because the alternative - a client that says "thanks, saved!" when
# storage is off - is the exact failure this project has already had three times:
# a caveat that never reached the screen.
COPY: dict[str, str] = {
    "title": "Was this useful?",
    "prompt": "Rate the dish recommendations you have seen so far.",
    "comment_prompt": "Anything you would change? (optional)",
    "comment_placeholder": "Wrong dishes, missing dishes, prices that looked off...",
    "submit": "Send feedback",
    "privacy_note": (
        "Only your rating and comment are stored - no IP address, no browser details, "
        "and nothing that links this to what you searched for."
    ),
    "disabled_note": (
        "Feedback collection is switched off on this server, so there is nowhere for "
        "this to go."
    ),
    # Shown *before* anyone types, while `accepting` is false. The point is that
    # it arrives in place of a working form rather than in place of a thank-you:
    # the refusal sentence below is what a full log says to someone who has
    # already written a paragraph, and by then it is too late to be useful.
    "paused_note": (
        "The feedback log on this server is full, so new submissions are paused. "
        "Nothing typed here would be saved."
    ),
    "thanks": "Thanks - your rating was saved.",
    # Truncation is silent unless the response says otherwise, and "Thanks - your
    # rating was saved" over a comment that lost its second half is the kind of
    # quiet half-truth this project keeps finding in its own code.
    "thanks_truncated": (
        "Thanks - your rating was saved. Your comment was longer than this server "
        "keeps, so only the first {limit} characters were stored."
    ),
    "thanks_duplicate": "Thanks - we already have this one, so it was not saved twice.",
    "full": (
        "The feedback log is full on this server, so this could not be saved. "
        "Nothing you typed was stored."
    ),
    "unwritable": (
        "Feedback could not be written on this server, so this was not saved. "
        "Nothing you typed was stored."
    ),
    "summary_note": (
        "Aggregates only. Comment text is never returned by this endpoint - it is "
        "written to the log for the maintainers and read from there, not served."
    ),
}


class FeedbackUnavailable(RuntimeError):
    """Storage refused the write. Carries the sentence to show the user.

    A distinct exception rather than a False return value: "not saved" has to be
    impossible to mistake for "saved", and a caller that ignores an exception
    fails loudly while a caller that ignores a boolean fails silently and
    cheerfully thanks the user.
    """


def clean_comment(raw: object, max_chars: int) -> tuple[str | None, bool]:
    """Normalise a free-text comment. Returns `(comment, was_truncated)`.

    Blank, whitespace-only and absent all collapse to None, so "no comment" has
    one representation in the file instead of four.

    C0 control characters are dropped except tab and newline, which people do
    type. The rest never arrive intentionally; they arrive from a paste or a
    fuzzer, and they make the log hostile to read in a terminal. This is not a
    security measure - `json.dumps` is what makes the line safe - it is hygiene.
    """
    text = "" if raw is None else str(raw)
    text = "".join(ch for ch in text if ch in "\t\n" or ord(ch) >= 32)
    text = text.strip()
    if not text:
        return None, False
    limit = max(1, max_chars)
    if len(text) > limit:
        # Truncated rather than rejected. The client is told the limit and counts
        # down to it, so reaching this line means a non-browser caller: keeping
        # the first 600 characters of what they said is more useful than a 422.
        return text[:limit], True
    return text, False


@dataclass(frozen=True)
class FeedbackEntry:
    """One stored submission.

    Frozen, like `Venue` and `Price`: once written to the file a record is
    history, and history that a later code path can edit in place is not
    history.
    """

    id: str
    created_at: str
    rating: int
    comment: str | None
    api_version: str

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "rating": self.rating,
            "comment": self.comment,
            "api_version": self.api_version,
        }

    def as_line(self) -> str:
        """One JSONL record, newline included.

        `ensure_ascii=True` is the default and is kept: Sinhala and Tamil
        comments survive as escapes, and the file stays byte-safe whatever
        encoding the thing reading it guesses.
        """
        return json.dumps(self.as_dict(), sort_keys=True) + "\n"


class FeedbackStore:
    """Append-only JSONL feedback log with an aggregate read.

    The clocks are injected so the tests can be about behaviour rather than about
    waiting: `monotonic` drives the duplicate window and `now` stamps the record.
    They are separate because they answer different questions - a wall clock can
    jump backwards over an NTP correction, which would silently widen or close
    the dedupe window, and a monotonic clock cannot be written into a record
    anyone can read.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        max_comment_chars: int = 600,
        max_bytes: int = 2_000_000,
        duplicate_window_seconds: int = 90,
        api_version: str = "unknown",
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = Path(path)
        self.max_comment_chars = max(1, max_comment_chars)
        self.max_bytes = max(0, max_bytes)
        self.duplicate_window = max(0, duplicate_window_seconds)
        self.api_version = api_version
        self._monotonic = monotonic
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = threading.Lock()
        self._last: tuple[float, tuple[int, str | None]] | None = None
        self._summary_cache: tuple[tuple[int, int], dict[str, object]] | None = None
        self.writes = 0
        self.duplicates = 0

    # -- writing ----------------------------------------------------------
    def submit(self, rating: object, comment: object = None) -> dict[str, object]:
        """Append one submission. Returns what to tell the user.

        Raises `ValueError` for a rating outside the scale and
        `FeedbackUnavailable` when the log cannot take the write. The rating is
        re-checked here rather than trusted from the HTTP layer for the same
        reason `places.validate_coordinates` re-checks coordinates: the Pydantic
        model guards one caller, and this guards every other one.
        """
        value = self._coerce_rating(rating)
        text, truncated = clean_comment(comment, self.max_comment_chars)
        entry = FeedbackEntry(
            id=uuid.uuid4().hex,
            created_at=self._now().replace(microsecond=0).isoformat(),
            rating=value,
            comment=text,
            api_version=self.api_version,
        )

        with self._lock:
            if self._is_repeat(value, text):
                self.duplicates += 1
                return {
                    "stored": False,
                    "duplicate": True,
                    "id": None,
                    "truncated": truncated,
                    "message": COPY["thanks_duplicate"],
                }
            self._append(entry)
            self._last = (self._monotonic(), (value, text))
            self.writes += 1

        return {
            "stored": True,
            "duplicate": False,
            "id": entry.id,
            "truncated": truncated,
            "message": self._thanks(truncated),
        }

    def _thanks(self, truncated: bool) -> str:
        """The sentence for a stored submission, which depends on what was stored.

        Split out so the truncated case cannot be forgotten at one of the two
        return sites: a saved rating whose comment was silently halved is not
        described by "your rating was saved" alone.
        """
        if not truncated:
            return COPY["thanks"]
        return COPY["thanks_truncated"].format(limit=self.max_comment_chars)

    def _coerce_rating(self, raw: object) -> int:
        """`raw` -> a rating on the scale, or ValueError.

        Two conversions are refused rather than performed, because both would
        invent an answer nobody gave. `bool` is rejected before the int
        conversion, since in Python `True` is `1` and would be stored as "Not
        useful" out of a client's type confusion. A fractional float is rejected
        because `int(3.7)` is 3, so a client that had misunderstood the scale
        would silently be recorded as having said "Mixed". An integral float
        (`4.0`) is fine - that is a JSON number, not a fraction.
        """
        if isinstance(raw, bool):
            raise ValueError(f"rating must be an integer {MIN_RATING}-{MAX_RATING}")
        if isinstance(raw, float) and not raw.is_integer():
            raise ValueError(f"rating must be a whole number {MIN_RATING}-{MAX_RATING}")
        try:
            value = int(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ValueError(f"rating must be an integer {MIN_RATING}-{MAX_RATING}") from None
        if value not in RATING_LABELS:
            raise ValueError(f"rating must be between {MIN_RATING} and {MAX_RATING}")
        return value

    def _is_repeat(self, rating: int, comment: str | None) -> bool:
        """Is this the same submission as the last one, within the window?

        Only the immediately preceding submission is remembered, not a set. This
        catches the accident it is for - a double click, or a retry after a
        timeout that had actually succeeded - while leaving a genuine second
        opinion from someone else able to land even if it happens to match.
        """
        if self.duplicate_window == 0 or self._last is None:
            return False
        stamped_at, signature = self._last
        if signature != (rating, comment):
            return False
        return (self._monotonic() - stamped_at) < self.duplicate_window

    def _append(self, entry: FeedbackEntry) -> None:
        """Write one line, or raise `FeedbackUnavailable` with a showable reason.

        The size check is before the write and against the encoded line, so the
        ceiling is never exceeded rather than being noticed afterwards.
        """
        line = entry.as_line().encode("utf-8")
        if self.max_bytes and self.size() + len(line) > self.max_bytes:
            raise FeedbackUnavailable(COPY["full"])
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("ab") as handle:
                handle.write(line)
        except OSError as exc:
            # A read-only volume or a bad FOODAI_FEEDBACK_PATH. The user gets the
            # prepared sentence; the operator gets the real error chained onto it.
            raise FeedbackUnavailable(COPY["unwritable"]) from exc
        self._summary_cache = None

    # -- reading ----------------------------------------------------------
    def size(self) -> int:
        try:
            return self.path.stat().st_size
        except OSError:
            return 0

    def _entries(self) -> Iterator[dict[str, object] | None]:
        """Every record in the log; `None` for a line that could not be read.

        A process killed mid-write leaves a partial last line. Letting that take
        down the summary endpoint would mean one truncated byte range hides every
        rating ever submitted, so bad lines are yielded as `None`, counted, and
        reported - see `unreadable_lines` in `summary`.

        `None` rather than a marker key inside the dict, so that a hand-edited log
        containing that key cannot be mistaken for a parse failure.
        """
        try:
            with self.path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        yield None
                        continue
                    yield record if isinstance(record, dict) else None
        except OSError:
            return

    def summary(self) -> dict[str, object]:
        """Aggregates. Never comment text.

        Comments are written for a maintainer reading the log, not served to
        whoever calls the API: this endpoint is unauthenticated, and free text
        submitted in the expectation of being read by the maintainers is not
        ours to republish. `test_feedback` asserts that a submitted comment
        cannot be found anywhere in this payload.

        Cached on the file's `(size, mtime_ns)`, which changes on every append,
        so the aggregate is recomputed exactly when the file changes and a page
        load does not re-read the whole log.
        """
        try:
            stat = self.path.stat()
            key = (stat.st_size, stat.st_mtime_ns)
        except OSError:
            key = (0, 0)

        cached = self._summary_cache
        if cached is not None and cached[0] == key:
            return dict(cached[1])

        distribution = {value: 0 for value in RATING_LABELS}
        total = 0
        count = 0
        with_comment = 0
        unreadable = 0
        first_at: str | None = None
        last_at: str | None = None

        for record in self._entries():
            if record is None:
                unreadable += 1
                continue
            rating = record.get("rating")
            if isinstance(rating, bool) or not isinstance(rating, int) or rating not in distribution:
                unreadable += 1
                continue
            distribution[rating] += 1
            total += rating
            count += 1
            if record.get("comment"):
                with_comment += 1
            stamp = record.get("created_at")
            if isinstance(stamp, str) and stamp:
                # Min/max rather than first/last line: ISO-8601 UTC sorts
                # lexicographically, and appends are chronological only as long
                # as nobody has concatenated two logs.
                first_at = stamp if first_at is None or stamp < first_at else first_at
                last_at = stamp if last_at is None or stamp > last_at else last_at

        payload: dict[str, object] = {
            "count": count,
            # Rounded to one decimal because the third decimal of a mean of 30
            # opinions is noise dressed as precision.
            "average_rating": round(total / count, 1) if count else None,
            "distribution": {str(value): distribution[value] for value in sorted(distribution)},
            "labels": {str(value): label for value, label in RATING_SCALE},
            "with_comment": with_comment,
            "unreadable_lines": unreadable,
            "first_at": first_at,
            "last_at": last_at,
            "note": COPY["summary_note"],
        }
        self._summary_cache = (key, payload)
        return dict(payload)

    def form(self) -> dict[str, object]:
        """Everything the client needs to draw the form, and its current totals.

        Served rather than hard-coded in the frontend for the same reason as
        /conditions and /cities: the scale, the limit and the privacy note are
        all things the server enforces, and a client copy of an enforced value is
        a client copy that can be wrong. Bundling the totals in here rather than
        making the panel fetch twice keeps a page load at one request.
        """
        return {
            "enabled": True,
            "scale": [{"value": value, "label": label} for value, label in RATING_SCALE],
            "comment_max_chars": self.max_comment_chars,
            "accepting": self.accepting,
            "summary": self.summary(),
            "title": COPY["title"],
            "prompt": COPY["prompt"],
            "comment_prompt": COPY["comment_prompt"],
            "comment_placeholder": COPY["comment_placeholder"],
            "submit": COPY["submit"],
            "privacy_note": COPY["privacy_note"],
            "paused_note": COPY["paused_note"],
        }

    @property
    def accepting(self) -> bool:
        """Is there room for the *largest* submission this store would accept?

        Not "is there room for an average one". The client disables the form on
        this flag, so if it were true while a maximal comment would be refused,
        the form would stay enabled for exactly the people with the most to say
        and then throw their paragraph away. Room is reserved for the envelope
        plus the comment limit at six bytes a character, which is what a
        non-ASCII codepoint costs once `json.dumps` escapes it.
        """
        if not self.max_bytes:
            return True
        worst_case = RECORD_ENVELOPE_BYTES + self.max_comment_chars * 6
        return self.size() + worst_case <= self.max_bytes

    def stats(self) -> dict[str, object]:
        """For GET /health. Counts and paths, no content."""
        return {
            "path": str(self.path),
            "bytes": self.size(),
            "max_bytes": self.max_bytes,
            "accepting": self.accepting,
            "writes_this_process": self.writes,
            "duplicates_this_process": self.duplicates,
            "max_comment_chars": self.max_comment_chars,
            "duplicate_window_seconds": self.duplicate_window,
        }


def disabled_form() -> dict[str, object]:
    """What /feedback returns when collection is switched off.

    A 200 describing a disabled feature, not a 503: the panel needs to render
    *something* honest, and "switched off" is a fact about the server that the
    client can display calmly. The 503 is reserved for POST, where the user has
    actually typed something and needs to know it did not land.
    """
    return {
        "enabled": False,
        "accepting": False,
        "scale": [],
        "note": COPY["disabled_note"],
        "title": COPY["title"],
    }


def store_from_settings(settings: object, api_version: str = "unknown") -> FeedbackStore | None:
    """Build the store, or None when `FOODAI_FEEDBACK_ENABLED=0`.

    None rather than a no-op store, so that "disabled" is visible at every layer
    - /health says `enabled: false`, POST /feedback 503s - instead of a store
    that accepts writes and drops them.
    """
    config = getattr(settings, "feedback", None)
    if config is None or not getattr(config, "enabled", False):
        return None
    return FeedbackStore(
        path=config.path,
        max_comment_chars=config.max_comment_chars,
        max_bytes=config.max_bytes,
        duplicate_window_seconds=config.duplicate_window_seconds,
        api_version=api_version,
    )


__all__ = [
    "COPY",
    "FeedbackEntry",
    "FeedbackStore",
    "FeedbackUnavailable",
    "MAX_RATING",
    "MIN_RATING",
    "RATING_LABELS",
    "RATING_SCALE",
    "clean_comment",
    "disabled_form",
    "store_from_settings",
]
