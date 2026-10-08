"""JEG-414: the served-health freshness watch must fail closed.

Negative cases prove discrimination: a stale, timestamp-less, unparseable
or future-dated artifact must never evaluate as fresh.
"""
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import health_artifacts_watch as w  # noqa: E402

NOW = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)


def iso(minutes_ago):
    return (NOW - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


class HealthArtifactsWatchTest(unittest.TestCase):
    def test_fresh_artifact_is_ok(self):
        ok, age, err = w.evaluate({"generated_at": iso(20)}, ("generated_at",), NOW)
        self.assertTrue(ok)
        self.assertAlmostEqual(20, age, places=3)
        self.assertIsNone(err)

    def test_stale_artifact_is_red(self):
        # The defect this guards: Muse cron stops, file keeps old contents.
        # 2026-10-08: the producer runs every 6 h, so the limit is 720 min
        # (twice the cadence; was 60 min at the 30-minute cadence).
        self.assertEqual(720, w.MAX_AGE_MINUTES)
        ok, age, err = w.evaluate({"generated_at": iso(721)}, ("generated_at",), NOW)
        self.assertFalse(ok)
        self.assertTrue(err.startswith("stale_"))
        ok, _, _ = w.evaluate({"generated_at": iso(400)}, ("generated_at",), NOW)
        self.assertTrue(ok, "one cadence old is current, not stale")

    def test_missing_timestamp_is_red_not_fresh(self):
        ok, _, err = w.evaluate({"sources": {}}, ("generated_at",), NOW)
        self.assertFalse(ok)
        self.assertEqual("missing_timestamp", err)

    def test_unreachable_is_red(self):
        ok, _, err = w.evaluate(None, ("generated_at",), NOW)
        self.assertFalse(ok)
        self.assertEqual("unreachable_or_unparseable", err)

    def test_future_timestamp_is_red(self):
        ok, _, err = w.evaluate({"generated_at": iso(-30)}, ("generated_at",), NOW)
        self.assertFalse(ok)
        self.assertEqual("timestamp_in_future", err)

    def test_fallback_field_order(self):
        # import-health carries checked_at; generated_at is only a fallback.
        payload = {"checked_at": iso(10), "generated_at": iso(500)}
        ok, age, _ = w.evaluate(payload, ("checked_at", "generated_at"), NOW)
        self.assertTrue(ok)
        self.assertAlmostEqual(10, age, places=3)


if __name__ == "__main__":
    unittest.main()
