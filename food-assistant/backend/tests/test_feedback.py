"""Tests for the feedback log.

Stdlib only, no network, no server: `FeedbackStore` takes a path and two clocks,
so every one of these runs against a real file in a temporary directory with time
under the test's control. Nothing here sleeps.

Three properties are load-bearing enough to be tested from more than one angle.
A comment must never come back out of the summary endpoint. A comment containing
newlines must not be able to forge a second record in a line-delimited file. And
"not stored" must never be reported to the user as "stored" - which is why the
refusal paths are tested for their message as well as their outcome.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.feedback import (
    COPY,
    MAX_RATING,
    MIN_RATING,
    RATING_LABELS,
    RATING_SCALE,
    FeedbackEntry,
    FeedbackStore,
    FeedbackUnavailable,
    clean_comment,
    disabled_form,
    store_from_settings,
)


class FakeClock:
    """A monotonic clock the test advances by hand."""

    def __init__(self, start: float = 1000.0) -> None:
        self.value = start

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


class StoreCase(unittest.TestCase):
    """Base: a store writing into a fresh temporary directory."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.clock = FakeClock()

    def store(self, **kwargs) -> FeedbackStore:
        options: dict = {
            "path": self.dir / "feedback.jsonl",
            "monotonic": self.clock,
            "api_version": "3.0",
        }
        options.update(kwargs)
        return FeedbackStore(**options)

    def lines(self, store: FeedbackStore) -> list[dict]:
        text = store.path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]


class TestTheScale(unittest.TestCase):
    def test_the_scale_is_the_bounds(self) -> None:
        """The advertised range and the accepted range are one definition."""
        values = [value for value, _ in RATING_SCALE]
        self.assertEqual(values, list(range(MIN_RATING, MAX_RATING + 1)))
        self.assertEqual(set(RATING_LABELS), set(values))

    def test_every_point_has_a_distinct_label(self) -> None:
        labels = [label for _, label in RATING_SCALE]
        self.assertEqual(len(set(labels)), len(labels))
        self.assertTrue(all(label.strip() for label in labels))

    def test_the_scale_has_a_real_middle(self) -> None:
        """An odd scale, so "some good some bad" is sayable rather than rounded."""
        self.assertEqual(len(RATING_SCALE) % 2, 1)


class TestCommentCleaning(unittest.TestCase):
    def test_absent_blank_and_whitespace_all_become_none(self) -> None:
        """One representation of "no comment", not four."""
        for raw in (None, "", "   ", "\t\n  \n"):
            with self.subTest(raw=raw):
                self.assertEqual(clean_comment(raw, 100), (None, False))

    def test_surrounding_whitespace_is_stripped(self) -> None:
        self.assertEqual(clean_comment("  too spicy  ", 100), ("too spicy", False))

    def test_newlines_and_tabs_survive(self) -> None:
        """People type these deliberately; JSON encoding makes them safe."""
        comment, truncated = clean_comment("line one\nline two\tindented", 100)
        self.assertEqual(comment, "line one\nline two\tindented")
        self.assertFalse(truncated)

    def test_other_control_characters_are_dropped(self) -> None:
        comment, _ = clean_comment("bell\x07null\x00escape\x1b", 100)
        self.assertEqual(comment, "bellnullescape")

    def test_a_long_comment_is_truncated_not_rejected(self) -> None:
        comment, truncated = clean_comment("x" * 50, 10)
        self.assertEqual(comment, "x" * 10)
        self.assertTrue(truncated)

    def test_a_comment_at_the_limit_is_not_flagged(self) -> None:
        comment, truncated = clean_comment("x" * 10, 10)
        self.assertEqual(comment, "x" * 10)
        self.assertFalse(truncated)

    def test_non_strings_do_not_raise(self) -> None:
        """A client sending a number should not 500 the endpoint."""
        self.assertEqual(clean_comment(42, 100), ("42", False))


