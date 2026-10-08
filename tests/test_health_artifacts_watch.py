"""JEG-414: the served-health freshness watch must fail closed.

Negative cases prove discrimination: a stale, timestamp-less, unparseable
or future-dated artifact must never evaluate as fresh.
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

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


class AwaitPublishedTest(unittest.TestCase):
    """2026-10-08: the watch measured the served copy right after dispatching
    the deploy of this run's fresh artifacts, so it judged the PREVIOUS
    deploy (run 37779712658: served checkpoints 1269 min old while this run's
    copy was mid-deploy) and three runs in a row went red."""

    def scenario(self, deploy_lands_after_polls, argv_extra):
        real_now = datetime.now(timezone.utc)
        fresh = (real_now - timedelta(minutes=2)).isoformat()
        old = (real_now - timedelta(minutes=1269)).isoformat()
        served_polls = {"n": 0}

        def fake_fetch(url, timeout=30):
            if url.endswith("pipeline-checkpoints.json"):
                served_polls["n"] += 1
                landed = served_polls["n"] > deploy_lands_after_polls
                return {"generated_at": fresh if landed else old, "sources": {}}, 200, 5
            return {"checked_at": fresh}, 200, 5
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td) / "published"
            pub.mkdir()
            (pub / "pipeline-checkpoints.json").write_text(json.dumps({"generated_at": fresh}))
            (pub / "source-import-health.json").write_text(json.dumps({"checked_at": fresh}))
            argv = ["--dry-run", "--shadow-dir", str(Path(td) / "none"),
                    *[a.replace("{pub}", str(pub)) for a in argv_extra]]
            with mock.patch.object(w, "fetch_json", fake_fetch), \
                 mock.patch.object(w.time, "sleep", lambda s: None), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return w.main(argv)

    def test_waits_for_this_runs_deploy_before_judging(self):
        rc = self.scenario(deploy_lands_after_polls=3,
                           argv_extra=["--await-published", "{pub}", "--await-interval-seconds", "0"])
        self.assertEqual(0, rc, "this run's freshly deployed artifact must be what is judged")

    def test_a_deploy_that_never_lands_is_still_red(self):
        rc = self.scenario(deploy_lands_after_polls=10**6,
                           argv_extra=["--await-published", "{pub}", "--await-interval-seconds", "0",
                                       "--await-timeout-minutes", "0"])
        self.assertEqual(1, rc, "fail-closed: a served copy that stays old is stale")

    def test_workflow_waits_only_when_this_run_published(self):
        wf = (Path(__file__).resolve().parent.parent / ".github/workflows/health-artifacts.yml").read_text()
        step = wf[wf.index("name: Watch served artifacts"):]
        step = step[:step.index("\n      - ")]
        self.assertIn("PUBLISHED: ${{ steps.publish.outputs.pushed }}", step)
        self.assertIn('if [ "$PUBLISHED" = "true" ]; then await=(--await-published dist/modules); fi', step)
        self.assertIn('"${await[@]}"', step)


if __name__ == "__main__":
    unittest.main()
