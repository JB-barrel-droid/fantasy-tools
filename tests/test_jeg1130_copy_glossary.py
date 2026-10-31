"""JEG-1130: the approved PMM glossary holds where this slice put it (Jeremy, 2026-10-26, final naming).

  * definitions and tooltips name no publisher: the three view tooltips on the default basis and every fit
    tooltip read as plain sentences, with publisher names left to auditing, source links and per-chart detail;
  * a group or table that lists the Market's charts one by one says "The Market, by chart";
  * the nav label is the page's H1 for every tool page (PMM doc 3.2: "The nav label *is* the page's H1").
    Writing and Values auditing are a section heading over sub-pages, and stay with the navigation work.

Discrimination: test_checks_fail_on_broken_builds puts a publisher back in a tooltip, renames an H1 and
restores the old caption, each in a copy of the sources.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

from tests.test_launch_copy_guard import PUBLISHERS
from tests.test_v2_finder_import import FINDER_JS, call

APP = FINDER_JS.parent
SHELL = APP / "shell.html"
WAIVERS = APP / "waivers.js"
# data-view of a nav link -> the id of that page's H1. One H1 per tool page.
TOOL_PAGES = {"values": None, "compare": "v2CompareTitle", "find": "v2FindPageTitle", "league": "v2FindLeagueTitle",
              "risers": "v2RisersTitle", "waivers": "v2WaiversTitle", "targets": "v2TargetsTitle",
              "overrides": "v2OverridesTitle"}
NAV = re.compile(r'<a class="v2-tab"[^>]*data-view="(\w+)"[^>]*><span class="v2-tab-full">([^<]+)</span></a>')


def h1_text(shell: str, h1_id: str | None) -> str | None:
    if h1_id is None:   # Player values: the first <main> has an H1 with no id
        m = re.search(r'<main[^>]*id="v2Main"[^>]*>.*?<h1>([^<]+)</h1>', shell, re.S)
    else:
        m = re.search(rf'<h1 id="{h1_id}">([^<]+)</h1>', shell)
    return m.group(1).strip() if m else None


def check(finder_js: Path, shell: str, waivers: str) -> list[str]:
    errors = []
    tips = {f"view {i}": call(finder_js, "viewTip", i, {"isDefault": True}) for i in ("ddf", "market", "projections")}
    tips.update({f"fit {v}": call(finder_js, "fitTip", v) for v in ("natural", "market", "force")})
    for name, text in tips.items():
        m = PUBLISHERS.search(text or "")
        if m:
            errors.append(f"{name} tooltip names a publisher ({m.group(0)}): {text}")
    if '"The Market, by chart"' not in waivers or "Market value by trade chart" in waivers:
        errors.append("the Waivers per-chart table caption is not \"The Market, by chart\"")
    nav = {view: label.strip() for view, label in NAV.findall(shell) if view in TOOL_PAGES}
    for view, h1_id in TOOL_PAGES.items():
        heading = h1_text(shell, h1_id)
        if view not in nav or heading is None:
            errors.append(f"{view}: nav label {nav.get(view)!r} or H1 {heading!r} not found")
        elif nav[view] != heading:
            errors.append(f"{view}: nav label {nav[view]!r} is not the page's H1 {heading!r}")
    return errors


MUTANTS = {
    "publisher back in the DDF tooltip": ("finder.js", "rooted in the trade charts, then adjusted",
                                          "rooted in FantasyCalc, USA Today, FantasyPros and CBS, then adjusted"),
    "publisher in a fit tooltip": ("finder.js", "Force fit: a roster would be broken", "Force fit (FantasyCalc): a roster would be broken"),
    "H1 drifts from its nav label": ("shell.html", '<h1 id="v2TargetsTitle">Trade targets</h1>', '<h1 id="v2TargetsTitle">Where the trade market is wrong</h1>'),
    "old per-chart caption": ("waivers.js", '"The Market, by chart"', '"Market value by trade chart"'),
}


class CopyGlossaryTests(unittest.TestCase):
    def sources(self):
        return {"finder.js": FINDER_JS.read_text(encoding="utf-8"), "shell.html": SHELL.read_text(encoding="utf-8"),
                "waivers.js": WAIVERS.read_text(encoding="utf-8")}

    def test_glossary(self):
        s = self.sources()
        self.assertEqual(check(FINDER_JS, s["shell.html"], s["waivers.js"]), [])

    def test_checks_fail_on_broken_builds(self):
        for name, (target, old, new) in MUTANTS.items():
            with self.subTest(name):
                s = self.sources()
                self.assertIn(old, s[target], f"mutant {name!r} no longer applies")
                s[target] = s[target].replace(old, new, 1)
                with tempfile.TemporaryDirectory() as tmp:
                    finder = Path(tmp) / "finder.js"
                    finder.write_text(s["finder.js"], encoding="utf-8")
                    self.assertTrue(check(finder, s["shell.html"], s["waivers.js"]), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
