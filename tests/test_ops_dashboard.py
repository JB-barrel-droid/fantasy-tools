"""Ops dashboard (modules/status.html): headless render against fixture data.

The page answers "is everything working and fresh?" from the published
producers. This test builds small fixture sites with a pinned clock and checks
that the rendered page turns each card green when the data is fresh and
healthy, amber when a feed is stale, and red when something failed or a feed is
missing. It then proves the checks can fail: two broken copies of the page
(staleness ignored; failures not propagated) must each be caught.

Needs Playwright with a Chromium (CHROMIUM_PATH, Playwright's own, or Google
Chrome); skips otherwise. Static checks (noindex, no public links) live in
tests/test_launch_qa_surfaces.py and tests/test_launch_front_door.py.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import os
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "modules" / "status.html"
sys.path.insert(0, str(ROOT / "pipelines"))

NOW = "2026-10-08T12:00:00Z"
SHA = "abc1234def5678abc1234def5678abc1234def56"
TAG = "tv-20261008-1100-abc1234"
SOURCES = ["usatoday", "fantasycalc", "fantasypros", "cbs", "espn", "cbsros", "razzball"]
INGEST = {"usatoday": "usatoday_trade_chart_ingest", "cbs": "cbs_trade_chart_ingest",
          "fantasypros": "fantasypros_trade_chart_ingest", "fantasycalc": "fantasycalc_weekly_save",
          "espn": "espn_supabase_sync", "cbsros": "cbsros_supabase_sync", "razzball": "razzball_projections_sync"}


def ago(hours: float) -> str:
    from datetime import datetime, timedelta, timezone
    t = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc) - timedelta(hours=hours)
    return t.isoformat().replace("+00:00", "Z")


def green_site() -> dict:
    """Relative path -> JSON document (or text for .html) for a healthy site."""
    checks = [{"check_id": cid, "status": "green", "state": "healthy", "reason": "last run ok",
               "last_run_at": ago(2), "last_ok_at": ago(2), "workflow": "trade-chart-ingest.yml",
               "pg_cron_job": "trade-chart-ingest-live", "owner_type": "github_actions"} for cid in INGEST.values()]
    checks.append({"check_id": "rebuild_chain", "status": "green", "state": "healthy", "reason": "last run ok",
                   "last_run_at": ago(2), "last_ok_at": ago(2), "workflow": "rebuild-chain.yml",
                   "pg_cron_job": "rebuild-chain-live"})
    summary = {
        "schema": "ddf-monitoring-summary-v1", "generated_at": ago(1), "overall": "green",
        "headline": "22 of 22 checks passing", "evaluator_last_run": ago(1), "evaluator_stale": False,
        "counts": {"total": len(checks), "green": len(checks), "yellow": 0, "red": 0},
        "checks": checks,
        "cron_jobs": [
            {"jobname": "rebuild-chain-live", "schedule": "17 */6 * * *", "active": True, "dispatches": "rebuild-chain.yml",
             "last_start": ago(1.7), "last_status": "succeeded", "dispatch_outcome": "ok", "dispatched_at": ago(1.7)},
            {"jobname": "rebuild-chain-retry", "schedule": "47 */6 * * *", "active": True, "dispatches": "rebuild-chain.yml",
             "last_start": ago(1.2), "last_status": "succeeded", "dispatch_outcome": "ok", "dispatched_at": ago(1.2)},
            {"jobname": "trade-chart-ingest-live", "schedule": "7 12 * * *", "active": True, "dispatches": "trade-chart-ingest.yml",
             "last_start": ago(23.9), "last_status": "succeeded", "dispatch_outcome": "ok", "dispatched_at": ago(23.9)},
            {"jobname": "monitoring-evaluator-5min", "schedule": "*/5 * * * *", "active": True, "dispatches": None,
             "last_start": ago(0.05), "last_status": "succeeded"},
        ],
        "producer": {"workflow": "health-artifacts.yml", "pg_cron_job": "health-artifacts-live",
                     "cadence_minutes": 360, "stale_after_minutes": 720},
        "security": {"schema": "ddf-security-posture-v1", "checked_at": ago(1), "ok": True,
                     "tables_without_rls": 0, "anon_or_auth_write_grants": 0, "public_definer_views": 0,
                     "mutable_search_path_functions": 0, "anon_executable_definer_functions": 0,
                     "api_definer_views_accepted": 3, "details": {}},
    }
    run = lambda wf, h=2: {"created_at": ago(h), "updated_at": ago(h - 0.05), "status": "completed",  # noqa: E731
                           "conclusion": "success", "event": "workflow_dispatch", "duration_s": 180}
    gha = {"generated_at": ago(2), "workflows": [
        {"name": "Rebuild comparison chain", "path": ".github/workflows/rebuild-chain.yml", "last_run": run("rc"), "consecutive_failures": 0},
        {"name": "Trade-chart ingest", "path": ".github/workflows/trade-chart-ingest.yml", "last_run": run("ti"), "consecutive_failures": 0},
    ]}
    chain = {"run_at": ago(2), "nfl_week": 5, "success": True, "outcome": "green", "held": [], "failed": [],
             "hold_severity": "none", "held_detail": {}, "runner": "github-actions",
             "fit": {"status": "ok", "detail": "fit complete"}, "adjusted_sections": {"status": "ok", "detail": "built"},
             "detail": {s: {"status": "ok", "stage": "complete", "detail": "promoted 3/3", "promoted": 3, "sections": 3} for s in SOURCES},
             "source_vintages": {s: {"content_vintage": "2026-10-06", "content_week": 5, "lagging_one_week": False} for s in SOURCES}}
    health = {"checked_at": ago(1), "nfl_week": 5, "sources": {s: {
        "status": "ok", "blocking": False, "content_vintage": "2026-10-06", "content_week": 5, "row_count": 500,
        "db_latest_arrived_at": ago(20), "failure_reason": None} for s in SOURCES}}
    cps = {"generated_at": ago(1), "checkpoints": [{"key": "c1_publication", "label": "C1 · Publication"},
                                                    {"key": "c10_rendered", "label": "C10 · Rendered"}],
           "sources": {s: {"label": s, "checkpoints": {"c1_publication": {"status": "ok", "reason": "fine"},
                                                       "c10_rendered": {"status": "ok", "reason": "fine"}}} for s in SOURCES}}
    ops = {"schema": "ddf-ops-status-v1", "generated_at": ago(1), "blocks": {
        "deploy": {"status": "ok", "as_of": ago(1), "main_sha": SHA, "main_committed_at": ago(1.2), "last_success_sha": SHA,
                   "live_tag": TAG, "verdict": "current",
                   "pages_runs": [{"status": "completed", "conclusion": "success", "created_at": ago(1.1), "event": "push",
                                   "duration_s": 200, "head_sha": SHA, "html_url": "https://example.invalid/run/1"}]},
        "synthetic": {"status": "ok", "as_of": ago(1), "run": {"created_at": ago(6), "conclusion": "success",
                                                               "html_url": "https://example.invalid/run/2"},
                      "report": {"passed": True, "liveTag": TAG, "problems": [], "pageErrors": [], "pages": [
                          {"name": n, "url": f"https://example.invalid/{n}", "httpStatus": 404 if n == "not-found" else 200,
                           "passed": True, "problems": [], "pageErrors": [], "tabs": []}
                          for n in ("root", "v2", "classic", "not-found")]}},
        "alerts": {"status": "ok", "as_of": ago(1), "label": "ops-alert", "open": []},
        "identity": {"status": "ok", "as_of": ago(1), "queue_total": 0,
                     "by_source": [{"source": "*", "review": 0, "unmatched": 0, "provisional": 0, "verified": 500,
                                    "last_seen_at": ago(20), "queued": 0}]},
        "players_bake": {"status": "ok", "as_of": ago(3), "players_as_of": "2026-10-08", "n_players": 613,
                         "snapshots": {"espn": "2026-10-07", "rz": "2026-10-07"}},
    }}
    fresh = {"generated_at": ago(5), "items": [{"label": "Players artifact as_of", "value": "2026-10-08", "age_days": 0,
                                                 "max_age_days": 2, "color": "green", "note": "unchanged"}]}
    history = {"fixture_built_at": ago(2), "content_week": 5, "weeks": {
        "4": {"frozen": True, "sources": {s: {"complete": True} for s in SOURCES}},
        "5": {"frozen": False, "sources": {s: {"complete": True} for s in SOURCES}}},
        "served": {s: {"week": 5} for s in SOURCES}}
    surfaces = {"surfaces": [
        {"id": "ops", "label": "Ops status", "page": "Monitor", "url": "modules/ops-status.json", "count_path": "blocks",
         "min_count": 5, "time_field": "generated_at", "max_age_hours": 7, "required": True},
        {"id": "fresh", "label": "Freshness", "page": "Trade Value Dashboard", "url": "assets/reference-freshness.json",
         "count_path": "items", "min_count": 1, "time_field": "generated_at", "max_age_hours": 26, "required": True}]}
    return {
        "index.html": f'<!doctype html><html><head><meta name="trade-chart-build" content="{TAG}"></head><body></body></html>',
        "modules/monitoring-summary.json": summary, "modules/github-actions.json": gha,
        "modules/comparison-chain-status.json": chain, "modules/source-import-health.json": health,
        "modules/pipeline-checkpoints.json": cps, "modules/ops-status.json": ops, "modules/surfaces.json": surfaces,
        "assets/reference-freshness.json": fresh, "assets/history/index.json": history,
        "modules/e2e-fidelity.json": {"generated_at": ago(4), "summary": {"status": "ok", "n_failures": 0},
                                      "sources": {s: {"status": "ok"} for s in ("fantasycalc", "usatoday", "fantasypros", "cbs")}},
        "modules/data-accuracy.json": {"generated_at": ago(4), "status": "ok", "violations": [],
                                       "checks": [{"name": "espn_ineligible_cross_check", "status": "ok"},
                                                  {"name": "espn_zeroed_staleness", "status": "ok"}]},
        "modules/input-lineage.json": {"generated_at": ago(2), "checked": 12, "mismatches": []},
        "modules/source-value-lineage.json": {"generated_at": ago(20), "sources": {"cbs": {}}},
    }


def stale_site() -> dict:
    """Producers stopped: timestamps past the amber limit, below the red one."""
    site = green_site()
    site["modules/comparison-chain-status.json"]["run_at"] = ago(10)
    site["modules/source-import-health.json"]["checked_at"] = ago(10)
    site["modules/ops-status.json"]["blocks"]["synthetic"]["run"]["created_at"] = ago(40)
    site["modules/source-value-lineage.json"]["generated_at"] = ago(60)          # a stale manual audit
    site["modules/input-lineage.json"]["mismatches"] = [{"section": "cbsros", "reason": "lineage_raw_vintage_mismatch"}]
    return site


def failed_site() -> dict:
    site = green_site()
    chain = site["modules/comparison-chain-status.json"]
    chain.update(success=False, outcome="failed", failed=["post_rebuild_validation"],
                 post_rebuild_validation={"status": "failed", "detail": "FAIL test_static_export"})
    summary = site["modules/monitoring-summary.json"]
    summary["overall"] = "red"
    summary["checks"][0].update(status="red", state="error", reason="last run failed (SOURCE_BLOCKED)")
    summary["security"].update(ok=False, tables_without_rls=1, details={"tables_without_rls": ["monitoring.check_config"]})
    ops = site["modules/ops-status.json"]["blocks"]
    ops["deploy"]["pages_runs"].insert(0, {"status": "completed", "conclusion": "failure", "created_at": ago(0.5),
                                           "event": "push", "duration_s": 90, "head_sha": "f" * 40, "html_url": "x"})
    ops["alerts"]["open"] = [{"number": 7, "title": "[ops-alert] rebuild-chain-failing", "key": "rebuild-chain-failing",
                              "created_at": ago(3), "updated_at": ago(1), "html_url": "https://example.invalid/7"}]
    ops["synthetic"]["report"]["passed"] = False
    ops["synthetic"]["report"]["pages"][2].update(passed=False, problems=["#weightsReadout is empty"])
    del site["assets/reference-freshness.json"]   # a missing published file: asset 404
    site["modules/data-accuracy.json"].update(status="bad", violations=[{"check": "espn_zeroed_staleness"}])
    return site


# Expected card statuses per scenario (cards not listed must be "ok").
EXPECT = {
    "green": {"__banner__": "ok"},
    "stale": {"__banner__": "warn", "chain": "warn", "ingest": "warn", "synthetic": "warn", "derived": "warn"},
    "failed": {"__banner__": "bad", "chain": "bad", "jobs": "bad", "ingest": "bad", "deploy": "bad",
               "alerts": "bad", "monitor": "bad", "synthetic": "bad", "surfaces": "bad", "freshness": "bad",
               "security": "bad", "derived": "bad"},
}
SCENARIOS = {"green": green_site, "stale": stale_site, "failed": failed_site}


def write_site(target: Path, site: dict, page_html: str) -> None:
    for rel, doc in site.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(doc if isinstance(doc, str) else json.dumps(doc), encoding="utf-8")
    (target / "modules" / "status.html").write_text(page_html, encoding="utf-8")


@contextlib.contextmanager
def serve(directory: Path):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    handler = functools.partial(Handler, directory=str(directory))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/"
        finally:
            server.shutdown()


def chromium_path(playwright):
    for c in (os.environ.get("CHROMIUM_PATH"), playwright.chromium.executable_path,
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", shutil.which("chromium")):
        if c and Path(c).exists():
            return c
    return None


def render(browser, site: dict, page_html: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        write_site(Path(tmp), site, page_html)
        with serve(Path(tmp)) as base:
            page = browser.new_page(viewport={"width": 1300, "height": 900})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(f"{base}modules/status.html?now={NOW}")
            page.wait_for_selector("body[data-ready='1']", timeout=30000)
            out = page.evaluate("""() => ({
              cards: Object.fromEntries([...document.querySelectorAll('[data-card]')].map(c => [c.dataset.card, c.dataset.status])),
              banner: document.getElementById('banner').dataset.overall,
              labels: [...document.querySelectorAll('[data-card] h3 .pill')].map(p => p.textContent.trim()) })""")
            page.close()
    out["errors"] = errors
    return out


def problems(result: dict, expect: dict) -> list[str]:
    out = []
    if result["errors"]:
        out.append(f"page errors: {result['errors']}")
    if result["banner"] != expect["__banner__"]:
        out.append(f"banner {result['banner']} != {expect['__banner__']}")
    for card, got in result["cards"].items():
        want = expect.get(card, "ok")
        if got != want:
            out.append(f"{card}: {got} != {want}")
    for card in expect:
        if card != "__banner__" and card not in result["cards"]:
            out.append(f"{card}: not rendered")
    # Status is never colour alone: every card's pill carries a text label.
    if not all(result["labels"]) or set(result["labels"]) - {"OK", "Attention", "Failed", "Unknown"}:
        out.append(f"unexpected status labels {sorted(set(result['labels']))}")
    return out


# Broken copies of the page: each must be caught by at least one scenario.
BROKEN = {
    "staleness ignored": ("function ageStatus(ts, amberH, redH) {", "function ageStatus(ts, amberH, redH) { return 'ok';"),
    "failures not propagated": ("const worst = (...xs) => xs.flat().filter(Boolean).reduce((a, b) => (RANK[b] > RANK[a] ? b : a), \"ok\");",
                                "const worst = (...xs) => \"ok\";"),
}


class OpsDashboardRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
        cls._pw = sync_playwright().start()
        exe = chromium_path(cls._pw)
        if not exe:
            cls._pw.stop()
            raise unittest.SkipTest("Chromium is not available")
        cls.browser = cls._pw.chromium.launch(executable_path=exe)
        cls.html = PAGE.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._pw.stop()

    def test_scenarios_render_expected_states(self):
        for name, build in SCENARIOS.items():
            with self.subTest(scenario=name):
                result = render(self.browser, build(), self.html)
                self.assertEqual([], problems(result, EXPECT[name]), result)

    def test_very_stale_and_missing_feeds_turn_red(self):
        site = green_site()
        # 13 h: past the producer's own stale_after_minutes (720), so red even
        # though the page's default limit for this feed is 25 h.
        site["modules/monitoring-summary.json"]["generated_at"] = ago(13)
        del site["modules/comparison-chain-status.json"]
        site["modules/monitoring-summary.json"]["security"] = {"read_error": "permission denied"}
        result = render(self.browser, site, self.html)
        self.assertEqual("unk", result["cards"]["security"])
        self.assertEqual("bad", result["cards"]["monitor"])
        self.assertEqual("bad", result["cards"]["chain"])
        self.assertEqual("bad", result["banner"])

    def test_broken_pages_are_caught(self):
        for label, (old, new) in BROKEN.items():
            with self.subTest(broken=label):
                self.assertIn(old, self.html, f"mutation anchor for {label!r} not found; update BROKEN")
                broken = self.html.replace(old, new, 1)
                caught = [name for name, build in SCENARIOS.items()
                          if problems(render(self.browser, build(), broken), EXPECT[name])]
                self.assertTrue(caught, f"broken page ({label}) passed every scenario")


class OpsStatusProducerTests(unittest.TestCase):
    def test_deploy_verdict(self):
        from build_ops_status import deploy_verdict
        self.assertEqual("current", deploy_verdict(TAG, SHA, None)[0])
        self.assertEqual("pending", deploy_verdict(TAG, "f" * 40, SHA)[0])
        self.assertEqual("unexpected", deploy_verdict(TAG, "f" * 40, "e" * 40)[0])
        self.assertEqual("unknown", deploy_verdict(None, SHA, SHA)[0])

    def test_alert_key_parsed_and_pull_requests_dropped(self):
        from build_ops_status import parse_alerts
        out = parse_alerts([{"number": 1, "title": "[ops-alert] x", "body": "hi\n<!-- ops-alert-key: source-stuck-cbs -->"},
                            {"number": 2, "title": "pr", "pull_request": {}, "body": ""}])
        self.assertEqual([("source-stuck-cbs", 1)], [(a["key"], a["number"]) for a in out])

    def test_identity_queue_counts_review_unmatched_provisional(self):
        from build_ops_status import summarize_identity
        out = summarize_identity([{"source": "*", "review": 2, "unmatched": 1, "provisional": 0, "verified": 9}])
        self.assertEqual(3, out["queue_total"])

    def test_failed_block_is_reported_not_raised(self):
        from build_ops_status import block
        def boom():
            raise RuntimeError("no token")
        out = block(boom)
        self.assertEqual("error", out["status"])
        self.assertIn("no token", out["error"])
        self.assertIn("as_of", out)


if __name__ == "__main__":
    unittest.main()
