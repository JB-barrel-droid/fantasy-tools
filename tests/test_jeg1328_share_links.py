"""JEG-1328: share links keep the league setup, the route's controls and both teams, by stable id.

The checks live in tests/node/share_link_context_check.cjs (pure Node). This runs them on app/v2 and, for each
mutation, on a broken copy that must fail, so a check that cannot see its own bug does not count.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tests" / "node" / "share_link_context_check.cjs"
V2 = ROOT / "app" / "v2"
FILES = ["workspace.js", "finder.js", "trade-context.js", "ddf-state.js", "league.js"]

# (file, anchor, replacement, a check that must fail)
MUTATIONS = {
    "the selected trade never travels": ("workspace.js",
        "if (pick && !pick.legacy && at(pick.opponentId) >= 0) out.push", "if (false) out.push", "league_link_round_trips_every_field"),
    "the pick keyed by name again": ("league.js",
        "const tradeParam = r => W.tradePick(r.opponentId, r.give, r.receive);",
        "const tradeParam = r => W.legacyTradePick(r.opponent, r.give, r.receive);", "league_page_uses_the_link_codec"),
    "the opponent filter keeps the sender's position": ("workspace.js",
        "if (idAt(params.get(\"opp\"))) filters.opponent = idAt(params.get(\"opp\"));",
        "if (params.get(\"opp\")) filters.opponent = params.get(\"opp\");", "league_link_round_trips_every_field"),
    "the package size is dropped": ("workspace.js",
        "if (LEAGUE_SIZES.includes(ui.maxSize) && ui.maxSize !== 2) out.push(`size=${ui.maxSize}`);", "", "league_link_round_trips_every_field"),
    "link parameters leak into the league settings": ("workspace.js",
        "SHARE_OWN_PARAMS.forEach(name => rest.delete(name));", "", "league_link_round_trips_every_field"),
    "an old name-keyed pick is dropped": ("workspace.js",
        "const trade = !pick ? null : pick.legacy ? legacyTradePick(pick.opponent, pick.give, pick.receive)",
        "const trade = !pick || pick.legacy ? null : pick.legacy ? null", "old_league_link_opens_the_same_view"),
    "viable-only never encoded": ("finder.js", "if (s.viableOnly) parts.push(\"viable=1\");", "", "finder_link_round_trips_every_field"),
    "saved teams accepted without their league": ("finder.js",
        "if (!teams.workspaceId || teams.mineId === teams.theirId) { teams.mineId = null; teams.theirId = null; }",
        "if (teams.mineId && teams.mineId === teams.theirId) { teams.mineId = null; teams.theirId = null; }", "finder_link_team_ids_are_checked"),
}


def run(directory: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(CHECK), str(directory)], capture_output=True, text=True, check=False)
    return json.loads(out.stdout)


class ShareLinkContextTest(unittest.TestCase):
    def test_share_links_round_trip(self):
        result = run(V2)
        self.assertEqual(result["failures"], [])
        self.assertGreaterEqual(len(result["ran"]), 11)

    def test_checks_fail_on_broken_builds(self):
        for name, (file, anchor, replacement, must_fail) in MUTATIONS.items():
            with self.subTest(mutation=name), tempfile.TemporaryDirectory() as tmp:
                for f in FILES:
                    shutil.copy(V2 / f, Path(tmp) / f)
                body = (V2 / file).read_text(encoding="utf-8")
                self.assertIn(anchor, body, f"mutation anchor for {name!r} is stale")
                (Path(tmp) / file).write_text(body.replace(anchor, replacement, 1), encoding="utf-8")
                failed = {f["name"] for f in run(Path(tmp))["failures"]}
                self.assertIn(must_fail, failed, f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
