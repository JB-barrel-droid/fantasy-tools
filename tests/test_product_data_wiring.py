"""Regression tests for the JEG-363 product-data.js integration wiring.

On 2026-10-04 the JEG-363 refactor made curve-widget.js and
comparison-dashboard.js read every fixture through
window.TradeValueProductData (assets/product-data.js), but two integration
gaps shipped:

1. index.html never loaded product-data.js, so the live chart fail-closed
   with "Curves unavailable: product-data.js missing; render refused."
2. product-data.js built fixture combo keys as f"{scoring}_{teams}"
   ("ppr_12"), while the fixture's combos are keyed "full_12" /
   "half_12" / "standard_12" -- so every getPlayerValues() call returned
   null and the as-published curves rendered empty (the guard harness even
   passed vacuously with zero espn checks).

Each test below also runs against a simulated broken state (tag removed /
mapping broken) and must FAIL there -- a guard that only asserts the
current behavior is worse than no guard.
"""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "app" / "trade-value-chart" / "index.html"
ASSETS = ROOT / "app" / "trade-value-chart" / "assets"
FIXTURE = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"

WIDGET = ASSETS / "curve-widget.js"
DASHBOARD = ASSETS / "comparison-dashboard.js"
PRODUCT_DATA = ASSETS / "product-data.js"

SCRIPT_SRC_RE = re.compile(r'<script\s+src="assets/([^"?]+)(?:\?[^"]*)?"[^>]*>')
TRADE_VALUE_GLOBAL_RE = re.compile(r"window\.(TradeValue[A-Za-z0-9_]+)")
TRADE_VALUE_DEF_RE = re.compile(r"window\.(TradeValue[A-Za-z0-9_]+)\s*=")

# Widget-internal scoring names, in the order the UI exposes them.
WIDGET_SCORINGS = ("ppr", "half_ppr", "standard")


def script_sources(html: str):
    return SCRIPT_SRC_RE.findall(html)


def provided_globals(sources):
    provided = {}
    for src in sources:
        path = ASSETS / src
        if not path.exists():
            continue
        for name in TRADE_VALUE_DEF_RE.findall(path.read_text()):
            provided.setdefault(name, src)
    return provided


def check_wiring(html: str):
    """Return a list of wiring problems (empty = wired correctly)."""
    problems = []
    sources = script_sources(html)
    if "product-data.js" not in sources:
        problems.append("index.html does not load assets/product-data.js")
        return problems
    order = {src: i for i, src in enumerate(sources)}
    for consumer in ("curve-widget.js", "comparison-dashboard.js"):
        if consumer in order and order["product-data.js"] > order[consumer]:
            problems.append(f"product-data.js loads after {consumer}")
    provided = provided_globals(sources)
    for consumer_path in (WIDGET, DASHBOARD):
        needed = set(TRADE_VALUE_GLOBAL_RE.findall(consumer_path.read_text()))
        # Globals a module defines for itself are not a wiring dependency.
        defined_here = set(TRADE_VALUE_DEF_RE.findall(consumer_path.read_text()))
        for name in sorted(needed - defined_here):
            if name not in provided:
                problems.append(
                    f"{consumer_path.name} reads window.{name} but no loaded "
                    f"script defines it"
                )
    return problems


def scoring_prefix_map():
    """Parse the SCORING_PREFIX map out of product-data.js."""
    text = PRODUCT_DATA.read_text()
    m = re.search(r"SCORING_PREFIX\s*=\s*\{([^}]+)\}", text)
    if not m:
        return {}
    pairs = re.findall(r"(\w+)\s*:\s*\"(\w+)\"", m.group(1))
    return dict(pairs)


def check_combo_keys_reachable(prefix_map):
    """Every widget scoring name must resolve to a real fixture combo key."""
    problems = []
    fixture = json.loads(FIXTURE.read_text())
    espn_combos = set(fixture["sources"]["espn"]["combos"])
    for scoring in WIDGET_SCORINGS:
        prefix = prefix_map.get(scoring)
        if not prefix:
            problems.append(f"no combo prefix mapped for widget scoring {scoring!r}")
            continue
        key = f"{prefix}_12"
        if key not in espn_combos:
            problems.append(
                f"widget scoring {scoring!r} maps to combo {key!r} "
                f"which is absent from the fixture"
            )
    return problems


class TestProductDataWiring(unittest.TestCase):
    def test_script_tag_present_and_ordered(self):
        problems = check_wiring(INDEX.read_text())
        self.assertEqual(problems, [], f"wiring problems: {problems}")

    def test_broken_state_missing_tag_is_caught(self):
        """Simulate the shipped JEG-363 gap: strip the product-data.js tag."""
        html = INDEX.read_text()
        broken = re.sub(
            r'<script\s+src="assets/product-data\.js[^"]*"[^>]*>\s*',
            "",
            html,
        )
        self.assertNotIn("product-data.js", script_sources(broken))
        problems = check_wiring(broken)
        self.assertTrue(
            problems,
            "wiring check passed on HTML without product-data.js -- "
            "the guard is not detecting the broken state",
        )
        self.assertTrue(
            any("product-data.js" in p for p in problems),
            f"expected a product-data.js complaint, got: {problems}",
        )

    def test_scoring_prefix_map_covers_widget_scorings(self):
        prefix_map = scoring_prefix_map()
        for scoring, expected in (
            ("ppr", "full"),
            ("half_ppr", "half"),
            ("standard", "standard"),
        ):
            self.assertEqual(
                prefix_map.get(scoring),
                expected,
                f"SCORING_PREFIX[{scoring!r}] should be {expected!r}",
            )

    def test_broken_state_wrong_prefix_is_caught(self):
        """Simulate the shipped combo-key bug: ppr -> 'ppr_12' (no such combo)."""
        problems = check_combo_keys_reachable({"ppr": "ppr", "half_ppr": "half", "standard": "standard"})
        self.assertTrue(
            problems,
            "combo-key check passed with the identity mapping -- "
            "the guard is not detecting the broken state",
        )
        self.assertTrue(any("ppr_12" in p for p in problems), problems)

    def test_combo_keys_reachable_in_fixture(self):
        problems = check_combo_keys_reachable(scoring_prefix_map())
        self.assertEqual(problems, [], f"combo key problems: {problems}")


if __name__ == "__main__":
    unittest.main()
