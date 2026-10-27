"""v2 Values auditing shell (JEG-847), rendered.

Loads the built page headless at 1440 and 390 px and checks:

  * "Values auditing" is the last tab, Research still directly follows How values work;
  * #values-auditing shows only the audit page with the Health check sub-tab (JEG-1011, was Value pie); the sub-tab
    link is aria-current and #audit-pie-root is the visible mount;
  * #values-auditing/single-source shows the Single source mount (#audit-source-root);
  * an unknown sub-route (#values-auditing/nope) falls back to the Health check; the old
    #values-auditing/value-pie hash is rewritten to #values-auditing/health-check;
  * the route calls the hook a sub-tab registered with DDFAudit.register, with its mount;
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves a v2.js with the audit route removed,
the unknown-slug fallback removed, and the render hook call removed, and requires the checks to fail.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_research_render import POSTS, _built_dist  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"

READ = """() => {
  const shown = id => { const n = document.getElementById(id); return Boolean(n) && !n.hidden; };
  return {
    tabs: [...document.querySelectorAll('.v2-tab')].map(t => ({view: t.dataset.view, current: t.getAttribute('aria-current') === 'page'})),
    audit: shown('v2Audit'),
    others: ['v2Main', 'v2Targets', 'v2Risers', 'v2Compare', 'v2How', 'v2Manifesto', 'v2Research'].filter(shown),
    pie: shown('v2AuditPie'), source: shown('v2AuditSource'),
    subCurrent: [...document.querySelectorAll('#v2AuditTabs .v2-subtab')].filter(a => a.getAttribute('aria-current') === 'page').map(a => a.dataset.audit),
    hookCalls: window.__auditCalls || [],
    overflow: document.documentElement.scrollWidth - innerWidth,
    // JEG-872: the pie tab's source names must be v2's own (symbol + label), never the engine's.
    pieValue: Number(((document.querySelector('#audit-pie-root .audit-pie-meta') || {}).textContent || '').match(/Value pie: ([\\d.]+)/)?.[1]),
    pieLabels: [...document.querySelectorAll('#audit-pie-root table[aria-label="Starter, bench and total value by source"] tbody tr')].map(r => r.cells[0].textContent),
    siteLabels: Object.fromEntries(Object.entries((window.TradeValueV2.publishers && window.TradeValueV2.publishers()) || {}).map(([k, p]) => [k, `${p.symbol} ${p.label}`])),
    pieReconcile: [...document.querySelectorAll('#audit-pie-root table[aria-label="Reconciling each source to Player values"] tbody tr')].map(r => [...r.cells].map(c => c.textContent)),
  };
}"""

# v2.js's PUBLISHERS as the site shows them; the pie tab must say exactly these (JEG-872).
SITE_LABELS = {"espn": "● ESPN", "fantasycalc": "■ FantasyCalc", "fantasypros": "▲ FantasyPros", "usatoday": "◆ USA Today",
               "cbs": "▼ CBS Sports", "cbsros": "▽ CBS rest of season", "razzball": "✚ Razzball"}

SPY = """() => {
  window.__auditCalls = [];
  for (const slug of DDFAudit.slugs) DDFAudit.register(slug, (mount, ctx) => {
    window.__auditCalls.push([slug, mount.id, ctx.slug]);
    if (slug === 'health-check' && window.AuditPie) window.AuditPie.render(mount, ctx);   // keep the real Health check render
  });
}"""

ROUTES = (
    ("#values-auditing", "health-check"),
    ("#values-auditing/health-check", "health-check"),
    ("#values-auditing/value-pie", "health-check"),   # JEG-1011: the old Value pie hash lands on the Health check
    ("#values-auditing/single-source", "single-source"),
    ("#values-auditing/nope", "health-check"),
)
MOUNTS = {"health-check": "audit-pie-root", "single-source": "audit-source-root"}


def check(snap, hash_, slug, width) -> list[str]:
    tag = f"[{width}px {hash_}] "
    errors = []
    if not snap["audit"] or snap["others"]:
        errors.append(f"{tag}pages shown: audit={snap['audit']} others={snap['others']}")
    if [t["view"] for t in snap["tabs"] if t["current"]] != ["audit"]:
        errors.append(f"{tag}Values auditing is not the current tab")
    if (snap["pie"], snap["source"]) != (slug == "health-check", slug == "single-source"):
        errors.append(f"{tag}panels shown pie={snap['pie']} source={snap['source']}, want {slug}")
    if snap["subCurrent"] != [slug]:
        errors.append(f"{tag}sub-tab current {snap['subCurrent']}, want {slug}")
    if not snap["hookCalls"] or snap["hookCalls"][-1] != [slug, MOUNTS[slug], slug]:
        errors.append(f"{tag}render hook calls {snap['hookCalls']}, want last {[slug, MOUNTS[slug], slug]}")
    if width <= 390 and snap["overflow"] > 0:
        errors.append(f"{tag}horizontal overflow {snap['overflow']}px")
    if slug == "health-check":
        if snap["siteLabels"] != SITE_LABELS:
            errors.append(f"{tag}TradeValueV2.publishers() {snap['siteLabels']}, want {SITE_LABELS}")
        if not snap["pieLabels"] or any(label not in SITE_LABELS.values() for label in snap["pieLabels"]):
            errors.append(f"{tag}pie tab source names {snap['pieLabels']} are not the site's {sorted(SITE_LABELS.values())}")
        # JEG-871: every source's own + filled-in = Total adjusted = pie, and the Player values column is shown.
        for cells in snap["pieReconcile"]:
            own, filled, total, shown = (float(c) for c in cells[1:5])
            if abs(own + filled - total) > 0.11 or abs(total - snap["pieValue"]) > 0.05:
                errors.append(f"{tag}pie reconcile row {cells}: own + filled != total adjusted = pie")
        if not snap["pieReconcile"]:
            errors.append(f"{tag}no reconcile rows on the Health check")
    return errors


def run_checks(js_edit=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if js_edit:
        old, new = js_edit
        assert old in js, f"test setup: {old!r} not in v2.js"
        js = js.replace(old, new, 1)
    errors = []
    with _built_dist(POSTS) as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
                page.goto(base, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                order = [t["view"] for t in page.evaluate(READ)["tabs"]]
                # JEG-1106: the menu lists Value pie and Source build-up (both audit) in the Auditing group, after Players.
                if order[0] != "values" or order.count("audit") != 2 or order.index("audit") < order.index("targets"):
                    errors.append(f"[{width}px] menu order {order}: Value chart should be first and the two audit entries follow Players")
                page.evaluate(SPY)
                for hash_, slug in ROUTES:
                    page.evaluate("() => { location.hash = '#trade-targets'; }")
                    page.wait_for_timeout(150)
                    page.evaluate("() => { window.__auditCalls.length = 0; }")
                    page.evaluate("h => { location.hash = h; }", hash_)
                    page.wait_for_timeout(300)
                    errors += check(page.evaluate(READ), hash_, slug, width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class AuditRenderTest(unittest.TestCase):
    def test_audit_shell(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        broken = {
            "route removed": ('(base === "#values-auditing" || base.startsWith("#values-auditing/")) ? "audit"', 'false ? "audit"'),
            "unknown slug not caught": ("slugs.includes(asked) ? asked : slugs[0]", "asked"),
            "hook not called": ("window.DDFAudit.render(slug, panel,", "(() => 0)(slug, panel,"),
            # JEG-872: the pie tab reads v2's map; with it gone the rows show raw keys ("cbs"), which the check rejects.
            "source name map not shared": ("publishers: () => PUBLISHERS,", "publishers: () => ({}),"),
            # JEG-872: a label that drifts from the site's wording is caught.
            "source name drifted": ('cbsros: {label: "CBS rest of season"', 'cbsros: {label: "CBS ROS"'),
        }
        for name, edit in broken.items():
            with self.subTest(name):
                self.assertTrue(run_checks(edit), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
