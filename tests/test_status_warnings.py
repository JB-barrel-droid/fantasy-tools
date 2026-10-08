"""GAP-033 / GAP-044: freshness and lineage warnings show on the status page.

modules/status.html (the ops dashboard since 2026-10-08) reads
modules/surfaces.json for its "Published files" card. A surface may name a list
of warnings inside its file (`warn_path`, dotted); a non-empty list turns the
surface amber ("Attention", data-status="warn") and names the first few
entries. Two surfaces use it:

- reference-freshness: `summary.expired_keys`, every input past its window
  (pipelines/check_reference_freshness.py), so a stale input is a visible
  warning, not a number nobody reads (GAP-033).
- input-lineage: `mismatches`, every derived section whose lineage disagrees
  with its current input (pipelines/check_input_lineage.py, run by the chain;
  GAP-044).

Warnings never block a deploy (Jeremy, 2026-10-08): nothing here is in a gate.

The rendered test serves a synthetic site and needs Playwright with a Chromium
(CHROMIUM_PATH); it skips, saying why, without one.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "tests"))

from check_reference_freshness import build_report  # noqa: E402

SPEC = json.loads((ROOT / "modules" / "surfaces.json").read_text())
STATUS_HTML = (ROOT / "modules" / "status.html").read_text()


def _chromium():
    for candidate in (os.environ.get("CHROMIUM_PATH"),
                      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                      shutil.which("chromium")):
        if candidate and Path(candidate).exists():
            return candidate
    return None


class SpecTests(unittest.TestCase):
    def test_freshness_and_lineage_surfaces_carry_warnings(self):
        by_id = {s["id"]: s for s in SPEC["surfaces"]}
        self.assertEqual(by_id["reference-freshness"].get("warn_path"), "summary.expired_keys")
        self.assertEqual(by_id["input-lineage"].get("warn_path"), "mismatches")

    def test_reference_freshness_lists_expired_keys(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        # players.pm_snapshot was the stale example until the producers lane
        # retired the prediction-markets item (9afaede); espn_snapshot keeps the
        # same intent: an input past its window is listed.
        (tmp / "players.json").write_text(json.dumps({"meta": {"as_of": "2026-10-08",
                                                               "espn_snapshot": "2026-09-22"}}))
        (tmp / "comparison-sources-data.json").write_text(json.dumps({"built_at": "2026-10-08T01:00:00Z"}))
        report = build_report(tmp, tmp / "out.json", date(2026, 10, 8))
        keys = report["summary"]["expired_keys"]
        self.assertIn("players.espn_snapshot", keys)
        self.assertNotIn("players.as_of", keys)
        self.assertNotIn("comparison.built_at", keys)
        self.assertEqual(len(keys), report["summary"]["expired_count"])


def render_status(status_html: str, surfaces: list, files: dict) -> dict:
    """Serve a synthetic site (modules/status.html + surfaces + files) and
    return {surface_id: (status, why)} as the page's Published files card
    renders it (status: ok / warn / bad / unk)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    from test_launch_front_door import _pages_server
    with tempfile.TemporaryDirectory() as tmp:
        site = Path(tmp)
        (site / "modules").mkdir()
        (site / "modules" / "status.html").write_text(status_html)
        (site / "modules" / "surfaces.json").write_text(json.dumps({"surfaces": surfaces}))
        (site / "404.html").write_text("not found")
        for rel, doc in files.items():
            (site / rel).parent.mkdir(parents=True, exist_ok=True)
            (site / rel).write_text(json.dumps(doc))
        with _pages_server(site) as base, sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=_chromium())
            page = browser.new_page()
            page.goto(base + "modules/status.html")
            page.wait_for_selector("body[data-ready='1']", timeout=20000)
            rows = page.eval_on_selector_all(
                "tr[data-surface]",
                "rs => rs.map(r => [r.dataset.surface, r.dataset.status, r.lastElementChild.innerText])")
            browser.close()
    return {sid: (state, why) for sid, state, why in rows}


class RenderedStatusWarningsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import playwright.sync_api  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("needs Playwright for Python")
        if not _chromium():
            raise unittest.SkipTest("needs a Chromium (CHROMIUM_PATH)")

    SURFACES = [
        {"id": "fresh", "page": "t", "label": "fresh", "url": "fresh.json", "backend": "t",
         "meaning": "t", "required": True, "time_field": "generated_at", "max_age_hours": 24,
         "warn_path": "summary.expired_keys"},
        {"id": "lagging", "page": "t", "label": "lagging", "url": "lagging.json", "backend": "t",
         "meaning": "t", "required": True, "time_field": "generated_at", "max_age_hours": 24,
         "warn_path": "mismatches", "warn_label": "derived sections lag their input"},
    ]

    def files(self):
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        return {
            "fresh.json": {"generated_at": now, "summary": {"expired_keys": []}},
            "lagging.json": {"generated_at": now, "mismatches": [
                {"section": "cbsros", "reason": "lineage_raw_vintage_mismatch"},
                {"section": "cbsros", "reason": "lineage_raw_built_at_mismatch"},
                {"section": "razzball", "reason": "lineage_raw_vintage_mismatch"}]},
        }

    def test_warnings_degrade_the_surface_and_name_it(self):
        got = render_status(STATUS_HTML, self.SURFACES, self.files())
        self.assertEqual(got["fresh"][0], "ok", got)
        state, why = got["lagging"]
        self.assertEqual(state, "warn", got)
        self.assertIn("2 derived sections lag their input: cbsros, razzball", why)

    def test_pre_fix_status_page_misses_the_warning(self):
        """Negative: the status page before GAP-033/044 ignored warn_path, so
        a lagging section showed as working."""
        start = STATUS_HTML.index("  const warnings = warningsAt(doc, s.warn_path);")
        end = STATUS_HTML.index("  const ts = s.time_field", start)
        old = STATUS_HTML[:start] + STATUS_HTML[end:]
        got = render_status(old, self.SURFACES, self.files())
        self.assertEqual(got["lagging"][0], "ok", got)


class LineageCardStaleNoteTest(unittest.TestCase):
    """GAP-LIVE-SCRAPE-STALE: the dashboard's lineage card says it is a stale
    manual audit once it is over 48h old (it has no scheduled producer)."""

    @classmethod
    def setUpClass(cls):
        RenderedStatusWarningsTest.setUpClass()

    def render(self, dashboard_html, lineage):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
        from test_launch_front_door import _pages_server
        if not (ROOT / "dist" / "modules" / "dashboard.html").exists():
            self.skipTest("needs make sync (dist/modules)")
        with tempfile.TemporaryDirectory() as tmp:
            # The real built site, so every card before the lineage card loads.
            site = Path(tmp) / "dist"
            shutil.copytree(ROOT / "dist", site,
                            ignore=shutil.ignore_patterns("consolidated-values.json"))
            (site / "modules" / "dashboard.html").write_text(dashboard_html)
            (site / "modules" / "source-value-lineage.json").write_text(json.dumps(lineage))
            with _pages_server(site) as base, sync_playwright() as pw:
                browser = pw.chromium.launch(executable_path=_chromium())
                page = browser.new_page()
                page.goto(base + "modules/dashboard.html")
                page.wait_for_function("document.getElementById('lineageSummary').innerHTML.length > 0",
                                       timeout=20000)
                note = page.evaluate("document.querySelector('#lineageSummary .lineage-stale')?.innerText || ''")
                browser.close()
        return note

    LINEAGE_OLD = {"generated_at": "2026-10-03T22:00:42+00:00", "live_scraped_at": "2026-10-03T01:07:35Z",
                   "sources": {}}

    def test_old_lineage_shows_stale_note(self):
        html = (ROOT / "modules" / "dashboard.html").read_text()
        self.assertIn("Stale audit", self.render(html, self.LINEAGE_OLD))

    def test_fresh_lineage_shows_no_note(self):
        from datetime import datetime, timezone
        fresh = dict(self.LINEAGE_OLD, generated_at=datetime.now(timezone.utc).isoformat())
        html = (ROOT / "modules" / "dashboard.html").read_text()
        self.assertEqual("", self.render(html, fresh))

    def test_pre_fix_dashboard_shows_no_note(self):
        """Negative: before 2026-10-08 the card showed a 5-day-old Week 4
        audit with no warning."""
        import subprocess
        old = subprocess.run(["git", "-C", str(ROOT), "show", "dac0ff2:modules/dashboard.html"],
                             capture_output=True, text=True)
        if old.returncode != 0:
            self.skipTest("pre-fix dashboard not in this clone's history")
        self.assertEqual("", self.render(old.stdout, self.LINEAGE_OLD))


if __name__ == "__main__":
    unittest.main()