class TestRatingValidation(StoreCase):
    def test_every_point_on_the_scale_is_accepted(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        for value in RATING_LABELS:
            with self.subTest(rating=value):
                self.assertIs(store.submit(value)["stored"], True)
        self.assertEqual(len(self.lines(store)), len(RATING_LABELS))

    def test_out_of_range_ratings_are_refused(self) -> None:
        store = self.store()
        for value in (0, -1, 6, 99):
            with self.subTest(rating=value):
                with self.assertRaises(ValueError):
                    store.submit(value)

    def test_unparseable_ratings_are_refused(self) -> None:
        store = self.store()
        for value in (None, "", "four", "3.7", [], {}):
            with self.subTest(rating=value):
                with self.assertRaises(ValueError):
                    store.submit(value)

    def test_booleans_are_refused_rather_than_read_as_one(self) -> None:
        """`True == 1` in Python, so a type-confused client must not score a 1."""
        store = self.store()
        for value in (True, False):
            with self.subTest(rating=value):
                with self.assertRaises(ValueError):
                    store.submit(value)

    def test_a_fractional_rating_is_refused_not_floored(self) -> None:
        """`int(3.7)` is 3, which would record an opinion nobody expressed."""
        store = self.store()
        for value in (3.7, 0.5, 4.99):
            with self.subTest(rating=value):
                with self.assertRaises(ValueError):
                    store.submit(value)
        self.assertFalse(store.path.exists())

    def test_a_whole_float_is_accepted(self) -> None:
        """JSON has one number type; 4.0 is a 4, not a fraction."""
        store = self.store()
        self.assertIs(store.submit(4.0)["stored"], True)
        self.assertEqual(self.lines(store)[0]["rating"], 4)

    def test_a_numeric_string_is_accepted(self) -> None:
        """Form encodings deliver "4"; that is a rating, not a client bug."""
        store = self.store()
        self.assertIs(store.submit("4")["stored"], True)
        self.assertEqual(self.lines(store)[0]["rating"], 4)

    def test_a_refused_rating_writes_nothing(self) -> None:
        store = self.store()
        with self.assertRaises(ValueError):
            store.submit(9)
        self.assertFalse(store.path.exists())


class TestWriting(StoreCase):
    def test_a_submission_lands_as_one_json_line(self) -> None:
        store = self.store()
        result = store.submit(5, "excellent")
        self.assertIs(result["stored"], True)
        self.assertEqual(result["message"], COPY["thanks"])
        records = self.lines(store)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["rating"], 5)
        self.assertEqual(records[0]["comment"], "excellent")
        self.assertEqual(records[0]["id"], result["id"])

    def test_submissions_append_rather_than_overwrite(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        store.submit(1)
        store.submit(5)
        self.assertEqual([r["rating"] for r in self.lines(store)], [1, 5])

    def test_the_api_version_travels_with_the_rating(self) -> None:
        """A 2-star is uninterpretable without knowing which ranking earned it."""
        store = self.store(api_version="9.9")
        store.submit(2)
        self.assertEqual(self.lines(store)[0]["api_version"], "9.9")

    def test_no_comment_is_stored_as_null(self) -> None:
        store = self.store()
        store.submit(3)
        self.assertIsNone(self.lines(store)[0]["comment"])

    def test_ids_are_unique(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        ids = {store.submit(3)["id"] for _ in range(20)}
        self.assertEqual(len(ids), 20)

    def test_the_timestamp_is_utc_and_second_resolution(self) -> None:
        store = self.store()
        store.submit(4)
        stamp = self.lines(store)[0]["created_at"]
        self.assertIn("+00:00", stamp)
        self.assertNotIn(".", stamp)

    def test_a_missing_parent_directory_is_created(self) -> None:
        store = self.store(path=self.dir / "nested" / "deeper" / "feedback.jsonl")
        store.submit(4)
        self.assertTrue(store.path.exists())

    def test_a_multiline_comment_cannot_forge_a_second_record(self) -> None:
        """The property JSONL rests on: one submission is always one line."""
        store = self.store()
        store.submit(1, 'bad\n{"rating": 5, "comment": "great"}')
        raw = store.path.read_text(encoding="utf-8")
        self.assertEqual(len(raw.strip().splitlines()), 1)
        records = self.lines(store)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["rating"], 1)
        self.assertEqual(store.summary()["count"], 1)

    def test_a_comment_beyond_the_limit_is_stored_truncated(self) -> None:
        store = self.store(max_comment_chars=20)
        result = store.submit(3, "y" * 100)
        self.assertIs(result["stored"], True)
        self.assertIs(result["truncated"], True)
        self.assertEqual(self.lines(store)[0]["comment"], "y" * 20)

    def test_a_truncated_comment_is_admitted_to_in_the_message(self) -> None:
        """A thanks that ignores a halved comment is a quiet half-truth.

        The client renders `message` verbatim, so this sentence is the only place
        the loss can be reported. It names the limit, because "shortened" without
        a number gives the person nothing to act on.
        """
        store = self.store(max_comment_chars=20)
        message = store.submit(3, "y" * 100)["message"]
        self.assertNotEqual(message, COPY["thanks"])
        self.assertIn("20", message)

    def test_an_untruncated_comment_gets_the_plain_thanks(self) -> None:
        """The admission must not appear when there was nothing to admit."""
        store = self.store(max_comment_chars=20)
        self.assertEqual(store.submit(3, "short")["message"], COPY["thanks"])

    def test_non_ascii_comments_survive_the_round_trip(self) -> None:
        store = self.store()
        store.submit(5, "ලස්සන")
        self.assertEqual(self.lines(store)[0]["comment"], "ලස්සන")


class TestDuplicateWindow(StoreCase):
    def test_an_immediate_repeat_is_not_written_twice(self) -> None:
        """The realistic accident: a double click, or a retry that had worked."""
        store = self.store(duplicate_window_seconds=90)
        store.submit(4, "good")
        result = store.submit(4, "good")
        self.assertIs(result["stored"], False)
        self.assertIs(result["duplicate"], True)
        self.assertIsNone(result["id"])
        self.assertEqual(len(self.lines(store)), 1)

    def test_a_duplicate_says_so_rather_than_claiming_a_save(self) -> None:
        store = self.store()
        store.submit(4, "good")
        self.assertEqual(store.submit(4, "good")["message"], COPY["thanks_duplicate"])
        self.assertNotEqual(COPY["thanks_duplicate"], COPY["thanks"])

    def test_the_same_rating_lands_once_the_window_has_passed(self) -> None:
        store = self.store(duplicate_window_seconds=90)
        store.submit(4, "good")
        self.clock.advance(91)
        self.assertIs(store.submit(4, "good")["stored"], True)
        self.assertEqual(len(self.lines(store)), 2)

    def test_a_different_rating_is_never_a_duplicate(self) -> None:
        store = self.store()
        store.submit(4, "good")
        self.assertIs(store.submit(5, "good")["stored"], True)

    def test_a_different_comment_is_never_a_duplicate(self) -> None:
        store = self.store()
        store.submit(4, "good")
        self.assertIs(store.submit(4, "also good")["stored"], True)

    def test_only_the_previous_submission_is_compared(self) -> None:
        """So a genuine second opinion still lands after someone else's."""
        store = self.store()
        store.submit(4, "good")
        store.submit(1, "bad")
        self.assertIs(store.submit(4, "good")["stored"], True)
        self.assertEqual(len(self.lines(store)), 3)

    def test_a_zero_window_disables_deduplication(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        store.submit(4, "good")
        self.assertIs(store.submit(4, "good")["stored"], True)


class TestSizeCeiling(StoreCase):
    def test_writes_are_refused_once_the_ceiling_is_reached(self) -> None:
        """An unauthenticated append endpoint must not be able to fill a disk."""
        store = self.store(max_bytes=200, duplicate_window_seconds=0)
        written = 0
        for _ in range(50):
            try:
                store.submit(3, "padding text to use up the budget")
            except FeedbackUnavailable:
                break
            written += 1
        self.assertGreater(written, 0)
        self.assertLessEqual(store.size(), 200)

    def test_the_ceiling_is_never_exceeded_even_by_one_line(self) -> None:
        store = self.store(max_bytes=1, duplicate_window_seconds=0)
        with self.assertRaises(FeedbackUnavailable):
            store.submit(3)
        self.assertFalse(store.path.exists())

    def test_a_refusal_says_nothing_was_stored(self) -> None:
        store = self.store(max_bytes=1)
        with self.assertRaises(FeedbackUnavailable) as caught:
            store.submit(3, "a careful paragraph")
        self.assertEqual(str(caught.exception), COPY["full"])
        self.assertIn("not", str(caught.exception).lower())

    def test_accepting_never_promises_room_it_does_not_have(self) -> None:
        """You must never be refused while the form was advertised as open."""
        store = self.store(max_bytes=4000, max_comment_chars=40, duplicate_window_seconds=0)
        self.assertTrue(store.accepting)
        refused_while_accepting = False
        for _ in range(400):
            if not store.accepting:
                break
            try:
                store.submit(3, "x" * 40)
            except FeedbackUnavailable:
                refused_while_accepting = True
                break
        self.assertFalse(refused_while_accepting)
        self.assertFalse(store.accepting)

    def test_a_zero_ceiling_means_unbounded(self) -> None:
        store = self.store(max_bytes=0, duplicate_window_seconds=0)
        store.submit(3)
        self.assertTrue(store.accepting)

    def test_an_unwritable_path_is_reported_not_raised_raw(self) -> None:
        """A directory where a file should be: the user still gets a sentence."""
        blocked = self.dir / "blocked"
        blocked.mkdir()
        store = self.store(path=blocked)
        with self.assertRaises(FeedbackUnavailable) as caught:
            store.submit(3)
        self.assertEqual(str(caught.exception), COPY["unwritable"])


class TestSummary(StoreCase):
    def test_an_empty_log_is_an_empty_summary_not_an_error(self) -> None:
        summary = self.store().summary()
        self.assertEqual(summary["count"], 0)
        self.assertIsNone(summary["average_rating"])
        self.assertIsNone(summary["first_at"])
        self.assertEqual(sum(summary["distribution"].values()), 0)

    def test_the_distribution_counts_every_rating(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        for value in (5, 5, 4, 1):
            store.submit(value)
        summary = store.summary()
        self.assertEqual(summary["count"], 4)
        self.assertEqual(summary["distribution"]["5"], 2)
        self.assertEqual(summary["distribution"]["4"], 1)
        self.assertEqual(summary["distribution"]["1"], 1)
        self.assertEqual(summary["distribution"]["3"], 0)

    def test_the_distribution_lists_every_point_even_at_zero(self) -> None:
        """A missing key would render as a gap in the client's bar chart."""
        store = self.store()
        store.submit(3)
        self.assertEqual(set(store.summary()["distribution"]), {"1", "2", "3", "4", "5"})

    def test_the_average_is_rounded_to_one_decimal(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        for value in (5, 4, 4):
            store.submit(value)
        self.assertEqual(store.summary()["average_rating"], 4.3)

    def test_comments_are_counted_not_returned(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        store.submit(2, "the kottu suggestions were wrong")
        store.submit(4)
        summary = store.summary()
        self.assertEqual(summary["with_comment"], 1)
        self.assertNotIn("kottu", json.dumps(summary))

    def test_no_submitted_text_appears_anywhere_in_the_summary(self) -> None:
        """The whole payload, not just a `comments` key that does not exist."""
        store = self.store(duplicate_window_seconds=0)
        secret = "zqxjkv-unmistakable-phrase"
        store.submit(1, secret)
        self.assertNotIn(secret, json.dumps(store.summary()))
        self.assertNotIn(secret, json.dumps(store.form()))
        self.assertNotIn(secret, json.dumps(store.stats()))

    def test_the_timestamps_span_the_log(self) -> None:
        store = self.store(duplicate_window_seconds=0)
        store.submit(3)
        store.submit(4)
        summary = store.summary()
        self.assertIsNotNone(summary["first_at"])
        self.assertLessEqual(summary["first_at"], summary["last_at"])

    def test_a_truncated_last_line_does_not_hide_the_rest(self) -> None:
        """A process killed mid-write must not take the endpoint down."""
        store = self.store(duplicate_window_seconds=0)
        store.submit(5)
        with store.path.open("a", encoding="utf-8") as handle:
            handle.write('{"rating": 4, "comm')
        summary = store.summary()
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["unreadable_lines"], 1)

    def test_a_record_with_a_nonsense_rating_is_counted_as_unreadable(self) -> None:
        store = self.store()
        store.path.write_text('{"rating": 11}\n{"rating": "x"}\n', encoding="utf-8")
        summary = store.summary()
        self.assertEqual(summary["count"], 0)
        self.assertEqual(summary["unreadable_lines"], 2)

    def test_blank_lines_are_ignored_entirely(self) -> None:
        store = self.store()
        store.submit(4)
        with store.path.open("a", encoding="utf-8") as handle:
            handle.write("\n\n")
        summary = store.summary()
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["unreadable_lines"], 0)

    def test_the_summary_updates_after_a_new_submission(self) -> None:
        """The cache is keyed on the file, so an append must invalidate it."""
        store = self.store(duplicate_window_seconds=0)
        store.submit(3)
        self.assertEqual(store.summary()["count"], 1)
        store.submit(3)
        self.assertEqual(store.summary()["count"], 2)

    def test_the_summary_is_a_copy_callers_cannot_corrupt(self) -> None:
        store = self.store()
        store.submit(3)
        first = store.summary()
        first["count"] = 999
        self.assertEqual(store.summary()["count"], 1)

    def test_a_second_store_reads_what_the_first_wrote(self) -> None:
        """Counts survive a restart, which is the point of a file."""
        first = self.store()
        first.submit(5, "kept")
        self.assertEqual(self.store().summary()["count"], 1)


class TestForm(StoreCase):
    def test_the_form_carries_the_scale_the_store_enforces(self) -> None:
        form = self.store().form()
        self.assertEqual(
            [point["value"] for point in form["scale"]], [value for value, _ in RATING_SCALE]
        )
        self.assertEqual(
            [point["label"] for point in form["scale"]], [label for _, label in RATING_SCALE]
        )

    def test_the_form_states_the_comment_limit_it_will_apply(self) -> None:
        store = self.store(max_comment_chars=123)
        self.assertEqual(store.form()["comment_max_chars"], 123)

    def test_the_form_carries_the_privacy_note(self) -> None:
        """The promise has to come from the code that does the storing."""
        note = self.store().form()["privacy_note"]
        self.assertIn("no IP address", note)
        self.assertTrue(note.strip())

    def test_the_form_includes_the_totals_so_far(self) -> None:
        """Bundled here so a page load costs one request, not two."""
        store = self.store()
        store.submit(4)
        self.assertEqual(store.form()["summary"]["count"], 1)

    def test_an_enabled_form_says_so(self) -> None:
        form = self.store().form()
        self.assertIs(form["enabled"], True)
        self.assertIs(form["accepting"], True)

    def test_every_string_the_client_renders_is_present(self) -> None:
        """A missing key would render as an empty label rather than a crash."""
        form = self.store().form()
        for key in (
            "title",
            "prompt",
            "comment_prompt",
            "comment_placeholder",
            "submit",
            "paused_note",
        ):
            with self.subTest(key=key):
                self.assertTrue(str(form[key]).strip())

    def test_the_paused_note_is_sent_before_it_is_needed(self) -> None:
        """The client owns no copy of its own, so this ships on every form.

        Sent unconditionally rather than only when `accepting` is false: the
        alternative is a panel that has to invent a sentence in the one state
        where it has to be exactly right about whether anything was saved.
        """
        note = self.store().form()["paused_note"]
        self.assertIn("paused", note)
        self.assertEqual(self.store(max_bytes=1).form()["paused_note"], note)

    def test_a_full_log_advertises_that_it_is_not_accepting(self) -> None:
        store = self.store(max_bytes=500, max_comment_chars=40)
        store.path.write_text("x" * 600, encoding="utf-8")
        self.assertIs(store.form()["accepting"], False)
        # Still `enabled`: the feature is on, this server has simply run out of
        # room. The panel needs to tell those two apart.
        self.assertIs(store.form()["enabled"], True)


class TestDisabled(unittest.TestCase):
    def test_the_disabled_form_is_a_description_not_an_error(self) -> None:
        form = disabled_form()
        self.assertIs(form["enabled"], False)
        self.assertIs(form["accepting"], False)
        self.assertEqual(form["scale"], [])

    def test_the_disabled_form_explains_why_it_is_empty(self) -> None:
        self.assertEqual(disabled_form()["note"], COPY["disabled_note"])
        self.assertIn("switched off", COPY["disabled_note"])

    def test_a_disabled_setting_yields_no_store_rather_than_a_silent_one(self) -> None:
        """None, so "off" is visible at every layer instead of writes vanishing."""

        class Config:
            enabled = False
            path = "unused.jsonl"
            max_comment_chars = 600
            max_bytes = 1000
            duplicate_window_seconds = 90

        class Settings:
            feedback = Config()

        self.assertIsNone(store_from_settings(Settings()))

    def test_an_enabled_setting_yields_a_configured_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            class Config:
                enabled = True
                path = str(Path(tmp) / "f.jsonl")
                max_comment_chars = 77
                max_bytes = 4242
                duplicate_window_seconds = 5

            class Settings:
                feedback = Config()

            store = store_from_settings(Settings(), api_version="1.2")
            self.assertIsNotNone(store)
            assert store is not None
            self.assertEqual(store.max_comment_chars, 77)
            self.assertEqual(store.max_bytes, 4242)
            self.assertEqual(store.duplicate_window, 5)
            self.assertEqual(store.api_version, "1.2")

    def test_settings_without_a_feedback_block_yield_no_store(self) -> None:
        self.assertIsNone(store_from_settings(object()))


class TestEntry(unittest.TestCase):
    def test_a_line_is_valid_json_ending_in_a_newline(self) -> None:
        entry = FeedbackEntry("abc", "2026-01-01T00:00:00+00:00", 4, "fine", "3.0")
        line = entry.as_line()
        self.assertTrue(line.endswith("\n"))
        self.assertEqual(json.loads(line)["id"], "abc")

    def test_an_entry_cannot_be_edited_after_it_is_written(self) -> None:
        entry = FeedbackEntry("abc", "2026-01-01T00:00:00+00:00", 4, None, "3.0")
        with self.assertRaises(Exception):
            entry.rating = 5  # type: ignore[misc]


class TestStats(StoreCase):
    def test_stats_report_counts_and_never_content(self) -> None:
        store = self.store(duplicate_window_seconds=90)
        store.submit(4, "distinctive-comment-text")
        store.submit(4, "distinctive-comment-text")
        stats = store.stats()
        self.assertEqual(stats["writes_this_process"], 1)
        self.assertEqual(stats["duplicates_this_process"], 1)
        self.assertGreater(stats["bytes"], 0)
        self.assertNotIn("distinctive-comment-text", json.dumps(stats))

    def test_stats_expose_the_path_for_the_operator(self) -> None:
        store = self.store()
        self.assertEqual(store.stats()["path"], str(store.path))


if __name__ == "__main__":
    unittest.main()
