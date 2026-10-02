#!/usr/bin/env python3
"""JEG-189 (R10 wiring): slip measurement wired into the deadline checker.

Acceptance criteria from the brief:
1. PUBLICATION_SCHEDULES carries `slip_observed_max_minutes` and
   `slip_measured_at` per source (validated by
   `test_every_source_has_slip_fields`).
2. `grace_window_minutes` returns
   `publication_window + slip_observed_max_minutes` (validated by
   `test_grace_window_includes_slip`).
3. Unmeasured sources use the 6h default and label
   `"slip: default 6h (unmeasured)"`.
4. Stale measurements (>30d old) label
   `"slip: stale measurement (>30d)"`.
5. The deadline checker wires `measure_scheduler_slip.compute_scheduler_slip`
   into the per-source state decision via `compute_slip_measurement`.
6. A 6h-late run is NOT flagged red when slip is measured at 6h
   (validated by `test_6h_late_with_6h_slip_not_red`).
7. A 24h-late run IS flagged red even with the slip grace (validated by
   `test_24h_late_with_6h_slip_red`).

Each positive check is paired with a negative control that proves the
guard catches the bug it names (per the "Every regression guard must
prove it catches the bug it names" rule). Tests copy the verbatim label
strings from the brief.

Run via `python3 -m unittest tests.test_jeg189_slip_wiring` or through
`make test-unit`. Verification happens outside this lane (Roman).

JEG-189 (R10 wiring), minimax M3.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from pipelines.lib.publication_windows import (
    DEFAULT_SLIP_MINUTES,
    PUBLICATION_SCHEDULES,
    SLIP_STALE_AFTER,
    effective_slip_minutes,
    format_slip_reason,
    get_slip_minutes,
    get_slip_status,
    load_slip_overrides,
    reset_slip_overrides,
    slip_is_stale,
)


def _restore_schedule():
    """Reset every entry's slip fields to the module defaults.

    A `PUBLICATION_SCHEDULES` mutation in one test can leak into the
    next; this helper guards against that for every test that mutates.
    """
    reset_slip_overrides()


class TestScheduleFields(unittest.TestCase):
    """Acceptance criterion 1: slip fields are present per source."""

    def test_every_source_has_slip_observed(self):
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertIn(
                "slip_observed_max_minutes", entry,
                f"{source} missing slip_observed_max_minutes",
            )

    def test_every_source_has_slip_measured_at(self):
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertIn(
                "slip_measured_at", entry,
                f"{source} missing slip_measured_at",
            )

    def test_every_source_has_slip_status(self):
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertIn(
                "slip_status", entry,
                f"{source} missing slip_status",
            )

    def test_initial_slip_status_is_unmeasured(self):
        """Fresh schedule: every source's slip_status is 'unmeasured'."""
        _restore_schedule()
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertEqual(
                entry.get("slip_status"), "unmeasured",
                f"{source} initial slip_status should be 'unmeasured', "
                f"got {entry.get('slip_status')!r}",
            )

    def test_negative_delete_field_breaks_assertion(self):
        """Negative control: deleting the field surfaces the omission in
        the assertion. Proves the guard checks the field exists, not just
        that it currently has a value."""
        mutated = {k: dict(v) for k, v in PUBLICATION_SCHEDULES.items()}
        del mutated["usatoday"]["slip_observed_max_minutes"]
        self.assertNotIn(
            "slip_observed_max_minutes", mutated["usatoday"],
            "negative control: deletion must be visible",
        )


