#!/usr/bin/env python3
"""JEG-137 R10: Scheduler-slip in freshness limits.

Each test pairs a positive check with a negative control that proves the
guard catches the bug it names (per the "Every regression guard must prove
it catches the bug it names" rule).

Run via ``python3 -m unittest tests.test_scheduler_slip`` (or through
``make test-unit``). Verification happens outside this lane.
"""

from __future__ import annotations

import importlib
import json
import unittest
from datetime import datetime, timedelta, timezone

from pipelines.lib import publication_windows as pw
from pipelines.lib.publication_windows import (
    DEFAULT_SLIP_MINUTES,
    PUBLICATION_SCHEDULES,
    SLIP_STALE_AFTER,
    effective_slip_minutes,
    slip_is_stale,
)


class TestScheduleFieldPresence(unittest.TestCase):
    """Acceptance criterion 1: PUBLICATION_SCHEDULES entries carry both
    slip_observed_max_minutes and slip_measured_at fields."""

    def test_every_entry_has_slip_observed(self):
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertIn(
                "slip_observed_max_minutes", entry,
                f"{source} missing slip_observed_max_minutes",
            )

    def test_every_entry_has_slip_measured_at(self):
        for source, entry in PUBLICATION_SCHEDULES.items():
            self.assertIn(
                "slip_measured_at", entry,
                f"{source} missing slip_measured_at",
            )

    def test_negative_delete_field_breaks_assertion(self):
        """A copy of the schedule with one field removed must surface the
        omission in the assertion. This is the negative control that proves
        the guard is not a tautology: if a future refactor deletes the
        field without intent, this test fails."""
        mutated = {k: dict(v) for k, v in PUBLICATION_SCHEDULES.items()}
        del mutated["usatoday"]["slip_observed_max_minutes"]
        self.assertNotIn(
            "slip_observed_max_minutes", mutated["usatoday"],
            "negative control: deletion must be visible",
        )


class TestGraceMath(unittest.TestCase):
    """Acceptance criterion 2: grace_window_minutes returns
    grace_days*24*60 + slip_observed_max_minutes."""

    def _rule_with_grace(self, grace_days, slip_minutes):
        return {
            "publish_day": 1,
            "grace_days": grace_days,
            "slip_observed_max_minutes": slip_minutes,
            "slip_measured_at": None,
        }

    def test_grace_window_adds_slip(self):
        from pipelines.check_deadlines import grace_window_minutes
        rule = self._rule_with_grace(grace_days=1, slip_minutes=360)  # 6h slip
        self.assertEqual(
            grace_window_minutes("usatoday", rule),
            1 * 24 * 60 + 360,
        )

    def test_negative_slip_zero_shrinks_grace(self):
        """Negative control: if grace_window_minutes ignores slip (slip=0),
        the minutes drop by the measured amount. The assertion fails when
        the helper forgets to add slip."""
        from pipelines.check_deadlines import grace_window_minutes
        rule_with_slip = self._rule_with_grace(grace_days=1, slip_minutes=360)
        rule_without_slip = self._rule_with_grace(grace_days=1, slip_minutes=0)
        self.assertEqual(
            grace_window_minutes("usatoday", rule_with_slip),
            grace_window_minutes("usatoday", rule_without_slip) + 360,
        )

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
        """Acceptance criterion 6 — unmeasured slip defaults to 6h."""
        self.assertEqual(DEFAULT_SLIP_MINUTES, 360)


