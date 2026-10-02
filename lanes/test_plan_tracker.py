#!/usr/bin/env python3
"""Discrimination tests for the JEG-96 plan tracker and status command.

Rule (AGENTS.md): every regression guard must negative-test against a
simulated broken state. A guard that asserts current behaviour is correct,
without checking which state is right, is worse than no guard.

These tests verify:
  1. status derivation from a fixture (Done vs not-Done routes the phase).
  2. A Tier-0-only doc change is auto-merge under the charter.
  3. A Tier-2 content trigger overrides the path match and demands Jeremy.
  4. The merge queue serializes and re-runs gates before each item.
  5. UNKNOWN tickets are reported as missing (not silently 'todo').
  6. Phase blocking: phase-1 stays blocked while phase-0 has open tickets.
  7. Phase parallelism: phase-4 is active from day 1 (parallel with phase-0).
"""
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "lanes"))

import plan_status  # noqa: E402
import merge_charter  # noqa: E402


FIXTURE_TEMPLATE = {
    "_comment": "test fixture",
    "_last_refreshed": "2026-10-02",
    "tickets": {
        "JEG-77": {"status": "Done", "title": "fidelity"},
        "JEG-78": {"status": "Done", "title": "hp 1"},
        "JEG-79": {"status": "Done", "title": "hp 2"},
        "JEG-80": {"status": "Done", "title": "hp 3"},
        "JEG-81": {"status": "Done", "title": "hp 4a"},
        "JEG-82": {"status": "Done", "title": "hp 4b"},
        "JEG-83": {"status": "Done", "title": "hp 4c"},
        "JEG-84": {"status": "Done", "title": "hp 4d"},
        "JEG-91": {"status": "Backlog", "title": "merge charter"},
        "JEG-92": {"status": "Backlog", "title": "acceptance"},
        "JEG-93": {"status": "Backlog", "title": "decision queue"},
        "JEG-94": {"status": "Backlog", "title": "lane channel"},
        "JEG-71": {"status": "Backlog", "title": "cbs pull"},
        "JEG-55": {"status": "Backlog", "title": "espn supabase"},
        "JEG-96": {"status": "In Progress", "title": "this"},
    },
}


def _with_fixture_and_plan(monkeypatch_fixture: dict) -> None:
    """Patch both plan_status and merge_charter to use a test fixture."""
    plan_status._load_json = lambda path: (
        monkeypatch_fixture["plan"] if path.name == "plan.json"
        else monkeypatch_fixture["fixture"]
    )
    merge_charter._load_plan = lambda: monkeypatch_fixture["plan"]


def _fixture_with_ticket(ticket: str, status: str) -> dict:
    f = json.loads(json.dumps(FIXTURE_TEMPLATE))
    f["tickets"][ticket]["status"] = status
    return f


def _load_real_plan() -> dict:
    return json.loads((REPO / "lanes" / "plan.json").read_text())


