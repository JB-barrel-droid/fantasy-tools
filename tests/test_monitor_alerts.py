"""GAP-ALERT-CHANNEL: pipelines/monitor_alerts.py raises an alert only for real
failures and delivers each one once (one open `ops-alert` issue per key,
closed when it clears).

Each rule is negative-tested: the state it names must alert, the neighbouring
benign state must not, and a mutated rule (threshold removed, dedup removed)
must be caught by the same assertions.
"""
import contextlib
import io
import json
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from pipelines import monitor_alerts as ma

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


def iso(dt):
    return dt.isoformat()


def summary(state="healthy", last_ok_hours=1.0, **extra):
    s = {"overall": "green", "evaluator_stale": False,
         "checks": [{"check_id": "rebuild_chain", "state": state, "reason": "r",
                     "last_ok_at": iso(NOW - timedelta(hours=last_ok_hours)) if last_ok_hours is not None else None}]}
    s.update(extra)
    return s


def health(**ages_days):
    return {"sources": {src: {"db_latest_arrived_at": iso(NOW - timedelta(days=d)), "content_vintage": "Week 5",
                              "status": "ok"} for src, d in ages_days.items()}}


def keys(alerts):
    return sorted(a.key for a in alerts)


class ConditionsTest(unittest.TestCase):
    def test_healthy_system_raises_nothing(self):
        self.assertEqual([], ma.evaluate(summary(), health(espn=1, cbs=6), NOW))

    def test_rebuild_chain_failing_for_hours_alerts(self):
        self.assertEqual(["rebuild-chain-failing"], keys(ma.evaluate(summary("error", 13), health(), NOW)))
        self.assertEqual(["rebuild-chain-failing"], keys(ma.evaluate(summary("missed", None), health(), NOW)))

    def test_one_red_run_between_green_ones_does_not_alert(self):
        # 2026-10-08 08:48-09:00: three red chain runs, green again at 09:50.
        self.assertEqual([], ma.evaluate(summary("error", 2), health(), NOW))

    def test_guard_catches_a_rule_without_the_publish_threshold(self):
        with mock.patch.object(ma, "REBUILD_STALE_HOURS", 0):
            self.assertEqual(["rebuild-chain-failing"],
                             keys(ma.evaluate(summary("error", 2), health(), NOW, stale_hours=ma.REBUILD_STALE_HOURS)))

    def test_source_stuck_past_threshold_alerts(self):
        self.assertEqual(["source-stuck-cbs"], keys(ma.evaluate(summary(), health(espn=1, cbs=11), NOW)))

    def test_recent_content_date_beats_an_old_landing_time(self):
        # ESPN upserts keep db_latest_arrived_at old while content moves on.
        h = {"sources": {"espn": {"db_latest_arrived_at": iso(NOW - timedelta(days=12)),
                                  "content_vintage": "2026-10-07"}}}
        self.assertEqual([], ma.evaluate(summary(), h, NOW))

    def test_source_with_no_timestamp_is_stuck_not_fine(self):
        h = {"sources": {"usatoday": {"content_vintage": "Week 5"}}}
        self.assertEqual(["source-stuck-usatoday"], keys(ma.evaluate(summary(), h, NOW)))

    def test_unreadable_monitor_alerts_and_suppresses_chain_guess(self):
        self.assertEqual(["monitor-unreadable"],
                         keys(ma.evaluate({"read_error": "HTTP 404", "checks": []}, health(), NOW)))
        self.assertEqual(["monitor-unreadable"], keys(ma.evaluate(summary(evaluator_stale=True), health(), NOW)))

    def test_security_regression_alerts_only_on_ok_false(self):
        bad = {"schema": "ddf-security-posture-v1", "ok": False, "tables_without_rls": 3}
        self.assertEqual(["security-regression"], keys(ma.evaluate(summary(security=bad), health(), NOW)))
        for fine in ({"ok": True}, {"read_error": "function does not exist"}, None):
            self.assertEqual([], ma.evaluate(summary(security=fine), health(), NOW), fine)

    def test_yellow_checks_and_holds_stay_warnings(self):
        s = summary()
        s["checks"] += [{"check_id": "rebuild_chain_source_held", "state": "error", "last_ok_at": None},
                        {"check_id": "usatoday_trade_chart_ingest", "state": "missed", "last_ok_at": None}]
        self.assertEqual([], ma.evaluate(s, health(), NOW))