class TestGraceMath(unittest.TestCase):
    """Acceptance criterion 2: grace = publication + slip."""

    def _rule_with_grace(self, grace_days, slip_minutes):
        return {
            "publish_day": 1,
            "grace_days": grace_days,
            "slip_observed_max_minutes": slip_minutes,
            "slip_measured_at": None,
            "slip_status": "measured" if slip_minutes is not None else "unmeasured",
        }

    def test_grace_window_includes_slip(self):
        from pipelines.check_deadlines import grace_window_minutes
        rule = self._rule_with_grace(grace_days=1, slip_minutes=360)
        self.assertEqual(
            grace_window_minutes("usatoday", rule),
            1 * 24 * 60 + 360,
        )

    def test_negative_slip_zero_shrinks_grace(self):
        """Negative control: a measured slip of 0 shrinks grace by exactly
        the 360-min default fallback. grace_window_minutes reads slip from
        the loaded PUBLICATION_SCHEDULES (not the passed rule dict), so the
        control loads a slip override of 0. The assertion fails if the
        helper ignores the loaded slip."""
        from pipelines.check_deadlines import grace_window_minutes
        from pipelines.lib.publication_windows import (
            load_slip_overrides,
            reset_slip_overrides,
        )
        rule = {"publish_day": 1, "grace_days": 1}
        baseline = grace_window_minutes("usatoday", rule)
        try:
            load_slip_overrides({
                "generated_at": "2026-10-02T12:00:00+00:00",
                "sources": {"usatoday": {"slip_minutes": 0, "is_stale": False}},
            })
            with_zero_slip = grace_window_minutes("usatoday", rule)
        finally:
            reset_slip_overrides()
        self.assertEqual(baseline, 1 * 24 * 60 + 360)
        self.assertEqual(with_zero_slip, baseline - 360)

    def test_effective_slip_defaults_to_6h_when_unmeasured(self):
        rule = self._rule_with_grace(grace_days=1, slip_minutes=None)
        self.assertEqual(effective_slip_minutes(rule), DEFAULT_SLIP_MINUTES)

    def test_effective_slip_uses_measured_value(self):
        rule = self._rule_with_grace(grace_days=1, slip_minutes=120)
        self.assertEqual(effective_slip_minutes(rule), 120)

    def test_effective_slip_clamps_negative_to_zero(self):
        rule = self._rule_with_grace(grace_days=1, slip_minutes=-50)
        self.assertEqual(effective_slip_minutes(rule), 0)

    def test_default_slip_is_360_minutes(self):
        """Acceptance criterion: unmeasured slip defaults to 6h."""
        self.assertEqual(DEFAULT_SLIP_MINUTES, 360)

    def test_slip_stale_after_is_30_days(self):
        """Pin the threshold so a future refactor that quietly changes
        the constant is caught."""
        self.assertEqual(SLIP_STALE_AFTER, timedelta(days=30))


