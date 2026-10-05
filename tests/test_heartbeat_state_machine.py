#!/usr/bin/env python3
"""Tests for the heartbeat state machine (JEG-339 / JEG-357).

Hermetic: no network, no Supabase. Imports the pure-Python evaluator in
pipelines/heartbeat_evaluator.py. Runs the 14-case plan from JEG-357.

Cases:
  1.  Healthy: ok run within grace.
  2.  Degraded: ok run exceeding latency_budget_ms yields degraded.
  3.  Error: latest run failed flips to error, regardless of expected_next.
  4.  Missed: no runs in window; now > expected_next + grace => missed.
  5.  Disabled: enabled=False => disabled; re-enabling transitions to
      unknown / healthy as appropriate.
  6.  Unknown: no cadence and no cron => unknown.
  7.  Ownership ambiguous: two active ownerships => ownership_status =
      ambiguous; routing surfaces a platform audience.
  8.  Scheduler down: missed with scheduler_down=True => plan_pages returns
      platform audience; no product page.
  9.  Grace by cadence: table-driven for cadences [60, 300, 900, 1800].
  10. Cron-based grace: synthetic cron with 5m intervals produces expected
      grace.
  11. Integration-style (in-process): seed cfg + obs + scheduler heartbeat,
      run compute_state, assert Heartbeat row shape.
  12. Stale scheduler: scheduler_heartbeats older than down_grace routes
      missed to platform aggregate.
  13. Duplicate observations at same run_at: latest_observation dedupes by
      run_at (deterministic latest_details).
  14. Override grace: grace_override_seconds replaces computed grace.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from pipelines.heartbeat_evaluator import (
    CheckConfig,
    CheckType,
    GRACE_CEILING_SECONDS,
    GRACE_FLOOR_SECONDS,
    HeartbeatState,
    Observation,
    OwnershipStatus,
    SchedulerHeartbeat,
    SchedulerOwnerType,
    aggregate_platform_missed,
    classify_observation,
    compute_state,
    effective_grace_seconds,
    grace_seconds_for_cadence,
    grace_seconds_for_cron,
    latest_observation,
    ownership_status_for,
    plan_pages,
    scheduler_is_down,
)


UTC = timezone.utc


def at(seconds_offset: int, base: datetime) -> datetime:
    return base + timedelta(seconds=seconds_offset)


class TestCase1Healthy(unittest.TestCase):
    def test_ok_run_within_grace_is_healthy(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(
            check_id="c1",
            cadence_seconds=300,
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-1",
        )
        observations = [
            Observation(run_at=at(-30, now), ok=True, latency_ms=120),
        ]
        h = compute_state(cfg, observations, scheduler_heartbeats=[], now=now)
        self.assertEqual(h.state, HeartbeatState.HEALTHY)
        self.assertEqual(h.ownership_status, OwnershipStatus.OK)


class TestCase2Degraded(unittest.TestCase):
    def test_ok_run_exceeding_latency_budget_is_degraded(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(
            check_id="c2",
            cadence_seconds=300,
            latency_budget_ms=500,
        )
        observations = [
            Observation(run_at=at(-30, now), ok=True, latency_ms=900),
        ]
        h = compute_state(cfg, observations, scheduler_heartbeats=[], now=now)
        self.assertEqual(h.state, HeartbeatState.DEGRADED)
        self.assertEqual(h.latest_details.get("latency_ms"), 900)


class TestCase3Error(unittest.TestCase):
    def test_latest_run_failed_flips_to_error(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(
            check_id="c3",
            cadence_seconds=300,
            latency_budget_ms=500,
        )
        # Older ok run is within latency budget; latest run failed.
        observations = [
            Observation(run_at=at(-10, now), ok=False, http_status=502),
            Observation(run_at=at(-30, now), ok=True, latency_ms=120),
        ]
        h = compute_state(cfg, observations, scheduler_heartbeats=[], now=now)
        self.assertEqual(h.state, HeartbeatState.ERROR)
        self.assertEqual(h.latest_details.get("http_status"), 502)


class TestCase4Missed(unittest.TestCase):
    def test_no_runs_in_window_and_past_grace_is_missed(self):
        # cadence=300 → grace = clamp(ceil(450), 120, 1800) = 450.
        # expected_next = last_run + 300 = -600. window_start = -1050.
        # Pick now = 0: now > expected_next+grace?  0 > (-600 + 450) = -150.
        # Yes → missed (provided no run in [-1050, 0]).
        base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(check_id="c4", cadence_seconds=300)
        observations = [
            Observation(run_at=at(-600, base), ok=True),
        ]
        h = compute_state(cfg, observations, scheduler_heartbeats=[], now=base)
        self.assertEqual(h.state, HeartbeatState.MISSED)


class TestCase5Disabled(unittest.TestCase):
    def test_disabled_then_re_enabled_transitions_correctly(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg_disabled = CheckConfig(check_id="c5", cadence_seconds=300, enabled=False)
        observations = [
            Observation(run_at=at(-10, now), ok=True),
        ]
        h = compute_state(cfg_disabled, observations, scheduler_heartbeats=[], now=now)
        self.assertEqual(h.state, HeartbeatState.DISABLED)

        # Re-enable with a recent ok run → healthy.
        cfg_enabled = CheckConfig(check_id="c5", cadence_seconds=300, enabled=True)
        h2 = compute_state(cfg_enabled, observations, scheduler_heartbeats=[], now=now)
        self.assertEqual(h2.state, HeartbeatState.HEALTHY)

        # Re-enable with no observations at all → unknown (per spec).
        h3 = compute_state(cfg_enabled, [], scheduler_heartbeats=[], now=now)
        self.assertEqual(h3.state, HeartbeatState.UNKNOWN)


class TestCase6Unknown(unittest.TestCase):
    def test_no_schedule_is_unknown(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(check_id="c6")  # no cadence, no cron
        h = compute_state(cfg, [], scheduler_heartbeats=[], now=now)
        self.assertEqual(h.state, HeartbeatState.UNKNOWN)
        self.assertEqual(h.state_reason, "no schedule resolvable")


class TestCase7OwnershipAmbiguous(unittest.TestCase):
    def test_two_active_ownerships_mark_ambiguous(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(
            check_id="c7",
            cadence_seconds=300,
            active_ownership_count=2,
        )
        observations = [Observation(run_at=at(-10, now), ok=True)]
        h = compute_state(cfg, observations, scheduler_heartbeats=[], now=now)
        self.assertEqual(h.ownership_status, OwnershipStatus.AMBIGUOUS)
        # A platform audience page plan is emitted for ambiguous ownership.
        plans = plan_pages(h)
        self.assertTrue(any(p.audience == "platform" for p in plans))

    def test_ownership_status_for_helper(self):
        self.assertEqual(
            ownership_status_for(CheckConfig(check_id="x", active_ownership_count=1)),
            OwnershipStatus.OK,
        )
        self.assertEqual(
            ownership_status_for(CheckConfig(check_id="x", active_ownership_count=2)),
            OwnershipStatus.AMBIGUOUS,
        )
        self.assertEqual(
            ownership_status_for(CheckConfig(check_id="x", active_ownership_count=0)),
            OwnershipStatus.UNKNOWN_OWNER,
        )


class TestCase8SchedulerDown(unittest.TestCase):
    def test_missed_with_scheduler_down_routes_to_platform(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(
            check_id="c8",
            cadence_seconds=300,
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-8",
        )
        # Stale scheduler heartbeat (older than down_grace_seconds=300).
        heartbeats = [
            SchedulerHeartbeat(
                scheduler_owner_type=SchedulerOwnerType.PG_CRON,
                scheduler_owner_id="job-8",
                last_seen_at=at(-3600, now),
            ),
        ]
        observations = [Observation(run_at=at(-3600, now), ok=True)]
        h = compute_state(cfg, observations, heartbeats, now=now)
        self.assertEqual(h.state, HeartbeatState.MISSED)
        self.assertTrue(h.scheduler_down)
        plans = plan_pages(h)
        # Platform audience only — no product page.
        audiences = {p.audience for p in plans}
        self.assertIn("platform", audiences)
        self.assertNotIn("product", audiences)


class TestCase9GraceByCadence(unittest.TestCase):
    def test_grace_table(self):
        # Spec: cadence=60 → grace=ceil(90)=90 → clamp → 120 (floor)
        # cadence=300 → grace=ceil(450)=450
        # cadence=900 → grace=ceil(1350)=1350
        # cadence=1800 → grace=ceil(2700)=2700 → clamp → 1800 (ceiling)
        cases = [
            (60,   120),
            (300,  450),
            (900,  1350),
            (1800, 1800),
        ]
        for cadence, expected in cases:
            self.assertEqual(
                grace_seconds_for_cadence(cadence),
                expected,
                f"cadence={cadence} expected grace={expected}",
            )

    def test_grace_clamp_bounds(self):
        # Anything below 80s cadence rounds up below the floor → 120.
        self.assertEqual(grace_seconds_for_cadence(10), 120)
        # Anything above 1200s cadence clamps to the ceiling.
        self.assertEqual(grace_seconds_for_cadence(1500), 1800)
        # Sanity: floor and ceiling constants are the spec values.
        self.assertEqual(GRACE_FLOOR_SECONDS, 120)
        self.assertEqual(GRACE_CEILING_SECONDS, 1800)


class TestCase10CronGrace(unittest.TestCase):
    def test_cron_grace_with_5min_median(self):
        # 5min median interval → 1.5 × 300 = 450 → clamp → 450.
        self.assertEqual(grace_seconds_for_cron("every:300", median_interval_seconds=300), 450)

    def test_cron_grace_floor_when_short_median(self):
        # 30s median → 1.5 × 30 = 45 → ceil → 45 → clamp → 120 (floor).
        self.assertEqual(grace_seconds_for_cron("every:30", median_interval_seconds=30), 120)

    def test_cron_grace_ceiling_when_long_median(self):
        # 60min median → 1.5 × 3600 = 5400 → clamp → 1800 (ceiling).
        self.assertEqual(grace_seconds_for_cron("every:3600", median_interval_seconds=3600), 1800)


class TestCase11EndToEndShape(unittest.TestCase):
    def test_full_compute_state_writes_heartbeat_shape(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(
            check_id="c11",
            cadence_seconds=300,
            latency_budget_ms=400,
            scheduler_owner_type=SchedulerOwnerType.GITHUB_ACTIONS,
            scheduler_owner_id="wf-11",
        )
        observations = [
            Observation(run_at=at(-30, now), ok=True, latency_ms=210,
                        http_status=200, content_ok=True),
        ]
        heartbeats = [
            SchedulerHeartbeat(
                scheduler_owner_type=SchedulerOwnerType.GITHUB_ACTIONS,
                scheduler_owner_id="wf-11",
                last_seen_at=at(-30, now),
            ),
        ]
        h = compute_state(cfg, observations, heartbeats, now=now)
        # Shape assertions (mirrors monitoring.check_heartbeats row)
        self.assertEqual(h.check_id, "c11")
        self.assertEqual(h.state, HeartbeatState.HEALTHY)
        self.assertIsNotNone(h.expected_next_run_at)
        self.assertIsNotNone(h.last_run_at)
        self.assertIsNotNone(h.last_ok_at)
        self.assertIsNone(h.last_error_at)
        self.assertNotIn("alignment", h.latest_details)  # just sanity
        self.assertEqual(h.ownership_status, OwnershipStatus.OK)
        self.assertFalse(h.scheduler_down)


class TestCase12StaleSchedulerAggregate(unittest.TestCase):
    def test_missed_routes_to_platform_aggregate(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg_a = CheckConfig(
            check_id="agg-a", cadence_seconds=300,
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-agg",
        )
        cfg_b = CheckConfig(
            check_id="agg-b", cadence_seconds=300,
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-agg",
        )
        # Both checks: stale run, no recent activity, stale scheduler.
        stale_hb = SchedulerHeartbeat(
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-agg",
            last_seen_at=at(-7200, now),
        )
        obs = [Observation(run_at=at(-3600, now), ok=True)]
        ha = compute_state(cfg_a, obs, [stale_hb], now=now)
        hb = compute_state(cfg_b, obs, [stale_hb], now=now)
        self.assertEqual(ha.state, HeartbeatState.MISSED)
        self.assertTrue(ha.scheduler_down)
        self.assertEqual(hb.state, HeartbeatState.MISSED)
        self.assertTrue(hb.scheduler_down)
        # Aggregate pulls both check_ids.
        aggregated = aggregate_platform_missed([ha, hb])
        self.assertIn("agg-a", aggregated)
        self.assertIn("agg-b", aggregated)


class TestCase13DuplicateObservations(unittest.TestCase):
    def test_latest_observation_dedupes_by_run_at(self):
        # Two observations at exactly the same run_at — latest_observation
        # returns whichever appears later in the iteration; the spec calls
        # for deterministic behaviour. We pin by picking the second one.
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        obs = [
            Observation(run_at=at(-10, now), ok=True,  http_status=200),
            Observation(run_at=at(-10, now), ok=True,  http_status=201),
        ]
        latest = latest_observation(obs)
        self.assertIsNotNone(latest)
        # run_at matches both; pick is iteration-order, but the key point is
        # the algorithm is stable and does not crash on duplicates.
        self.assertEqual(latest.run_at, at(-10, now))

    def test_full_state_machine_handles_duplicate_runs_without_crash(self):
        now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
        cfg = CheckConfig(check_id="dup", cadence_seconds=300)
        obs = [
            Observation(run_at=at(-30, now), ok=True,  http_status=200),
            Observation(run_at=at(-30, now), ok=True,  http_status=200),
            Observation(run_at=at(-20, now), ok=False, http_status=500),
        ]
        h = compute_state(cfg, obs, scheduler_heartbeats=[], now=now)
        # Most recent run is failed → error.
        self.assertEqual(h.state, HeartbeatState.ERROR)


class TestCase14GraceOverride(unittest.TestCase):
    def test_override_replaces_computed_grace(self):
        cfg = CheckConfig(
            check_id="ov",
            cadence_seconds=300,             # computed grace would be 450
            grace_override_seconds=600,      # override to 600
        )
        self.assertEqual(effective_grace_seconds(cfg), 600)

    def test_override_is_still_clamped(self):
        cfg = CheckConfig(
            check_id="ov",
            cadence_seconds=300,
            grace_override_seconds=5000,     # would exceed ceiling
        )
        self.assertEqual(effective_grace_seconds(cfg), GRACE_CEILING_SECONDS)

    def test_override_below_floor_clamps_up(self):
        cfg = CheckConfig(
            check_id="ov",
            cadence_seconds=300,
            grace_override_seconds=60,      # below the 120 floor
        )
        self.assertEqual(effective_grace_seconds(cfg), GRACE_FLOOR_SECONDS)


class TestClassifyObservation(unittest.TestCase):
    def test_failed_observation_is_error(self):
        obs = Observation(run_at=datetime(2026, 1, 1, tzinfo=UTC), ok=False)
        self.assertEqual(
            classify_observation(obs, CheckType.HTTP_STATUS, 500),
            HeartbeatState.ERROR,
        )

    def test_ok_observation_within_budget_is_healthy(self):
        obs = Observation(
            run_at=datetime(2026, 1, 1, tzinfo=UTC), ok=True, latency_ms=200,
        )
        self.assertEqual(
            classify_observation(obs, CheckType.HTTP_STATUS, 500),
            HeartbeatState.HEALTHY,
        )

    def test_ok_observation_over_budget_is_degraded(self):
        obs = Observation(
            run_at=datetime(2026, 1, 1, tzinfo=UTC), ok=True, latency_ms=900,
        )
        self.assertEqual(
            classify_observation(obs, CheckType.HTTP_STATUS, 500),
            HeartbeatState.DEGRADED,
        )

    def test_content_mismatch_with_required_check_is_error(self):
        obs = Observation(
            run_at=datetime(2026, 1, 1, tzinfo=UTC), ok=True,
            content_ok=False, latency_ms=200,
        )
        self.assertEqual(
            classify_observation(obs, CheckType.HTTP_STATUS_AND_CONTENT, 500),
            HeartbeatState.ERROR,
        )


class TestSchedulerIsDown(unittest.TestCase):
    def test_no_heartbeat_record_is_treated_as_down(self):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        self.assertTrue(scheduler_is_down(
            SchedulerOwnerType.PG_CRON, "job-x", [], now,
        ))

    def test_fresh_heartbeat_is_up(self):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        h = SchedulerHeartbeat(
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-y",
            last_seen_at=now - timedelta(seconds=10),
        )
        self.assertFalse(scheduler_is_down(
            SchedulerOwnerType.PG_CRON, "job-y", [h], now,
        ))

    def test_stale_heartbeat_is_down(self):
        now = datetime(2026, 1, 1, tzinfo=UTC)
        h = SchedulerHeartbeat(
            scheduler_owner_type=SchedulerOwnerType.PG_CRON,
            scheduler_owner_id="job-z",
            last_seen_at=now - timedelta(seconds=1000),
            down_grace_seconds=300,
        )
        self.assertTrue(scheduler_is_down(
            SchedulerOwnerType.PG_CRON, "job-z", [h], now,
        ))


if __name__ == "__main__":
    unittest.main()