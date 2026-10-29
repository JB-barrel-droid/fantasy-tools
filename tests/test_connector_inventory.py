"""JEG-1030: one inventory of the connector's tools and the site's routes (node, no network).

Every tool the MCP endpoint lists must be in TOOLS below, with the site route its link opens (observed
by calling it, tests/node/connector_inventory_dump.mjs) and the checks that guard it. Every top-level
route the site's tabs open must be reached by a tool's link or be an explicit exception in
ROUTE_EXCEPTIONS, naming the ticket that adds it or why none will. A new tool (JEG-1029) fails here
until it is listed with its own parity coverage, and its exception is removed when it lands.

Offline only: this is the engine and tool code, not the deployed function or a live chat client.

Discrimination: test_inventory_check_catches_drift runs the same check on altered inventories.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "app" / "v2" / "shell.html"

# Value parity for every pricing tool is get-values against the page (tests/test_endpoint_parity.py);
# the tools only read get-values, so the per-tool checks are about what they send and link.
VALUES = "tests/test_endpoint_parity.py"
ROUND_TRIP = "tests/node/connector_roundtrip_check.mjs"
REMOTE = "tests/node/mcp_remote_check.mjs"
FIT = "tests/node/connector_fit_check.mjs"

TOOLS = {
    "get_values": {"route": "#trade-targets", "checks": [VALUES, ROUND_TRIP, REMOTE]},
    "get_player_value": {"route": "#trade-targets", "checks": [VALUES, ROUND_TRIP, REMOTE]},
    "trade_targets": {"route": "#trade-targets", "checks": [VALUES, ROUND_TRIP, REMOTE]},
    "compare_trade": {"route": "#compare-trade", "checks": [VALUES, ROUND_TRIP, REMOTE]},
    # read_state links to the view its work belongs to (give/get here, so Compare a trade).
    "read_state": {"route": "#compare-trade", "checks": [ROUND_TRIP, REMOTE]},
    "make_state": {"route": "#find-trade", "checks": [ROUND_TRIP, REMOTE]},
    "find_trades": {"route": "#find-trade", "checks": [VALUES, ROUND_TRIP, REMOTE, FIT]},
    "find_trades_league": {"route": "#find-trade", "checks": [VALUES, ROUND_TRIP, REMOTE]},
    # explain prices nothing and links to the front page without a league.
    "explain": {"route": "/", "checks": [ROUND_TRIP, REMOTE]},
}

# Site routes no tool links to. "JEG-n": the ticket that adds the analysis. "by design: ...": none
# will. "untracked: ...": a gap found by JEG-1030 that still needs a ticket (reported on JEG-1030).
ROUTE_EXCEPTIONS = {
    "#risers-fallers": "JEG-1029",  # risers_fallers (state.ts already has the route)
    "#values-auditing": "JEG-1029",  # audit_values with the health and source views
    "#value-overrides": "JEG-1224",  # value basis and overrides are not part of the DDF state yet
    "#writing": "by design: prose pages, nothing to compute",
    "#player-values": "untracked: get_values links to Trade targets, not the value chart (JEG-1030 F2)",
    "#find-league": "untracked: find_trades_league links to the one-opponent finder (JEG-1030 F2)",
    "#waivers": "untracked: no waiver analysis in the connector or in JEG-1029's proposal (JEG-1030 F3)",
}
EXCEPTION_FORM = re.compile(r"^(JEG-\d+|by design: .+|untracked: .+)$")


def site_routes(html: str) -> set[str]:
    """Top-level routes the page's tabs open (#values-auditing/health-check -> #values-auditing)."""
    return {"#" + m.split("/")[0] for m in re.findall(r'class="v2-tab" href="v2/#([^"]+)"', html)}


def inventory_errors(dump: dict, tools: dict, exceptions: dict, routes: set[str]) -> list[str]:
    errors = []
    for name in dump["tools"]:
        if name not in tools:
            errors.append(f"tool {name} is not in the inventory: list its route and parity checks")
    for name, entry in tools.items():
        if name not in dump["tools"]:
            errors.append(f"inventory lists {name}, which the endpoint does not")
            continue
        if dump["routes"].get(name) != entry["route"]:
            errors.append(f"{name} links to {dump['routes'].get(name)}, inventory says {entry['route']}")
        for check in entry["checks"]:
            path = ROOT / check
            if not path.exists():
                errors.append(f"{name}: check {check} does not exist")
            elif check != VALUES and name not in path.read_text(encoding="utf-8"):
                errors.append(f"{name}: check {check} never names the tool")
    linked = {entry["route"] for entry in tools.values()}
    for route in sorted(routes):
        if route not in linked and route not in exceptions:
            errors.append(f"site route {route} has no tool and no exception")
    for route, why in exceptions.items():
        if route not in routes:
            errors.append(f"exception for {route}, which the site no longer has")
        elif route in linked:
            errors.append(f"exception for {route}, which a tool now links to: remove it")
        if not EXCEPTION_FORM.match(why):
            errors.append(f"exception for {route} needs a ticket or a reason: {why!r}")
    for view, route in dump["connector_routes"].items():
        if route not in routes:
            errors.append(f"state.ts route {view} -> {route} is not a site route")
    return errors


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class ConnectorInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "tests/node/connector_inventory_dump.mjs")],
            capture_output=True, text=True, timeout=60,
        )
        if out.returncode != 0:
            raise AssertionError(out.stdout + out.stderr)
        cls.dump = json.loads(out.stdout)
        cls.routes = site_routes(SHELL.read_text(encoding="utf-8"))

    def test_inventory(self):
        self.assertGreater(len(self.dump["tools"]), 5)
        self.assertIn("#compare-trade", self.routes)
        self.assertEqual(inventory_errors(self.dump, TOOLS, ROUTE_EXCEPTIONS, self.routes), [])

    def test_inventory_check_catches_drift(self):
        new_tool = {**self.dump, "tools": self.dump["tools"] + ["risers_fallers"]}
        moved = {**self.dump, "routes": {**self.dump["routes"], "compare_trade": "#find-trade"}}
        cases = {
            "unlisted new tool": (new_tool, TOOLS, ROUTE_EXCEPTIONS, self.routes),
            "tool links elsewhere": (moved, TOOLS, ROUTE_EXCEPTIONS, self.routes),
            "site route without exception": (self.dump, TOOLS, {k: v for k, v in ROUTE_EXCEPTIONS.items() if k != "#waivers"}, self.routes),
            "exception without a ticket": (self.dump, TOOLS, {**ROUTE_EXCEPTIONS, "#waivers": "later"}, self.routes),
            "stale exception": (self.dump, TOOLS, {**ROUTE_EXCEPTIONS, "#gone": "JEG-1"}, self.routes),
            "missing check file": (self.dump, {**TOOLS, "explain": {"route": "/", "checks": ["tests/node/nope.mjs"]}},
                                   ROUTE_EXCEPTIONS, self.routes),
        }
        for name, args in cases.items():
            with self.subTest(case=name):
                self.assertNotEqual(inventory_errors(*args), [], f"inventory check did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