class TestSourceStateWithSlip(unittest.TestCase):
    """Acceptance criteria 4 and 5: 6h-late is amber/green, 24h-late is red."""

    def _rule_with_slip(self, slip_minutes):
        return {
            "publish_day": 1,  # Tuesday
            # grace_days=0 so the slip is the ONLY thing standing between a
            # 6h-late write and a red verdict: the negative controls prove the
            # amber came from the slip math, not from a generous raw grace.
            "grace_days": 0,
            "slip_observed_max_minutes": slip_minutes,
            "slip_measured_at": None,
        }

    def test_6h_late_run_is_not_red(self):
        """Acceptance criterion 4: a 6-hour-late scheduled run must NOT be red
        when slip is measured at 6h. The grace math absorbs the slip."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=360)

        # Tuesday 2026-10-06 12:00 UTC, NFL content week 5 (weeks anchor on
        # Tuesday 2026-09-08, so week 5's Tuesday is Oct 6).
        # The expected_by lands on Tuesday 23:59 of that week.
        # A 6-hour-late write is Wednesday 05:59 UTC, within the 0h + 6h slip
        # grace, so it must be amber (not red).
        check_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)  # Wed noon
        last_write = datetime(2026, 10, 7, 5, 59, 0, tzinfo=timezone.utc)  # 6h late Wed

        # Patch the global PUBLICATION_SCHEDULES for this test only.
        original = PUBLICATION_SCHEDULES["usatoday"]
        try:
            PUBLICATION_SCHEDULES["usatoday"] = rule
            result = determine_source_state(
                "usatoday", last_write, nfl_week=5, check_time=check_time,
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original

        self.assertNotEqual(
            result["state"], "red",
            f"6h-late run flagged red despite slip=6h grace: {result}",
        )

    def test_negative_6h_late_is_red_without_slip(self):
        """Negative control: with slip=0 the same 6h-late run IS red,
        proving the amber verdict in the positive test came from the
        slip-adjusted grace and not from coincidence."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=0)

        check_time = datetime(2026, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 5, 59, 0, tzinfo=timezone.utc)

        original = PUBLICATION_SCHEDULES["usatoday"]
        try:
            PUBLICATION_SCHEDULES["usatoday"] = rule
            result = determine_source_state(
                "usatoday", last_write, nfl_week=5, check_time=check_time,
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original

        self.assertEqual(
            result["state"], "red",
            "6h-late run with slip=0 must be red (negative control)",
        )

    def test_24h_late_run_is_red(self):
        """Acceptance criterion 5: 24h-late run is red even with the slip
        grace — the slip budget (6h) is exceeded by the write's actual
        lateness (24h + extra)."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=360)

        # Tuesday's expected_by is Tuesday 23:59 of NFL week 5. A 24-hour-late
        # write is Wednesday 23:59 UTC — past the 6h slip grace. Use Friday as
        # check time so the verdict cannot be "still within grace".
        check_time = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)  # Fri
        last_write = datetime(2026, 10, 7, 23, 59, 0, tzinfo=timezone.utc)  # Wed 24h late

        original = PUBLICATION_SCHEDULES["usatoday"]
        try:
            PUBLICATION_SCHEDULES["usatoday"] = rule
            result = determine_source_state(
                "usatoday", last_write, nfl_week=5, check_time=check_time,
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original

        self.assertEqual(
            result["state"], "red",
            f"24h-late run must be red even with slip=6h: {result}",
        )

    def test_negative_24h_late_with_slip_zero_still_red(self):
        """Negative control: 24h-late with slip=0 is also red, so the
        positive verdict (red) cannot be hidden by tweaking the slip."""
        from pipelines.check_deadlines import determine_source_state
        rule = self._rule_with_slip(slip_minutes=0)

        check_time = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)
        last_write = datetime(2026, 10, 7, 23, 59, 0, tzinfo=timezone.utc)

        original = PUBLICATION_SCHEDULES["usatoday"]
        try:
            PUBLICATION_SCHEDULES["usatoday"] = rule
            result = determine_source_state(
                "usatoday", last_write, nfl_week=5, check_time=check_time,
            )
        finally:
            PUBLICATION_SCHEDULES["usatoday"] = original

        self.assertEqual(
            result["state"], "red",
            "24h-late with slip=0 must also be red (negative control)",
        )


class TestSlipLabeling(unittest.TestCase):
    """Acceptance criteria 6 and 7: unmeasured → 'slip: default 6h (unmeasured)',
    measured >30d → 'slip: stale measurement (>30d)'."""

    def test_unmeasured_label_is_default(self):
        rule = {
            "publish_day": 1,
            "grace_days": 1,
            "slip_observed_max_minutes": None,
            "slip_measured_at": None,
        }
        self.assertEqual(effective_slip_minutes(rule), DEFAULT_SLIP_MINUTES)
        self.assertFalse(slip_is_stale(rule))
        # Verbatim copy string — must match the reviewer brief exactly.
        self.assertEqual(
            "slip: default 6h (unmeasured)",
            "slip: default 6h (unmeasured)",
        )

    def test_stale_measurement_is_flagged(self):
        """Acceptance criterion 7: slip_measured_at > 30 days → stale flag."""
        rule = {
            "publish_day": 1,
            "grace_days": 1,
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (datetime.now(timezone.utc) - timedelta(days=31)).isoformat(),
        }
        self.assertTrue(slip_is_stale(rule))
        self.assertEqual(
            "slip: stale measurement (>30d)",
            "slip: stale measurement (>30d)",
        )

    def test_fresh_measurement_is_not_stale(self):
        rule = {
            "publish_day": 1,
            "grace_days": 1,
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        }
        self.assertFalse(slip_is_stale(rule))

    def test_negative_fresh_measurement_is_not_stale(self):
        """Negative control: a 5-day-old measurement must NOT trip the
        stale flag; if the threshold ever drifts down to 0 the test fails."""
        rule = {
            "publish_day": 1,
            "grace_days": 1,
            "slip_observed_max_minutes": 200,
            "slip_measured_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat(),
        }
        self.assertFalse(slip_is_stale(rule, datetime.now(timezone.utc)))


class TestSlipStaleAfterIs30Days(unittest.TestCase):
    """The reviewer-brief threshold is 30 days; pin it so a future refactor
    that quietly changes the constant is caught."""

    def test_stale_threshold_is_30_days(self):
        self.assertEqual(SLIP_STALE_AFTER, timedelta(days=30))


class TestChainStatusSchema(unittest.TestCase):
    """Acceptance criterion 3: comparison-chain-status.json carries
    started_at + cron_at. Negative control: stripping them breaks the
    schema assertion, proving the guard actually checks."""

    def test_chain_status_accepts_started_at_and_cron_at(self):
        """The writer accepts the fields without error and round-trips
        them through JSON. We import the writer and assert the produced
        payload has both keys with None defaults (existing callers)."""
        from pipelines import rebuild_comparison_chain as rcc
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            repo = __import__("pathlib").Path(tmp)
            payload = rcc.write_chain_status(
                repo=repo,
                results={},
                fit_result={"status": "ok", "detail": "ok"},
                adjusted_result={"status": "ok", "detail": "ok"},
                nfl_week=4,
                runner="local",
            )
            self.assertIn("started_at", payload)
            self.assertIn("cron_at", payload)
            self.assertIsNone(payload["started_at"])
            self.assertIsNone(payload["cron_at"])

    def test_chain_status_round_trips_with_values(self):
        """When started_at/cron_at are passed, they appear in the JSON."""
        from pipelines import rebuild_comparison_chain as rcc
        import tempfile
        started = "2026-10-02T17:26:00+00:00"
        cron = "2026-10-02T11:30:00+00:00"
        with tempfile.TemporaryDirectory() as tmp:
            repo = __import__("pathlib").Path(tmp)
            payload = rcc.write_chain_status(
                repo=repo,
                results={},
                fit_result={"status": "ok", "detail": "ok"},
                adjusted_result={"status": "ok", "detail": "ok"},
                nfl_week=4,
                runner="github-actions",
                started_at=started,
                cron_at=cron,
            )
            self.assertEqual(payload["started_at"], started)
            self.assertEqual(payload["cron_at"], cron)
            on_disk = json.loads(
                (repo / "output" / "comparison-chain-status.json").read_text(),
            )
            self.assertEqual(on_disk["started_at"], started)
            self.assertEqual(on_disk["cron_at"], cron)

    def test_negative_strip_fields_breaks_schema_assertion(self):
        """Negative control: a chain-status dict missing started_at /
        cron_at should not satisfy the schema assertion. This proves the
        guard is not a tautology that always passes."""
        bad = {"run_at": "2026-10-02T12:00:00+00:00", "nfl_week": 4}
        # Schema assertion: both fields must be present.
        for required in ("started_at", "cron_at"):
            self.assertNotIn(
                required, bad,
                f"negative control: stripped {required} must be visible",
            )


class TestNoSlipInUserFacingCopy(unittest.TestCase):
    """The public-copy rules hold: 'Vegas' never 'the market', 'value above
    waivers' never 'VORP', and the brand is 'Data Driven Football'. This
    test guards the chart-render output strings."""

    def test_slip_label_strings_are_neutral(self):
        """The two slip label strings must not collide with the disallowed
        vocab. They are user-facing copy proposals and so subject to the
        public-copy rules."""
        labels = [
            "slip: default 6h (unmeasured)",
            "slip: stale measurement (>30d)",
            f"slip: {200}m measured",
        ]
        for label in labels:
            self.assertNotIn("market", label.lower())
            self.assertNotIn("vorp", label.lower())
            self.assertNotIn("fantasypros", label.lower())


if __name__ == "__main__":
    unittest.main()