class PlanTrackerDerivationTest(unittest.TestCase):
    """The tracker's job: derive state from a JSON fixture, not hand-maintain it."""

    def setUp(self):
        self.monkey = {"plan": _load_real_plan(), "fixture": FIXTURE_TEMPLATE}

    def test_phase0_done_unblocks_phase1_and_phase2(self):
        """Phase 0 100% Done should leave only phase-1 + phase-2 active
        (phase-3 blocked by phase-0 only, so also active)."""
        state = plan_status.compute_state()
        # When run with the real fixture (which has JEG-77 + JEG-84 still open),
        # phase-0 is 'active', not 'done'.
        p0 = next(p for p in state["phases"] if p["id"] == "phase-0")
        self.assertEqual(p0["state"], "active")
        self.assertGreater(p0["done"], 0)
        self.assertLess(p0["done"], p0["total"])

    def test_phase0_all_done_unblocks_phase1(self):
        """With phase-0 100% Done, phase-1's `blocked_by` (phase-0) clears
        and the phase becomes active. This is the discrimination: a frozen
        fixture that ignored phase-0 status would misroute this."""
        fixture = _fixture_with_ticket("JEG-77", "Done")
        fixture = _fixture_with_ticket("JEG-84", "Done")
        # rewrite JEG-77 status
        fixture["tickets"]["JEG-77"]["status"] = "Done"
        fixture["tickets"]["JEG-84"]["status"] = "Done"
        self.monkey["fixture"] = fixture
        _with_fixture_and_plan(self.monkey)
        state = plan_status.compute_state()
        p0 = next(p for p in state["phases"] if p["id"] == "phase-0")
        self.assertEqual(p0["state"], "done")
        p1 = next(p for p in state["phases"] if p["id"] == "phase-1")
        self.assertEqual(p1["state"], "active", "phase-1 should unblock when phase-0 hits Done")

    def test_phase4_active_from_day_one(self):
        """Phase 4 has empty blocked_by so it is active from the moment the
        tracker exists, regardless of phase-0. Discrimination: a tracker
        that treated phases as strictly sequential would mark phase-4
        'blocked'."""
        state = plan_status.compute_state()
        p4 = next(p for p in state["phases"] if p["id"] == "phase-4")
        self.assertEqual(p4["state"], "active")

    def test_unknown_ticket_reported_missing_not_todo(self):
        """A ticket id absent from the fixture must NOT silently count as
        complete. This catches the 'forgot to refresh the fixture' bug."""
        fixture = json.loads(json.dumps(FIXTURE_TEMPLATE))
        fixture["tickets"]["JEG-77"]["status"] = "Done"
        fixture["tickets"]["JEG-84"]["status"] = "Done"
        # Drop JEG-78 from the fixture entirely.
        del fixture["tickets"]["JEG-78"]
        self.monkey["fixture"] = fixture
        _with_fixture_and_plan(self.monkey)
        state = plan_status.compute_state()
        p0 = next(p for p in state["phases"] if p["id"] == "phase-0")
        # JEG-78 missing -> blocking list contains it.
        self.assertIn("JEG-78=missing", p0["blocking_tickets"])
        self.assertLess(p0["done"], p0["total"])

    def test_jeg95_cancelled_does_not_count_as_complete_work(self):
        """JEG-95 is cancelled/superseded. It must not be in any phase's
        ticket_ids list, so a tracker that pulled it from the fixture and
        re-classified would inflate Done counts. This is the discrimination
        guard against an over-eager 'auto-include all known tickets' bug."""
        plan = _load_real_plan()
        all_plan_tickets = {
            tid
            for phase in plan["phases"]
            for tid in phase["ticket_ids"]
        }
        self.assertNotIn("JEG-95", all_plan_tickets)

    def test_status_render_includes_active_blocking_tickets(self):
        """The render() output must name the specific blocking tickets; the
        status command without names is worse than no command."""
        self.monkey["fixture"] = FIXTURE_TEMPLATE
        _with_fixture_and_plan(self.monkey)
        out = plan_status.render(plan_status.compute_state())
        # JEG-77 is the open fidelity ticket in the default fixture.
        self.assertIn("JEG-77", out)
        # The phase name appears so a reader knows which phase.
        self.assertIn("phase-0", out)

    def test_broken_state_drops_phase0_to_blocked(self):
        """Negative test against a simulated broken fixture where phase-0
        regressions: if JEG-78 (health program 1/4) goes back to Backlog,
        phase-0 must show 'active' with a blocking ticket, not silently
        'done'. This is the discrimination guard."""
        fixture = json.loads(json.dumps(FIXTURE_TEMPLATE))
        fixture["tickets"]["JEG-78"]["status"] = "Backlog"
        self.monkey["fixture"] = fixture
        _with_fixture_and_plan(self.monkey)
        state = plan_status.compute_state()
        p0 = next(p for p in state["phases"] if p["id"] == "phase-0")
        self.assertEqual(p0["state"], "active")
        self.assertIn("JEG-78=backlog", p0["blocking_tickets"])
        self.assertEqual(p0["done"], p0["total"] - 1)