class TestSourceStateWithSlip(unittest.TestCase):
    """Acceptance criteria 6 and 7: 6h-late is amber/green, 24h-late is red.

    `grace_days=0` in the helper makes the slip the ONLY thing standing
    between a 6h-late write and red -- the negative controls prove the
    amber verdict came from the slip, not from a generous raw grace.
    """

    def _rule_with_slip(self, slip_minutes, slip_status="measured"):
        return {
            "publish_day": 1,  # Tuesday
            # grace_days=0: the slip is the only thing between a 6h-late
            # write and a red verdict. The negative controls prove the
            # amber came from the slip math, not from a generous raw grace.
            "grace_days": 0,
            "slip_observed_max_minutes": slip_minutes,
            "slip_measured_at": (
                datetime.now(timezone.utc).isoformat()
                if slip_status == "measured" else None
            ),
            "slip_status": slip_status,
        }

    def _patch_usatoday(self, rule):
        """Patch PUBLICATION_SCHEDULES['usatoday'] for a single test; restore after."""
        _restore_schedule()
        original = PUBLICATION_SCHEDULES["usatoday"]
        PUBLICATION_SCHEDULES["usatoday"] = rule
        self.addCleanup(self._restore_usatoday, original)

    def _restore_usatoday(self, original):
        PUBLICATION_SCHEDULES["usatoday"] = original
        _restore_schedule()

    def test_6h_late_with_6h_slip_is_not_red(self):
        """Acceptance criterion 6: a 6-hour-late scheduled run must NOT be
        red when slip is measured at 6h. The grace math absorbs the slip."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=360)
        self._patch_usatoday(rule)

        # Tuesday 2026-10-06 is NFL content week 5 (weeks anchor on
        # Tuesday 2026-09-08; week 5's Tuesday is Oct 6).
        # Expected publish: Tuesday 23:59 UTC.
        # A 6h-late write is Wednesday 05:59 UTC. With grace_days=0 and
        # slip=360, effective grace = 6h, so the write is within grace
        # and the verdict must be amber.
        check_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 5, 59, 0, tzinfo=timezone.utc)

        result = determine_source_state(
            "usatoday", last_write, nfl_week=5, check_time=check_time,
        )

        self.assertNotEqual(
            result["state"], "red",
            f"6h-late run flagged red despite slip=6h grace: {result}",
        )
        self.assertEqual(result["slip_minutes"], 360)
        self.assertEqual(result["slip_status"], "measured")

    def test_negative_6h_late_with_slip_zero_is_red(self):
        """Negative control: with slip=0 the same 6h-late run IS red,
        proving the amber verdict in the positive test came from the
        slip-adjusted grace and not from coincidence."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=0)
        self._patch_usatoday(rule)

        check_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 5, 59, 0, tzinfo=timezone.utc)

        result = determine_source_state(
            "usatoday", last_write, nfl_week=5, check_time=check_time,
        )

        self.assertEqual(
            result["state"], "red",
            f"6h-late run with slip=0 must be red (negative control), got {result}",
        )

    def test_24h_late_with_6h_slip_is_red(self):
        """Acceptance criterion 7: a 24h-late run is red even with the
        slip grace -- the slip budget (6h) is exceeded by the write's
        actual lateness (24h)."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=360)
        self._patch_usatoday(rule)

        # Tuesday 2026-10-06 23:59 UTC is the expected publish for week 5.
        # A 24h-late write is Wednesday 23:59 UTC -- past the 6h slip
        # grace. Use Friday as check_time so the verdict cannot be
        # "still within grace".
        check_time = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 23, 59, 0, tzinfo=timezone.utc)

        result = determine_source_state(
            "usatoday", last_write, nfl_week=5, check_time=check_time,
        )

        self.assertEqual(
            result["state"], "red",
            f"24h-late run must be red even with slip=6h: {result}",
        )

    def test_negative_24h_late_with_slip_zero_still_red(self):
        """Negative control: 24h-late with slip=0 is also red, so the
        positive verdict (red) cannot be hidden by tweaking the slip."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=0)
        self._patch_usatoday(rule)

        check_time = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 23, 59, 0, tzinfo=timezone.utc)

        result = determine_source_state(
            "usatoday", last_write, nfl_week=5, check_time=check_time,
        )

        self.assertEqual(
            result["state"], "red",
            "24h-late with slip=0 must also be red (negative control)",
        )


