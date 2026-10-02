"""Tests for docs/decisions.md structural validity.

This is a pure-Python, no-network validator for the JEG-93 decision-queue
log. It does not execute any queued decision and does not touch Linear;
it only asserts that the file the reviewer maintains parses cleanly and
that every entry carries every required key, with parseable dates and
outcomes from the allowed set.

The harness is hermetic by design. A malformed-entry fixture is built
inline (missing `deadline`) so a reviewer can prove the validator
catches the named defect.

Run:
    python3 -m unittest tests.test_decisions_log -v
"""

from __future__ import annotations

import re
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DECISIONS_MD = ROOT / "docs" / "decisions.md"

ALLOWED_OUTCOMES = {"pending", "proceeded", "vetoed", "modified"}
ALLOWED_SILENCE = {"proceed", "explicit-tap"}

# Sections that MUST appear under every entry, in this order.
REQUIRED_SECTIONS = (
    "Context",
    "Problem",
    "Options",
    "Recommendation",
    "Outcome Note",
)

# Front-matter keys every entry must carry.
REQUIRED_KEYS = (
    "id",
    "created",
    "deadline",
    "category",
    "silence-default",
    "outcome",
    "outcome_date",
    "recommendation",
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ENTRY_HEADING_RE = re.compile(r"^##\s+(?P<id>[^:]+):\s*(?P<title>.+?)\s*$")


def _split_entries(text):
    """Yield (heading_match, body_text) pairs for each `## id:` entry.

    The preamble (everything before the first entry) is skipped. The
    comment marker that the format recommends is honored as a no-op.
    """
    lines = text.splitlines()
    entries = []
    current_heading = None
    current_body = []

    def flush():
        if current_heading is not None:
            entries.append((current_heading, "\n".join(current_body)))

    for line in lines:
        m = ENTRY_HEADING_RE.match(line)
        if m:
            flush()
            current_heading = m
            current_body = []
        elif current_heading is not None:
            current_body.append(line)
    flush()
    return entries


def _parse_front_matter(body):
    """Return (dict, body_after_front_matter).

    Front matter is the leading contiguous run of `- key: value` lines
    (each line starts with "- "). The first non-front-matter line starts
    the body. Keys with empty values (`- key:`) are accepted as present
    but flagged downstream if they are required.
    """
    fm = {}
    lines = body.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("- "):
            break
        rest = line[2:]
        if ":" not in rest:
            raise ValueError(
                f"front-matter line missing ':' separator: {line!r}"
            )
        key, value = rest.split(":", 1)
        fm[key.strip()] = value.strip()
        i += 1
    return fm, "\n".join(lines[i:])


def _parse_sections(body):
    """Return ordered list of (section_name, section_body)."""
    sections = []
    current_name = None
    current_body = []

    def flush():
        if current_name is not None:
            sections.append((current_name, "\n".join(current_body)))

    for line in body.splitlines():
        m = re.match(r"^###\s+(?P<name>.+?)\s*$", line)
        if m:
            flush()
            current_name = m.group("name").strip()
            current_body = []
        elif current_name is not None:
            current_body.append(line)
    flush()
    return sections


def _format_entry(entry_id, title, *, missing=(), **overrides):
    """Render a minimal entry for fixture use.

    `missing` is an iterable of required keys to omit (so the fixture
    can prove it catches the omission). `overrides` lets tests tweak
    individual keys.
    """
    keys = {k: overrides.get(k, "") for k in REQUIRED_KEYS}
    for k in missing:
        keys.pop(k, None)

    lines = [f"## {entry_id}: {title}", ""]
    for k in REQUIRED_KEYS:
        if k in keys:
            lines.append(f"- {k}: {keys[k]}")
    lines.append("")
    for section in REQUIRED_SECTIONS:
        lines.append(f"### {section}")
        lines.append("")
        lines.append(f"Filler body for {section}.")
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class DecisionsLogValidator:
    """Pure-Python structural validator. Returns list of error strings."""

    def __init__(self, text):
        self.text = text

    def errors(self):
        errs = []
        entries = _split_entries(self.text)
        if not entries:
            # Empty queue is valid: no entries have been queued yet.
            return errs

        seen_ids = set()
        for heading, body in entries:
            entry_id = heading.group("id").strip()
            errs.extend(self._errors_for_entry(entry_id, body))
            if entry_id in seen_ids:
                errs.append(f"duplicate entry id: {entry_id}")
            seen_ids.add(entry_id)

        return errs

    def _errors_for_entry(self, entry_id, body):
        errs = []
        try:
            fm, after = _parse_front_matter(body)
        except ValueError as exc:
            return [f"entry {entry_id}: {exc}"]

        for key in REQUIRED_KEYS:
            if key not in fm:
                errs.append(
                    f"entry {entry_id}: missing required front-matter "
                    f"key {key!r}"
                )

        # Date parses.
        for dkey in ("created", "deadline", "outcome_date"):
            val = fm.get(dkey, "")
            if dkey in fm and val and not DATE_RE.match(val):
                errs.append(
                    f"entry {entry_id}: {dkey!r}={val!r} is not YYYY-MM-DD"
                )

        # Deadline is on-or-after created.
        created = fm.get("created", "")
        deadline = fm.get("deadline", "")
        if (
            created
            and deadline
            and DATE_RE.match(created)
            and DATE_RE.match(deadline)
        ):
            if date.fromisoformat(deadline) < date.fromisoformat(created):
                errs.append(
                    f"entry {entry_id}: deadline {deadline} is before "
                    f"created {created}"
                )

        # Outcome from allowed set.
        outcome = fm.get("outcome", "")
        if outcome and outcome not in ALLOWED_OUTCOMES:
            errs.append(
                f"entry {entry_id}: outcome {outcome!r} not in "
                f"{sorted(ALLOWED_OUTCOMES)}"
            )

        # Silence-default from allowed set.
        silence = fm.get("silence-default", "")
        if silence and silence not in ALLOWED_SILENCE:
            errs.append(
                f"entry {entry_id}: silence-default {silence!r} not in "
                f"{sorted(ALLOWED_SILENCE)}"
            )

        # methodology / copy / publish must be explicit-tap.
        category = fm.get("category", "")
        if category in {"methodology", "copy", "publish"}:
            if silence != "explicit-tap":
                errs.append(
                    f"entry {entry_id}: category {category!r} must use "
                    f"silence-default=explicit-tap"
                )

        # Required sections in order.
        sections = [name for name, _ in _parse_sections(after)]
        idx = 0
        for required in REQUIRED_SECTIONS:
            try:
                next_idx = sections.index(required, idx)
            except ValueError:
                errs.append(
                    f"entry {entry_id}: missing required section "
                    f"### {required}"
                )
                # Don't advance; downstream section checks stay meaningful.
                continue
            if next_idx != idx:
                errs.append(
                    f"entry {entry_id}: section ### {required} out of "
                    f"order"
                )
            idx = next_idx + 1

        # Outcome Note must be non-empty when outcome != pending.
        if outcome and outcome != "pending":
            sections_dict = {
                name: body for name, body in _parse_sections(after)
            }
            note = sections_dict.get("Outcome Note", "").strip()
            if not note:
                errs.append(
                    f"entry {entry_id}: outcome {outcome!r} requires a "
                    f"non-empty `### Outcome Note`"
                )

        return errs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class GoodEntryFixture(unittest.TestCase):
    """A hand-written entry must validate cleanly."""

    ENTRY = _format_entry(
        "jeg-93-001",
        "USA Today native drift — refresh or accept",
        id="jeg-93-001",
        created="2026-10-02",
        deadline="2026-10-09",
        category="native-drift",
        silence_default="proceed",
        outcome="pending",
        outcome_date="",
        recommendation=(
            "DRAFT: refresh the USA Today half_12 snapshot via the "
            "documented puller, then re-run the cascade and review."
        ),
    )

    def test_good_entry_validates(self):
        errs = DecisionsLogValidator(self.ENTRY).errors()
        self.assertEqual(errs, [], msg=f"unexpected errors: {errs}")


class MalformedEntryFixture(unittest.TestCase):
    """The acceptance contract requires a missing-deadline entry that
    fails validation. This fixture asserts both that it is parsed and
    that the validator names the missing key."""

    ENTRY = _format_entry(
        "jeg-93-bad",
        "Fixture missing deadline — must fail",
        missing=("deadline",),
        id="jeg-93-bad",
        created="2026-10-02",
        category="native-drift",
        silence_default="proceed",
        outcome="pending",
        outcome_date="",
        recommendation="DRAFT: this entry is intentionally broken.",
    )

    def test_missing_deadline_is_caught(self):
        errs = DecisionsLogValidator(self.ENTRY).errors()
        self.assertTrue(
            any("'deadline'" in e for e in errs),
            msg=f"expected missing-deadline error, got: {errs}",
        )

    def test_missing_deadline_entry_is_not_silent(self):
        errs = DecisionsLogValidator(self.ENTRY).errors()
        self.assertTrue(errs, msg="validator must report at least one error")


class RealDecisionsFileTests(unittest.TestCase):
    """The committed docs/decisions.md file must parse cleanly.

    `docs/decisions.md` is the format spec itself: the file currently
    contains only the preamble, which is the format declaration and the
    queue rules. No entries yet. The validator must accept that state
    (zero entries is allowed; the queue starts empty).
    """

    def test_committed_file_parses(self):
        text = DECISIONS_MD.read_text(encoding="utf-8")
        # Either zero entries (queue empty) or every entry validates.
        entries = _split_entries(text)
        if not entries:
            self.assertEqual(
                DecisionsLogValidator(text).errors(), [],
                msg="empty queue must validate as zero entries"
            )
        else:
            errs = DecisionsLogValidator(text).errors()
            self.assertEqual(errs, [], msg=f"errors: {errs}")

    def test_preamble_section_order_marker_present(self):
        text = DECISIONS_MD.read_text(encoding="utf-8")
        # Format spec must declare the queue rules from JEG-93 so the
        # reviewer can see what they are agreeing to.
        self.assertIn("Silence by the deadline", text)
        self.assertIn("explicit-tap", text)
        self.assertIn("methodology", text.lower())
        self.assertIn("copy", text.lower())
        self.assertIn("publish", text.lower())


class EndToEndRoundTripTests(unittest.TestCase):
    """Round-trip checks across the full grammar: write, validate, modify,
    re-validate. Catches regressions in the section parser."""

    def _render(self, **overrides):
        merged = dict(
            id="jeg-93-rt",
            created="2026-10-02",
            deadline="2026-10-09",
            category="native-drift",
            silence_default="proceed",
            outcome="pending",
            outcome_date="",
            recommendation="DRAFT: round-trip fixture.",
        )
        merged.update(overrides)
        return _format_entry(
            "jeg-93-rt",
            "Round-trip fixture",
            **merged,
        )

    def test_outcome_must_be_allowed_value(self):
        text = self._render(outcome="yolo")
        errs = DecisionsLogValidator(text).errors()
        self.assertTrue(
            any("outcome 'yolo'" in e for e in errs),
            msg=f"expected outcome error, got: {errs}",
        )

    def test_outcome_must_have_note_when_closed(self):
        text = self._render(outcome="proceeded", outcome_date="2026-10-09")
        # The fixture's Outcome Note is the default filler, which is
        # non-empty, so this must validate. Then we blank it out and
        # re-check.
        self.assertEqual(DecisionsLogValidator(text).errors(), [])
        blanked = text.replace(
            "Filler body for Outcome Note.", ""
        )
        errs = DecisionsLogValidator(blanked).errors()
        self.assertTrue(
            any("Outcome Note" in e for e in errs),
            msg=f"expected Outcome Note error, got: {errs}",
        )

    def test_methodology_requires_explicit_tap(self):
        text = self._render(
            category="methodology", silence_default="proceed"
        )
        errs = DecisionsLogValidator(text).errors()
        self.assertTrue(
            any("explicit-tap" in e for e in errs),
            msg=f"expected explicit-tap enforcement, got: {errs}",
        )

    def test_methodology_with_explicit_tap_validates(self):
        text = self._render(
            category="methodology", silence_default="explicit-tap"
        )
        errs = DecisionsLogValidator(text).errors()
        self.assertEqual(errs, [], msg=f"unexpected errors: {errs}")

    def test_deadline_before_created_rejected(self):
        text = self._render(created="2026-10-09", deadline="2026-10-02")
        errs = DecisionsLogValidator(text).errors()
        self.assertTrue(
            any("deadline" in e and "before" in e for e in errs),
            msg=f"expected date-order error, got: {errs}",
        )

    def test_malformed_date_rejected(self):
        text = self._render(created="10/02/2026")
        errs = DecisionsLogValidator(text).errors()
        self.assertTrue(
            any("created" in e and "YYYY-MM-DD" in e for e in errs),
            msg=f"expected date-format error, got: {errs}",
        )

    def test_duplicate_ids_caught(self):
        a = self._render()
        b = self._render()
        combined = a + "\n" + b
        errs = DecisionsLogValidator(combined).errors()
        self.assertTrue(
            any("duplicate" in e for e in errs),
            msg=f"expected duplicate-id error, got: {errs}",
        )

    def test_section_out_of_order_caught(self):
        text = self._render()
        # Swap Problem and Context so Problem comes first.
        swapped = (
            text.replace("### Context", "### CONTEXT_TMP")
            .replace("### Problem", "### Context")
            .replace("### CONTEXT_TMP", "### Problem")
        )
        errs = DecisionsLogValidator(swapped).errors()
        self.assertTrue(
            any("out of order" in e for e in errs),
            msg=f"expected order error, got: {errs}",
        )


class DraftFilesRoundTrip(unittest.TestCase):
    """The three drafts in docs/decisions/drafts/ must validate too.

    Each draft follows the entry format but is explicitly marked
    DRAFT in the recommendation. Their `outcome` is `pending` and
    their `silence-default` follows the queue rule for their category.
    """

    DRAFTS = ROOT / "docs" / "decisions" / "drafts"

    def _read(self, name):
        return (self.DRAFTS / name).read_text(encoding="utf-8")

    def test_each_draft_validates(self):
        for name in (
            "usatoday-drift.md",
            "fantasypros-half12-drift.md",
            "prediction-markets-leg.md",
        ):
            with self.subTest(draft=name):
                text = self._read(name)
                errs = DecisionsLogValidator(text).errors()
                self.assertEqual(
                    errs, [], msg=f"{name}: {errs}"
                )

    def test_each_draft_is_marked_DRAFT(self):
        for name in (
            "usatoday-drift.md",
            "fantasypros-half12-drift.md",
            "prediction-markets-leg.md",
        ):
            with self.subTest(draft=name):
                text = self._read(name)
                self.assertIn(
                    "DRAFT:", text,
                    msg=f"{name}: recommendation must start with DRAFT:",
                )


if __name__ == "__main__":
    unittest.main()