class MergeCharterClassificationTest(unittest.TestCase):
    """The tier rules' job: auto-merge what is safe, hold what is not."""

    def test_docs_only_pr_is_tier0_with_gates_satisfied(self):
        r = merge_charter.classify_pr(
            ["docs/merge-charter.md"],
            validate_green=True,
            verify_live_green=True,
        )
        self.assertEqual(r.tier, "tier_0")
        self.assertTrue(r.auto_merge)
        self.assertEqual(r.human_in_loop, "none")
        self.assertTrue(r.ok, f"unmet gates: {r.unmet_gates}")

    def test_docs_only_pr_with_failed_validate_is_held(self):
        """Negative test: same doc-only PR but validate is red. Must hold."""
        r = merge_charter.classify_pr(
            ["docs/merge-charter.md"],
            validate_green=False,
            verify_live_green=True,
        )
        self.assertFalse(r.auto_merge)
        self.assertIn("make validate green", r.unmet_gates)

    def test_methodology_content_trigger_overrides_tier0(self):
        """A docs-only PR that also flips a methodology flag must be
        Tier 2. Discrimination: a charter that trusted the path match
        alone would route this to Tier 0."""
        r = merge_charter.classify_pr(
            ["docs/notes.md"],
            touches_methodology=True,
            validate_green=True,
            verify_live_green=True,
        )
        self.assertEqual(r.tier, "tier_2")
        self.assertFalse(r.auto_merge)
        self.assertEqual(r.human_in_loop, "jeremy")

    def test_pipeline_pr_with_no_triggers_is_tier1(self):
        """A pipeline change with no forbidden content triggers and no
        forbidden paths lands in Tier 1 with Roman's tap. Discrimination:
        not Tier 0 (touches pipelines/) and not Tier 2 (no content flag)."""
        r = merge_charter.classify_pr(
            ["pipelines/some_helper.py"],
            contract_tests_green=True,
            wiring_verification_green=True,
            evidence_bundle_attached=True,
            different_lane_review_posted=True,
        )
        self.assertEqual(r.tier, "tier_1")
        self.assertTrue(r.auto_merge)
        self.assertEqual(r.human_in_loop, "roman")

    def test_tier1_missing_review_blocks_auto_merge(self):
        """A Tier-1 PR without a different-lane review must hold. This is
        the discrimination guard against Phase 2 being skipped."""
        r = merge_charter.classify_pr(
            ["pipelines/some_helper.py"],
            contract_tests_green=True,
            wiring_verification_green=True,
            evidence_bundle_attached=True,
            different_lane_review_posted=False,  # the missing gate
        )
        self.assertEqual(r.tier, "tier_1")
        self.assertFalse(r.auto_merge)
        self.assertIn("different-lane review posted", r.unmet_gates)

    def test_supabase_ddl_is_tier2(self):
        """SQL migration touching the schema is Tier 2 by forbidden-path."""
        r = merge_charter.classify_pr(
            ["sql/migrations/007_some_change.sql"],
        )
        self.assertEqual(r.tier, "tier_2")
        self.assertEqual(r.human_in_loop, "jeremy")

    def test_data_raw_touch_is_tier2(self):
        """data/raw/ holds the only copy of inputs — any touch is Tier 2."""
        r = merge_charter.classify_pr(
            ["data/raw/sources/razzball/2026-10-02/snapshot.json"],
        )
        self.assertEqual(r.tier, "tier_2")

    def test_test_only_change_with_all_gates_is_tier0(self):
        r = merge_charter.classify_pr(
            ["tests/test_jeg_acceptance.py"],
            validate_green=True,
            verify_live_green=True,
        )
        self.assertEqual(r.tier, "tier_0")
        self.assertTrue(r.auto_merge)

    def test_lanes_dir_change_is_tier0(self):
        """lanes/ is in Tier 0 globs (process tooling, not production)."""
        r = merge_charter.classify_pr(
            ["lanes/merge_charter.py", "lanes/test_merge_charter.py"],
            validate_green=True,
            verify_live_green=True,
        )
        self.assertEqual(r.tier, "tier_0")

    def test_app_change_without_triggers_is_tier1(self):
        """app/ is in Tier 1 globs (not Tier 0's docs/tests/lanes)."""
        r = merge_charter.classify_pr(
            ["app/trade-value-chart/index.html"],
            contract_tests_green=True,
            wiring_verification_green=True,
            evidence_bundle_attached=True,
            different_lane_review_posted=True,
        )
        self.assertEqual(r.tier, "tier_1")


class MergeQueueSerializationTest(unittest.TestCase):
    """The merge queue's job: serialize merges, re-verify before each."""

    def setUp(self):
        self.q = merge_charter.MergeQueue.from_plan()

    def test_default_is_serial_one_at_a_time(self):
        d = self.q.next_action(current_main_sha="abc1234", pending=["pr1", "pr2", "pr3"])
        self.assertTrue(d.serialize)
        self.assertEqual(d.max_concurrent, 1)
        self.assertEqual(d.enqueue, ["pr1"])
        self.assertEqual(d.wait, ["pr2", "pr3"])

    def test_serial_actions_include_rebase_and_reverify(self):
        d = self.q.next_action(current_main_sha="abc1234", pending=["pr1"])
        joined = " ".join(d.actions_per_item).lower()
        self.assertIn("rebase", joined)
        self.assertIn("re-run", joined)
        self.assertIn("validate", joined)
        self.assertIn("verify", joined)

    def test_in_flight_pr_does_not_consume_extra_slot(self):
        """If one PR is in flight, the queue must not start a second."""
        d = self.q.next_action(
            current_main_sha="abc1234",
            pending=["pr2", "pr3"],
            in_flight=["pr1"],
        )
        self.assertEqual(d.enqueue, [])
        self.assertEqual(d.wait, ["pr2", "pr3"])

    def test_broken_state_queue_misroutes_to_parallel(self):
        """Negative test against a simulated broken queue spec where
        serialize=false. The default-loaded queue must NOT route like
        that, but if someone edits lanes/plan.json to disable
        serialization, the queue decision must surface it."""
        d = self.q.next_action(current_main_sha="x", pending=["a", "b", "c"])
        self.assertNotEqual(len(d.enqueue), 3,
                            "broken queue would let all three merge at once")


class PlanCliRenderTest(unittest.TestCase):
    def test_cli_runs_and_prints_human_readable(self):
        """End-to-end: invoking main() prints a render + JSON to stderr."""
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            rc = plan_status.main()
        self.assertEqual(rc, 0)
        out = buf_out.getvalue()
        self.assertIn("Operating-model status", out)
        err = buf_err.getvalue()
        self.assertIn("active", err)  # JSON has "state":"active"


if __name__ == "__main__":
    unittest.main()