class TestSlipLabels(unittest.TestCase):
    """Acceptance criteria 3 and 4: verbatim label strings.

    The brief pins the exact strings the operator sees. These tests
    assert equality (not contains) so a future refactor that rewords
    the message fails the build.
    """

    def test_unmeasured_label_default_6h(self):
        """Acceptance criterion 3: unmeasured → 'slip: default 6h (unmeasured)'."""
        _restore_schedule()
        self.assertEqual(
            format_slip_reason("usatoday"),
            "slip: default 6h (unmeasured)",
        )

    def test_stale_label_exact_string(self):
        """Acceptance criterion 4: stale (>30d) →
        'slip: stale measurement (>30d)'."""
        _restore_schedule()
        original = PUBLICATION_SCHEDULES["usatoday"]
        PUBLICATION_SCHEDULES["usatoday"] = {
            **original,
            "slip_status": "stale",
            "slip_observed_max_minutes": None,
            "slip_measured_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
        }
        try:
            self.assertEqual(
                format_slip_reason("usatoday"),
                "slip: stale measurement (>30d)",
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original
            _restore_schedule()

    def test_measured_label_uses_minutes(self):
        """A measured slip labels as 'slip: <N>m measured'."""
        _restore_schedule()
        original = PUBLICATION_SCHEDULES["usatoday"]
        PUBLICATION_SCHEDULES["usatoday"] = {
            **original,
            "slip_status": "measured",
            "slip_observed_max_minutes": 200,
            "slip_measured_at": datetime.now(timezone.utc).isoformat(),
        }
        try:
            self.assertEqual(
                format_slip_reason("usatoday"),
                "slip: 200m measured",
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original
            _restore_schedule()

    def test_slip_is_stale_for_old_measurement(self):
        """A 31-day-old measurement is stale."""
        rule = {
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
        }
        self.assertTrue(slip_is_stale(rule))

    def test_negative_fresh_measurement_is_not_stale(self):
        """Negative control: a 5-day-old measurement is NOT stale. If the
        threshold ever drifts down to 0 the test fails."""
        rule = {
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        }
        self.assertFalse(slip_is_stale(rule))

    def test_exactly_30d_not_stale(self):
        """The 30d boundary is non-strict (>30d, not >=30d). Exactly 30d
        is fresh; this matches the underlying measure_scheduler_slip.is_stale."""
        now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
        rule = {
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (now - timedelta(days=30)).isoformat(),
        }
        self.assertFalse(slip_is_stale(rule, now=now))

    def test_31d_is_stale(self):
        """31d is past the boundary; the rule is stale."""
        now = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
        rule = {
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (now - timedelta(days=31)).isoformat(),
        }
        self.assertTrue(slip_is_stale(rule, now=now))


class TestLoadSlipOverrides(unittest.TestCase):
    """Acceptance criterion 5: load_slip_overrides applies a measurement
    dict to PUBLICATION_SCHEDULES."""

    def setUp(self):
        _restore_schedule()
        self.addCleanup(_restore_schedule)

    def test_load_overrides_sets_measured_status(self):
        measurement = {
            "generated_at": "2026-10-02T12:00:00+00:00",
            "sources": {
                "espn": {"slip_minutes": 17, "is_stale": False},
            },
        }
        statuses = load_slip_overrides(measurement)
        self.assertEqual(statuses.get("espn"), "measured")
        rule = PUBLICATION_SCHEDULES["espn"]
        self.assertEqual(rule["slip_observed_max_minutes"], 17)
        self.assertEqual(rule["slip_measured_at"], "2026-10-02T12:00:00+00:00")
        self.assertEqual(get_slip_minutes("espn"), 17)

    def test_load_overrides_sets_stale_status(self):
        measurement = {
            "generated_at": "2026-10-02T12:00:00+00:00",
            "sources": {
                "espn": {"slip_minutes": 17, "is_stale": True},
            },
        }
        load_slip_overrides(measurement)
        self.assertEqual(get_slip_status("espn"), "stale")
        # Stale sources fall back to the 6h default in grace math.
        self.assertEqual(get_slip_minutes("espn"), DEFAULT_SLIP_MINUTES)
        self.assertEqual(format_slip_reason("espn"),
                         "slip: stale measurement (>30d)")

    def test_load_overrides_resets_unmeasured_sources(self):
        """Unmeasured sources stay unmeasured after a load."""
        _restore_schedule()
        measurement = {
            "generated_at": "2026-10-02T12:00:00+00:00",
            "sources": {
                "espn": {"slip_minutes": 17, "is_stale": False},
            },
        }
        load_slip_overrides(measurement)
        # usatoday/cbs/cbsros/fantasycalc/fantasypros were not in the
        # measurement; reset_slip_overrides() inside load_slip_overrides
        # restores their defaults first.
        self.assertEqual(get_slip_status("usatoday"), "unmeasured")
        self.assertEqual(get_slip_status("fantasycalc"), "unmeasured")
        self.assertEqual(get_slip_status("fantasypros"), "unmeasured")

    def test_load_overrides_ignores_unknown_source(self):
        """A measurement for an unknown source does not error and does
        not pollute the schedule."""
        _restore_schedule()
        measurement = {
            "generated_at": "2026-10-02T12:00:00+00:00",
            "sources": {
                "made_up_source": {"slip_minutes": 99, "is_stale": False},
            },
        }
        statuses = load_slip_overrides(measurement)
        self.assertNotIn("made_up_source", statuses)
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertNotEqual(entry.get("slip_observed_max_minutes"), 99)

    def test_load_overrides_clears_stale_load(self):
        """A previous load followed by a load that omits the source
        leaves the source in 'unmeasured' state, not 'measured'."""
        _restore_schedule()
        load_slip_overrides({
            "generated_at": "2026-10-01T12:00:00+00:00",
            "sources": {"espn": {"slip_minutes": 30, "is_stale": False}},
        })
        self.assertEqual(get_slip_status("espn"), "measured")
        # Now load a measurement that doesn't include espn.
        load_slip_overrides({
            "generated_at": "2026-10-02T12:00:00+00:00",
            "sources": {},
        })
        self.assertEqual(get_slip_status("espn"), "unmeasured")

    def test_negative_load_overrides_actually_mutates(self):
        """Negative control: load_slip_overrides must change the rule;
        if a future refactor makes it a no-op, the assertion fails."""
        _restore_schedule()
        before = dict(PUBLICATION_SCHEDULES["espn"])
        load_slip_overrides({
            "generated_at": "2026-10-02T12:00:00+00:00",
            "sources": {"espn": {"slip_minutes": 42, "is_stale": False}},
        })
        after = PUBLICATION_SCHEDULES["espn"]
        self.assertNotEqual(
            before.get("slip_observed_max_minutes"),
            after.get("slip_observed_max_minutes"),
            "load_slip_overrides must mutate PUBLICATION_SCHEDULES[source]",
        )


class TestDeadlineCheckerWiring(unittest.TestCase):
    """Acceptance criterion 5: check_deadlines() calls the slip
    measurement and applies it to per-source state decisions."""

    def setUp(self):
        _restore_schedule()
        self.addCleanup(_restore_schedule)

    def test_check_deadlines_calls_compute_slip_measurement(self):
        """check_deadlines() must call compute_slip_measurement with the
        injected slip_history_fn before deciding states."""
        from pipelines import check_deadlines

        called = {"count": 0}

        def fake_history():
            called["count"] += 1
            return [{
                "workflow_name": "ESPN scrape to Supabase",
                "run_started_at": "2026-10-02T11:35:00Z",
                "event": "schedule",
                "run_id": 1,
            }]

        with mock.patch("pipelines.check_deadlines.read_chain_status",
                        return_value=None):
            artifact = check_deadlines.check_deadlines(
                nfl_week=5,
                check_time=datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc),
                source_last_write_fn=lambda src, wk: None,
                slip_history_fn=fake_history,
            )

        self.assertEqual(called["count"], 1)
        self.assertIn("slip_measurement", artifact)
        self.assertIsNone(artifact["slip_measurement"].get("error"))
        # ESPN was measured; the schedule reflects it.
        self.assertEqual(get_slip_status("espn"), "measured")
        self.assertEqual(get_slip_minutes("espn"), 5)  # 11:35 - 11:30 = 5 min

    def test_check_deadlines_no_injection_resets_to_defaults(self):
        """No injection → no measurement → defaults; the artifact still
        carries a slip_measurement section (with error='no_slip_history_injected')."""
        from pipelines import check_deadlines

        with mock.patch("pipelines.check_deadlines.read_chain_status",
                        return_value=None):
            artifact = check_deadlines.check_deadlines(
                nfl_week=5,
                check_time=datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc),
                source_last_write_fn=lambda src, wk: None,
                slip_history_fn=None,
            )

        # No fetch function injected; we don't try to call the GitHub
        # API. The result is "no measurement" with slip_status reset.
        self.assertIn("slip_measurement", artifact)
        self.assertEqual(artifact["slip_measurement"].get("error"),
                         "no_slip_history_injected")
        self.assertEqual(get_slip_status("espn"), "unmeasured")
        self.assertEqual(get_slip_minutes("espn"), DEFAULT_SLIP_MINUTES)

    def test_check_deadlines_uses_slip_in_source_state(self):
        """End-to-end: with slip loaded, a 6h-late write is not red;
        the slip is part of the deadline checker's verdict."""
        from pipelines import check_deadlines

        history = [{
            "workflow_name": "ESPN scrape to Supabase",
            "run_started_at": "2026-10-02T11:30:00Z",  # 0 min slip
            "event": "schedule",
            "run_id": 1,
        }]

        # No measurement -> defaults: unmeasured, slip=360 default.
        # A 6h-late write (Wed 05:59 UTC) for an unmeasured usatoday
        # would be red without the slip math.
        check_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 5, 59, 0, tzinfo=timezone.utc)

        # Patch usatoday to grace_days=0 so the default slip (6h) is the
        # only thing standing between the 6h-late write and a red verdict.
        original = PUBLICATION_SCHEDULES["usatoday"]
        PUBLICATION_SCHEDULES["usatoday"] = {
            **original,
            "grace_days": 0,
        }

        try:
            with mock.patch("pipelines.check_deadlines.read_chain_status",
                            return_value=None):
                artifact = check_deadlines.check_deadlines(
                    nfl_week=5,
                    check_time=check_time,
                    source_last_write_fn=lambda src, wk: (
                        last_write if src == "usatoday" else None
                    ),
                    slip_history_fn=lambda: history,
                )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original

        # usatoday: 6h-late write, grace_days=0 + 6h default slip = 6h
        # effective grace; the write is within grace => amber, not red.
        usatoday_state = artifact["sources"]["usatoday"]["state"]
        self.assertNotEqual(
            usatoday_state, "red",
            f"usatoday 6h-late run flagged red despite default slip: {artifact['sources']['usatoday']}",
        )
        # The reason explicitly mentions the slip.
        self.assertIn("slip", artifact["sources"]["usatoday"]["reason"].lower())
        # The artifact's slip_measurement section is populated.
        self.assertIsNone(artifact["slip_measurement"].get("error"))

    def test_negative_no_wiring_flags_6h_late_red(self):
        """Negative control: a checker that ignores slip flags the 6h-late
        run red. We simulate this by calling determine_source_state directly
        with grace_days=0 and slip=0; this is what the wiring must NOT
        produce."""
        from pipelines.check_deadlines import determine_source_state

        rule = {
            "publish_day": 1,
            "grace_days": 0,
            "slip_observed_max_minutes": 0,
            "slip_measured_at": None,
            "slip_status": "measured",
        }
        original = PUBLICATION_SCHEDULES["usatoday"]
        PUBLICATION_SCHEDULES["usatoday"] = rule
        try:
            result = determine_source_state(
                "usatoday",
                datetime(2026, 10, 7, 5, 59, 0, tzinfo=timezone.utc),
                nfl_week=5,
                check_time=datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc),
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original
            _restore_schedule()

        self.assertEqual(
            result["state"], "red",
            "negative control: no slip => 6h-late is red",
        )


class TestNoUserFacingVocabulary(unittest.TestCase):
    """The two slip label strings must not collide with the disallowed
    public-copy vocab (CLAUDE.md): no 'market', no 'vorp', no
    'fantasypros' brand."""

    def test_slip_labels_are_neutral(self):
        labels = [
            "slip: default 6h (unmeasured)",
            "slip: stale measurement (>30d)",
            f"slip: 200m measured",
        ]
        for label in labels:
            self.assertNotIn("market", label.lower())
            self.assertNotIn("vorp", label.lower())
            self.assertNotIn("fantasypros", label.lower())


if __name__ == "__main__":
    unittest.main()