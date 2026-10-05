"""Tests for pipelines.heartbeat_driver (JEG-339 / JEG-357).

Two scopes:
    1. build_observation: table-driven over all 7 approved verdicts + unknown.
    2. run_once: end-to-end on fixtures (2 checks, one with ok rows →
       healthy; one with zero rows → unknown).
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from pipelines.heartbeat_evaluator import HeartbeatState, Observation

from pipelines.heartbeat_driver import build_observation, run_once


# ---- Helpers ------------------------------------------------------------


def _now_z(delta_seconds: float = 0) -> str:
    """Current UTC time as ISO-8601 'Z' string, minus delta_seconds."""
    return (datetime.now(timezone.utc) - timedelta(seconds=delta_seconds)
            ).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _row(verdict: str, *, url: str = "https://example.test/", status: int = 200,
         latency: int = 50, when: str = None) -> dict:
    """One NDJSON-shaped producer row (fresh timestamp unless given)."""
    return {
        "checked_at": when if when is not None else _now_z(),
        "url": url,
        "status_code": status,
        "response_ms": latency,
        "verdict": verdict,
    }


# ---- build_observation --------------------------------------------------


class BuildObservationTests(unittest.TestCase):
    """Table-driven coverage of the 7 approved verdicts + unknown."""

    def test_ok_verdict(self):
        obs = build_observation(_row("ok", status=200, latency=120))
        self.assertTrue(obs.ok)
        self.assertIsNone(obs.content_ok)
        self.assertIsNone(obs.error_code)
        self.assertEqual(obs.http_status, 200)
        self.assertEqual(obs.latency_ms, 120)
        self.assertEqual(obs.run_at.tzinfo, timezone.utc)

    def test_content_mismatch_verdict(self):
        obs = build_observation(_row("content_mismatch", status=200, latency=80))
        self.assertTrue(obs.ok)
        self.assertIs(obs.content_ok, False)
        self.assertIsNone(obs.error_code)
        self.assertEqual(obs.http_status, 200)

    def test_timeout_verdict(self):
        obs = build_observation(_row("timeout", status=None, latency=10000))
        self.assertFalse(obs.ok)
        self.assertIsNone(obs.content_ok)
        self.assertEqual(obs.error_code, "timeout")
        self.assertIsNone(obs.http_status)

    def test_dns_error_verdict(self):
        obs = build_observation(_row("dns_error", status=None, latency=15))
        self.assertFalse(obs.ok)
        self.assertEqual(obs.error_code, "dns")

    def test_tls_error_verdict(self):
        obs = build_observation(_row("tls_error", status=None, latency=80))
        self.assertFalse(obs.ok)
        self.assertEqual(obs.error_code, "tls")

    def test_connect_error_verdict(self):
        obs = build_observation(_row("connect_error", status=None, latency=200))
        self.assertFalse(obs.ok)
        self.assertEqual(obs.error_code, "connect")

    def test_http_error_verdict(self):
        obs = build_observation(_row("http_error", status=503, latency=300))
        self.assertFalse(obs.ok)
        self.assertEqual(obs.error_code, "http")
        self.assertEqual(obs.http_status, 503)

    def test_unknown_verdict_raises(self):
        with self.assertRaises(ValueError):
            build_observation(_row("green_check"))

    def test_unknown_verdict_arbitrary_string_raises(self):
        with self.assertRaises(ValueError):
            build_observation(_row("nuclear_meltdown"))


# ---- run_once end-to-end -----------------------------------------------


class RunOnceTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.checks_path = os.path.join(self._tmp.name, "checks.json")
        self.obs_path = os.path.join(self._tmp.name, "obs.ndjson")
        self.out_path = os.path.join(self._tmp.name, "snapshot.json")

    def _write(self, path: str, payload):
        with open(path, "w", encoding="utf-8") as fh:
            if isinstance(payload, list):
                for item in payload:
                    fh.write(json.dumps(item) + "\n")
            else:
                json.dump(payload, fh)

    def test_two_checks_one_healthy_one_unknown(self):
        checks = {
            "checks": [
                {
                    "check_id": "trade-value-chart",
                    "url": "https://example.test/chart",
                    "enabled": True,
                    "timeout_seconds": 10,
                    "latency_budget_ms": 3000,
                    "check_type": "http_status",
                },
                {
                    "check_id": "consolidation-watcher",
                    "url": "https://example.test/consolidation",
                    "enabled": True,
                    "timeout_seconds": 10,
                    "latency_budget_ms": 3000,
                    "check_type": "http_status",
                },
            ]
        }
        self._write(self.checks_path, checks)

        # Only observations for the first check_id; second check has none.
        rows = [
            _row("ok", url="https://example.test/chart", status=200, latency=120),
            _row("ok", url="https://example.test/chart", status=200, latency=110),
        ]
        self._write(self.obs_path, rows)

        summary = run_once(self.checks_path, self.obs_path, self.out_path)

        # File exists and has the contract fields.
        self.assertTrue(os.path.exists(self.out_path))
        with open(self.out_path, encoding="utf-8") as fh:
            snap = json.load(fh)
        self.assertIn("generated_at", snap)
        self.assertIsInstance(snap["generated_at"], str)
        self.assertTrue(snap["generated_at"].endswith("Z"))
        self.assertEqual(len(snap["heartbeats"]), 2)

        by_id = {h["check_id"]: h for h in snap["heartbeats"]}
        self.assertEqual(set(by_id), {"trade-value-chart", "consolidation-watcher"})

        # First check had ok rows → healthy.
        self.assertEqual(by_id["trade-value-chart"]["state"], HeartbeatState.HEALTHY.value)

        # Second check had zero rows → unknown.
        self.assertEqual(by_id["consolidation-watcher"]["state"], HeartbeatState.UNKNOWN.value)

        # Summary shape.
        self.assertEqual(summary["checks"], 2)
        self.assertEqual(summary["states"][HeartbeatState.HEALTHY.value], 1)
        self.assertEqual(summary["states"][HeartbeatState.UNKNOWN.value], 1)

    def test_observation_for_unknown_url_is_silently_skipped(self):
        """A row whose url is not in checks config must not crash the pass."""
        checks = {
            "checks": [
                {
                    "check_id": "chart",
                    "url": "https://example.test/chart",
                    "enabled": True,
                    "timeout_seconds": 10,
                    "latency_budget_ms": 3000,
                    "check_type": "http_status",
                },
            ]
        }
        self._write(self.checks_path, checks)

        rows = [
            _row("ok", url="https://example.test/chart"),
            _row("ok", url="https://example.test/UNKNOWN"),  # stale row, must be ignored
        ]
        self._write(self.obs_path, rows)

        summary = run_once(self.checks_path, self.obs_path, self.out_path)
        with open(self.out_path, encoding="utf-8") as fh:
            snap = json.load(fh)
        self.assertEqual(summary["checks"], 1)
        self.assertEqual(snap["heartbeats"][0]["state"], HeartbeatState.HEALTHY.value)


if __name__ == "__main__":
    unittest.main()