class FakeIssues:
    def __init__(self, open_issues=()):
        self.issues = {i["number"]: dict(i) for i in open_issues}
        self.created, self.updated, self.closed = [], [], []

    def ensure_label(self):
        pass

    def open_issues(self):
        return [i for i in self.issues.values() if i.get("state", "open") == "open"]

    def create(self, title, body):
        n = max(self.issues, default=0) + 1
        self.issues[n] = {"number": n, "title": title, "body": body, "state": "open"}
        self.created.append(n)
        return self.issues[n]

    def update(self, number, body):
        self.issues[number]["body"] = body
        self.updated.append(number)

    def close(self, number, comment):
        self.issues[number]["state"] = "closed"
        self.closed.append(number)


def chain_alert():
    return ma.evaluate(summary("error", 20), health(), NOW)


class DeliveryTest(unittest.TestCase):
    def run_once(self, client, alerts):
        ma.reconcile(alerts, client, NOW, mention="JB-barrel-droid", log=lambda *_: None)

    def test_opens_once_then_updates_silently_then_closes(self):
        gh = FakeIssues()
        self.run_once(gh, chain_alert())
        self.assertEqual([1], gh.created)
        self.assertIn("@JB-barrel-droid", gh.issues[1]["body"])
        self.assertIn("ops-alert-key: rebuild-chain-failing", gh.issues[1]["body"])
        self.run_once(gh, chain_alert())
        self.run_once(gh, chain_alert())
        self.assertEqual([1], gh.created, "a still-failing chain must not open a second issue")
        self.assertEqual([1, 1], gh.updated)
        self.run_once(gh, [])
        self.assertEqual([1], gh.closed)
        self.run_once(gh, chain_alert())
        self.assertEqual([1, 2], gh.created, "a new failure after it cleared opens a new issue")

    def test_guard_catches_delivery_without_dedup(self):
        gh = FakeIssues()
        with mock.patch.object(ma, "issue_key", lambda issue: None):  # the broken state: keys never match
            self.run_once(gh, chain_alert())
            self.run_once(gh, chain_alert())
        self.assertEqual(2, len(gh.created), "without the key marker every run re-opens: this guard must see it")

    def test_unrelated_open_issues_are_left_alone(self):
        gh = FakeIssues([{"number": 7, "title": "manual", "body": "no marker", "state": "open"}])
        self.run_once(gh, [])
        self.assertEqual([], gh.closed)

    def test_webhook_gets_transitions_only(self):
        gh, sent = FakeIssues(), []
        with mock.patch.object(ma, "post_webhook", lambda url, text: sent.append(text)):
            for alerts in (chain_alert(), chain_alert(), []):
                ma.reconcile(alerts, gh, NOW, webhook="https://hooks.example/x", log=lambda *_: None)
        self.assertEqual(2, len(sent))
        self.assertTrue(sent[0].startswith("ALERT") and sent[1].startswith("CLEARED"))

    def test_main_never_fails_the_run_and_dry_run_touches_nothing(self):
        with mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t"}), \
             mock.patch.object(ma.GitHubIssues, "ensure_label", side_effect=OSError("network down")):
            self.assertEqual(0, ma.main(["--summary", "/nonexistent.json", "--import-health", "/nonexistent.json"]))
        with mock.patch.object(ma, "reconcile") as rec:
            self.assertEqual(0, ma.main(["--summary", "/nonexistent.json", "--import-health", "/x", "--dry-run"]))
            rec.assert_not_called()


class FakeResponse:
    def __init__(self, payload):
        self.raw = json.dumps(payload).encode()

    def read(self):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def fake_github(has_issues):
    """urlopen stand-in for a repo with Issues on/off. With Issues off GitHub
    still answers GET /issues with 200 [] and rejects the create with 410
    (observed on JB-barrel-droid/fantasy-tools, 2026-10-08)."""
    calls = []

    def urlopen(req, timeout=None):
        method, url = req.get_method(), req.full_url
        calls.append((method, url))
        if method == "GET" and url.endswith("/repos/o/r"):
            return FakeResponse({"has_issues": has_issues})
        if method == "GET":
            return FakeResponse([])
        if method == "POST" and url.endswith("/labels"):
            return FakeResponse({})
        if method == "POST" and url.endswith("/issues") and not has_issues:
            raise urllib.error.HTTPError(url, 410, "Issues has been disabled in this repository.", {}, None)
        return FakeResponse({"number": 1, "html_url": "u"})
    return urlopen, calls


