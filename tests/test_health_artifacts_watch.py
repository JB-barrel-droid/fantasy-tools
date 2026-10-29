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
        wf = (Path(__file__).resolve().parent.parent / ".github/workflows/health-artifacts.yml").read_text(encoding="utf-8")
        step = wf[wf.index("name: Watch served artifacts"):]
        step = step[:step.index("\n      - ")]
        self.assertIn("PUBLISHED: ${{ steps.publish.outputs.pushed }}", step)
        self.assertIn('if [ "$PUBLISHED" = "true" ]; then await=(--await-published dist/modules); fi', step)
        self.assertIn('"${await[@]}"', step)


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "health_artifacts_watch"
JUDGED_AT = datetime(2026, 10, 28, 19, 17, tzinfo=timezone.utc)
CHECKPOINTS = "pipeline-checkpoints.json"
IMPORT_HEALTH = "source-import-health.json"


def fixture(kind, name):
    return json.loads((FIXTURES / kind / name).read_text(encoding="utf-8"))


class FakeClock:
    """Deterministic monotonic clock; sleep advances it."""

    def __init__(self):
        self.t = 0.0

    def clock(self):
        return self.t

    def sleep(self, s):
        self.t += s


class PublicationArrivalTest(unittest.TestCase):
    """JEG-1239: with the 720-minute content limit, a deploy that never lands
    leaves a valid previous copy (386 / 109 minutes old) that is still fresh.
    The watch warned after the 25-minute wait, then judged that copy and went
    green, so this run's publication counted as arrived when it had not."""

    def run_watch(self, served, published="published", extra=()):
        """served(name, n) -> fetch_json result for the n-th fetch of name
        (1-based; polls first, the judging fetch last). Real defaults: 25-minute
        window, 60-second interval, on a fake clock."""
        fc = FakeClock()
        counts = {CHECKPOINTS: 0, IMPORT_HEALTH: 0}

        def fake_fetch(url, timeout=30):
            name = url.rsplit("/", 1)[-1]
            counts[name] += 1
            return served(name, counts[name])

        real_await = w.await_arrival

        def fake_await(*a, **kw):
            kw.update(sleep=fc.sleep, clock=fc.clock)
            return real_await(*a, **kw)

        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            result_path = Path(td) / "result.json"
            pub = published if isinstance(published, Path) else FIXTURES / published
            argv = ["--dry-run", "--shadow-dir", str(Path(td) / "none"),
                    "--await-published", str(pub), "--result-json", str(result_path), *extra]
            with mock.patch.object(w, "fetch_json", fake_fetch), \
                 mock.patch.object(w, "await_arrival", fake_await), \
                 mock.patch.object(w, "_utcnow", lambda: JUDGED_AT), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                rc = w.main(argv)
            result = json.loads(result_path.read_text(encoding="utf-8"))
        return rc, result, out.getvalue(), err.getvalue(), counts, fc.t

    @staticmethod
    def lands_after(n_by_name):
        """The previous copy is served for the first n fetches, this run's after."""
        def served(name, n):
            kind = "published" if n > n_by_name.get(name, 10**6) else "served_previous"
            return fixture(kind, name), 200, 5
        return served

    def outcomes(self, result):
        return {c: r["outcome"] for c, r in result["publication_arrival"].items()}

    # -- failing before JEG-1239 ------------------------------------------
    def test_valid_old_served_copies_past_the_wait_are_not_arrival(self):
        """Reproduction from the stored fixtures. Before JEG-1239 this exited 0."""
        fc = FakeClock()
        served_counts = {"n": 0}

        def fake_fetch(url, timeout=30):
            served_counts["n"] += 1
            return fixture("served_previous", url.rsplit("/", 1)[-1]), 200, 5
        # Falls back to the pre-JEG-1239 names so this test runs, and fails on
        # the exit code, against the old watcher too.
        real_await = w.await_published if not hasattr(w, "await_arrival") else w.await_arrival
        target = "await_arrival" if hasattr(w, "await_arrival") else "await_published"

        def fake_await(*a, **kw):
            kw.update(sleep=fc.sleep, clock=fc.clock)
            return real_await(*a, **kw)
        with tempfile.TemporaryDirectory() as td:
            argv = ["--dry-run", "--shadow-dir", str(Path(td) / "none"),
                    "--await-published", str(FIXTURES / "published")]
            with mock.patch.object(w, "fetch_json", fake_fetch), \
                 mock.patch.object(w, target, fake_await), \
                 mock.patch.object(w, "datetime", mock.Mock(now=lambda tz=None: JUDGED_AT)), \
                 contextlib.redirect_stdout(io.StringIO()) as out, \
                 contextlib.redirect_stderr(io.StringIO()):
                rc = w.main(argv)
        self.assertEqual(25 * 60, fc.t, "the existing 25-minute window is used in full, unchanged")
        self.assertIn("served_pipeline_checkpoints_fresh: ok", out.getvalue(),
                      "content freshness is unchanged: 386 min is under the 720-min limit")
        self.assertNotEqual(0, rc, "valid but older served copies must not count as this run's arrival")
        self.assertEqual(w.EXIT_NOT_ARRIVED, rc)

    def test_mismatch_is_explicit_and_kept_apart_from_freshness(self):
        rc, result, out, err, _, _ = self.run_watch(self.lands_after({}))
        self.assertEqual(w.EXIT_NOT_ARRIVED, rc)
        self.assertEqual(rc, result["exit_code"])
        cp = result["publication_arrival"]["served_pipeline_checkpoints_fresh"]
        ih = result["publication_arrival"]["served_import_health_fresh"]
        self.assertEqual(("not_arrived", "served_copy_older_than_published"), (cp["outcome"], cp["reason"]))
        self.assertEqual(("not_arrived", "served_copy_older_than_published"), (ih["outcome"], ih["reason"]))
        self.assertEqual("2026-10-28T18:50:40+00:00", cp["expected_at"])
        self.assertEqual("2026-10-28T12:51:00+00:00", cp["served_at"])
        fresh = result["freshness"]
        self.assertTrue(fresh["served_pipeline_checkpoints_fresh"]["ok"])
        self.assertAlmostEqual(386, fresh["served_pipeline_checkpoints_fresh"]["age_minutes"], places=3)
        self.assertAlmostEqual(109, fresh["served_import_health_fresh"]["age_minutes"], places=3)
        line = next(l for l in out.splitlines() if l.startswith("publication_arrival: "))
        self.assertEqual(result["publication_arrival"],
                         json.loads(line[len("publication_arrival: "):])["artifacts"])
        self.assertIn("not a source-feed outage", err)
        self.assertNotIn("RED: stale", err)

    # -- arrival, boundaries and the grace window --------------------------
    def test_expected_arrival_is_green(self):
        rc, result, _, err, counts, t = self.run_watch(self.lands_after({CHECKPOINTS: 3, IMPORT_HEALTH: 1}))
        self.assertEqual(w.EXIT_OK, rc)
        self.assertEqual({"arrived"}, set(self.outcomes(result).values()))
        self.assertEqual(3 * 60, t, "stops polling once both arrived")
        self.assertEqual("", err)

    def test_arrival_on_the_last_poll_inside_the_window(self):
        # Polls run at minutes 0..25 (26 polls); the 26th is at the boundary.
        rc, result, _, _, _, t = self.run_watch(self.lands_after({CHECKPOINTS: 25, IMPORT_HEALTH: 25}))
        self.assertEqual(25 * 60, t)
        self.assertEqual(w.EXIT_OK, rc)
        self.assertEqual({"arrived"}, set(self.outcomes(result).values()))

    def test_late_arrival_seen_by_the_judging_fetch_recovers(self):
        rc, result, _, _, _, _ = self.run_watch(self.lands_after({CHECKPOINTS: 26, IMPORT_HEALTH: 26}))
        self.assertEqual(w.EXIT_OK, rc, "a copy that lands after the window but before judging has arrived")
        self.assertEqual({"arrived"}, set(self.outcomes(result).values()))

    def test_served_timestamp_equal_to_published_is_arrival(self):
        want = w.parse_ts("2026-10-28T18:50:40Z")
        same = w.judge_arrival(want, ({"generated_at": "2026-10-28T18:50:40.000000+00:00"}, 200, 1), ("generated_at",))
        self.assertEqual("arrived", same["outcome"])
        older = w.judge_arrival(want, ({"generated_at": "2026-10-28T18:50:39.999999+00:00"}, 200, 1), ("generated_at",))
        self.assertEqual(("not_arrived", "served_copy_older_than_published"), (older["outcome"], older["reason"]))

    def test_partial_arrival_of_the_pair_is_not_arrival(self):
        rc, result, _, err, _, _ = self.run_watch(self.lands_after({CHECKPOINTS: 2}))
        self.assertEqual(w.EXIT_NOT_ARRIVED, rc)
        self.assertEqual({"served_pipeline_checkpoints_fresh": "arrived",
                          "served_import_health_fresh": "not_arrived"}, self.outcomes(result))
        self.assertIn("served_import_health_fresh", err)
        self.assertNotIn("served_pipeline_checkpoints_fresh (", err)

    # -- missing / malformed timestamps ------------------------------------
    def test_missing_or_malformed_served_timestamp_is_unverified(self):
        for bad in ({"sources": {}}, {"generated_at": "not-a-date", "checked_at": "2026-13-45T99:00:00Z"}):
            with self.subTest(bad=bad):
                def served(name, n, bad=bad):
                    return (bad if name == CHECKPOINTS else fixture("published", name)), 200, 5
                rc, result, _, err, _, _ = self.run_watch(served)
                cp = result["publication_arrival"]["served_pipeline_checkpoints_fresh"]
                self.assertEqual(("unverified", "served_timestamp_missing"), (cp["outcome"], cp["reason"]))
                self.assertEqual("arrived", self.outcomes(result)["served_import_health_fresh"])
                self.assertEqual(w.EXIT_STALE, rc, "freshness stays fail-closed on a missing timestamp")
                self.assertNotIn("did not arrive", err)

    def test_published_copy_without_timestamp_is_unverified_not_failed(self):
        with tempfile.TemporaryDirectory() as td:
            pub = Path(td)
            (pub / CHECKPOINTS).write_text(json.dumps({"sources": {}}))
            (pub / IMPORT_HEALTH).write_text((FIXTURES / "published" / IMPORT_HEALTH).read_text())
            rc, result, _, err, counts, _ = self.run_watch(self.lands_after({CHECKPOINTS: 0, IMPORT_HEALTH: 0}),
                                                           published=pub)
        cp = result["publication_arrival"]["served_pipeline_checkpoints_fresh"]
        self.assertEqual(("unverified", "published_timestamp_missing"), (cp["outcome"], cp["reason"]))
        self.assertEqual(w.EXIT_ARRIVAL_UNVERIFIED, rc)
        self.assertIn("UNVERIFIED", err)
        self.assertNotIn("did not arrive", err)
        self.assertEqual(1, counts[CHECKPOINTS], "nothing to await: only the judging fetch")

    # -- fetch denial / error and recovery ---------------------------------
    def test_denied_fetch_is_unknown_not_a_mismatch_or_outage(self):
        rc, result, _, err, _, _ = self.run_watch(lambda name, n: (None, 403, 5))
        for check_id, r in result["publication_arrival"].items():
            self.assertEqual(("unverified", "fetch_denied", 403), (r["outcome"], r["reason"], r["http_status"]), check_id)
        self.assertEqual(w.EXIT_STALE, rc, "the served-copy freshness check stays fail-closed (unchanged)")
        self.assertEqual(403, result["freshness"]["served_import_health_fresh"]["http_status"])
        self.assertNotIn("did not arrive", err)
        self.assertNotIn("outage", err.replace("not a source-feed outage", ""))
        self.assertIn("not declared failed or recovered", err)

    def test_fetch_error_is_unverified(self):
        rc, result, _, _, _, _ = self.run_watch(lambda name, n: (None, None, 5))
        self.assertEqual({"fetch_failed"}, {r["reason"] for r in result["publication_arrival"].values()})

    def test_denied_then_recovered_counts_as_arrival(self):
        def served(name, n):
            return (None, 403, 5) if n <= 4 else (fixture("published", name), 200, 5)
        rc, result, _, err, _, t = self.run_watch(served)
        self.assertEqual(w.EXIT_OK, rc)
        self.assertEqual({"arrived"}, set(self.outcomes(result).values()))
        self.assertEqual(4 * 60, t)

    def test_old_copy_then_denied_judging_fetch_is_unknown(self):
        # Latest evidence inaccessible: arrival is unknown, not declared missed.
        def served(name, n):
            return (None, 403, 5) if n > 26 else (fixture("served_previous", name), 200, 5)
        rc, result, _, _, _, _ = self.run_watch(served)
        self.assertEqual({"unverified"}, set(self.outcomes(result).values()))

    def test_arrival_seen_then_previous_copy_at_judgment_is_not_arrived(self):
        # Codex review f97f58ed (a): the wait saw this run's copy, then the
        # judged copy is the previous deploy again (CDN flip or rollback).
        def served(name, n):
            kind = "published" if n == 1 else "served_previous"
            return fixture(kind, name), 200, 5
        rc, result, _, err, counts, _ = self.run_watch(served)
        self.assertEqual({CHECKPOINTS: 2, IMPORT_HEALTH: 2}, counts, "one poll, then the judging fetch")
        for check_id, r in result["publication_arrival"].items():
            self.assertEqual(("not_arrived", "served_copy_older_than_published"), (r["outcome"], r["reason"]), check_id)
            self.assertEqual("arrived", r["observed_during_wait"]["outcome"], "the earlier observation is kept")
            self.assertEqual(r["expected_at"], r["observed_during_wait"]["served_at"])
        self.assertEqual("2026-10-28T12:51:00+00:00",
                         result["publication_arrival"]["served_pipeline_checkpoints_fresh"]["served_at"],
                         "served_at is the judged copy's, not the polled one")
        self.assertEqual(w.EXIT_NOT_ARRIVED, rc, "a regressed served copy is not current publication success")
        self.assertIn("did not arrive", err)

    def test_arrival_seen_then_denied_judging_fetch_is_unverified(self):
        # Codex review f97f58ed (b): the wait saw this run's copy (HTTP 200),
        # then the judging fetch is denied (HTTP 403).
        def served(name, n):
            return (fixture("published", name), 200, 5) if n == 1 else (None, 403, 5)
        rc, result, _, err, _, _ = self.run_watch(served)
        for check_id, r in result["publication_arrival"].items():
            self.assertEqual(("unverified", "fetch_denied", 403), (r["outcome"], r["reason"], r["http_status"]), check_id)
            self.assertIsNone(r["served_at"])
            self.assertEqual(("arrived", 200), (r["observed_during_wait"]["outcome"],
                                                r["observed_during_wait"]["http_status"]))
        self.assertEqual(w.EXIT_STALE, rc, "freshness stays fail-closed on the denied copy (precedence)")
        self.assertNotIn("did not arrive", err)
        self.assertIn("not declared failed or recovered", err)

    def test_fetch_json_keeps_the_http_status_of_a_denial(self):
        denied = w.urllib.error.HTTPError("https://example.invalid/x.json", 403, "Forbidden", {}, None)
        with mock.patch.object(w.urllib.request, "urlopen", side_effect=denied):
            payload, status, _ = w.fetch_json("https://example.invalid/x.json")
        self.assertIsNone(payload)
        self.assertEqual(403, status)
        with mock.patch.object(w.urllib.request, "urlopen", side_effect=OSError("boom")):
            self.assertEqual((None, None), w.fetch_json("https://example.invalid/x.json")[:2])

    # -- compatibility -----------------------------------------------------
    def test_without_await_nothing_is_expected(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as td:
            res = Path(td) / "r.json"
            with mock.patch.object(w, "fetch_json", lambda url, timeout=30: (fixture("served_previous", url.rsplit("/", 1)[-1]), 200, 5)), \
                 mock.patch.object(w, "_utcnow", lambda: JUDGED_AT), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = w.main(["--dry-run", "--shadow-dir", str(Path(td) / "none"), "--result-json", str(res)])
            result = json.loads(res.read_text())
        self.assertEqual(w.EXIT_OK, rc)
        self.assertEqual({"not_awaited"}, {r["outcome"] for r in result["publication_arrival"].values()})

    def test_await_published_still_returns_the_names_behind(self):
        fc = FakeClock()
        behind = w.await_published(
            "https://example.invalid/", FIXTURES / "published", 120, 60,
            fetch=lambda url: ((fixture("published", CHECKPOINTS) if url.endswith(CHECKPOINTS)
                                else fixture("served_previous", IMPORT_HEALTH)), 200, 5),
            sleep=fc.sleep, clock=fc.clock, log=lambda *_: None)
        self.assertEqual([IMPORT_HEALTH], behind)


if __name__ == "__main__":
    unittest.main()