class IssuesDisabledTest(unittest.TestCase):
    """2026-10-08: the repo has GitHub Issues disabled, so the default
    channel cannot open an ops-alert issue. A firing alert must still be
    visible: a named warning and the alert in the job summary."""

    def run_main(self, urlopen, td):
        out = io.StringIO()
        summary_path = Path(td) / "summary.md"
        summary_file = Path(td) / "monitoring-summary.json"
        summary_file.write_text(json.dumps(summary("error", 20)))
        health_file = Path(td) / "health.json"
        health_file.write_text(json.dumps(health()))
        env = {"GITHUB_REPOSITORY": "o/r", "GITHUB_TOKEN": "t", "GITHUB_STEP_SUMMARY": str(summary_path)}
        with mock.patch.dict("os.environ", env), \
             mock.patch.object(ma.urllib.request, "urlopen", urlopen), \
             contextlib.redirect_stdout(out):
            rc = ma.main(["--summary", str(summary_file), "--import-health", str(health_file)])
        text = summary_path.read_text(encoding="utf-8") if summary_path.exists() else ""
        return rc, out.getvalue(), text

    def test_disabled_issues_put_the_alert_in_the_job_summary(self):
        urlopen, calls = fake_github(has_issues=False)
        with tempfile.TemporaryDirectory() as td:
            rc, out, text = self.run_main(urlopen, td)
        self.assertEqual(0, rc, "alert delivery never fails the run")
        self.assertIn("GitHub Issues are disabled", out)
        self.assertIn("Rebuild chain is failing", text)
        self.assertIn("GitHub Issues are disabled", text)
        self.assertFalse(any(m == "POST" and u.endswith("/issues") for m, u in calls),
                         "with has_issues=false no create is attempted")

    def test_a_410_on_create_is_named_not_swallowed(self):
        # The repo flag can lag the API; the 410 itself must map to the same
        # visible fallback, not a generic "delivery failed".
        urlopen, _ = fake_github(has_issues=False)

        def flag_says_on(req, timeout=None):
            if req.get_method() == "GET" and req.full_url.endswith("/repos/o/r"):
                return FakeResponse({"has_issues": True})
            return urlopen(req, timeout)
        with tempfile.TemporaryDirectory() as td:
            rc, out, text = self.run_main(flag_says_on, td)
        self.assertEqual(0, rc)
        self.assertIn("HTTP 410", out)
        self.assertIn("Rebuild chain is failing", text)

    def test_enabled_issues_still_open_the_issue(self):
        urlopen, calls = fake_github(has_issues=True)
        with tempfile.TemporaryDirectory() as td:
            rc, out, text = self.run_main(urlopen, td)
        self.assertEqual(0, rc)
        self.assertTrue(any(m == "POST" and u.endswith("/issues") for m, u in calls))
        self.assertNotIn("disabled", out)
        self.assertIn("Rebuild chain is failing", text)


def pulse(**statuses):
    return {"checked_at": "2026-10-08T23:00:00Z", "sources": [
        {"source": s, "label": s.upper(), "status": st, "stored_week": 5, "chart_week": 5,
         "stages": {"stored_vs_chart": {"status": st, "summary": f"{s} {st}"}},
         "worst_examples": [{"stage": "stored_vs_chart", "grain": "half|1", "name": "Jahmyr Gibbs",
                             "left": 74.0, "right": 74.5, "type": "value_mismatch"}]} for s, st in statuses.items()]}


class FidelityPulseAlertsTest(unittest.TestCase):
    """JEG-480: a red fidelity source opens one fidelity-red-<source> issue; the
    pulse run and the health-artifacts run never close each other's issues."""

    def test_red_source_alerts_amber_does_not(self):
        alerts = ma.pulse_alerts(pulse(cbs="red", usatoday="amber", fantasypros="green"))
        self.assertEqual(["fidelity-red-cbs"], [a.key for a in alerts])
        self.assertIn("Jahmyr Gibbs", alerts[0].body)
        self.assertEqual([], ma.pulse_alerts({"read_error": "x"}))

    def test_runs_own_disjoint_keys(self):
        gh = FakeIssues()
        ma.reconcile(chain_alert(), gh, NOW, log=lambda *_: None)
        ma.reconcile(ma.pulse_alerts(pulse(cbs="red")), gh, NOW, log=lambda *_: None,
                     scope=ma.in_pulse_scope, source="fidelity-pulse.yml")
        self.assertEqual([1, 2], gh.created)
        self.assertIn("by fidelity-pulse.yml", gh.issues[2]["body"])
        # health run with nothing failing must not close the pulse issue ...
        ma.reconcile([], gh, NOW, log=lambda *_: None)
        self.assertEqual([1], gh.closed)
        # ... and a green pulse closes only its own
        ma.reconcile(ma.pulse_alerts(pulse(cbs="green")), gh, NOW, log=lambda *_: None,
                     scope=ma.in_pulse_scope, source="fidelity-pulse.yml")
        self.assertEqual([1, 2], gh.closed)

    def test_unreadable_pulse_leaves_issues_untouched(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict("os.environ", {"GITHUB_REPOSITORY": "o/r",
                                                                              "GITHUB_TOKEN": "t"}), \
                mock.patch.object(ma, "reconcile") as rec, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(0, ma.main(["--pulse", str(Path(d) / "missing.json")]))
            rec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
