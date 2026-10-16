"""JEG-571: Start / Hold / Stash / Drop tag rules, pinned on fixture players.

The rules (app/trade-value-chart/assets/player-tags.js) read only the engine's
own row fields: ddfTier (from the roster convention), startWorthy (P(level
above the starter line)). The module is run in node. The guard test mutates
the module with each named bug and requires the fixture table to fail.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "app" / "trade-value-chart" / "assets" / "player-tags.js"
NODE = shutil.which("node")

# (name, row, expected). Mason / Mitchell use the ticket's Week 5 ESPN 12-team
# full PPR probabilities (50%, 12.5%); the others are shaped fixtures.
FIXTURES = [
    ("Starter", {"ddfTier": "starter", "startWorthy": 0.9}, "Start"),
    ("Starter with no probability", {"ddfTier": "starter", "startWorthy": None}, "Start"),
    ("Mason (waiver tier, 50% to start)", {"ddfTier": "waiver", "startWorthy": 0.5}, "Stash"),
    ("Bench player, 40% to start", {"ddfTier": "bench", "startWorthy": 0.4}, "Stash"),
    ("Keaton Mitchell (waiver tier, 12.5%)", {"ddfTier": "waiver", "startWorthy": 0.125}, "Drop"),
    ("Bench depth, 5% to start", {"ddfTier": "bench", "startWorthy": 0.05}, "Hold"),
    ("Bench, no probability", {"ddfTier": "bench", "startWorthy": None}, "Hold"),
    ("Exactly at the stash line", {"ddfTier": "bench", "startWorthy": 0.25}, "Stash"),
    ("No tier (no source prices him)", {"ddfTier": None, "startWorthy": 0.9}, None),
]


def run_tags(module: Path, rows, options=None):
    script = (
        "const T = require(process.argv[1]).PlayerTags;"
        "const rows = JSON.parse(process.argv[2]);"
        "const opts = JSON.parse(process.argv[3]);"
        "console.log(JSON.stringify(rows.map(r => T.playerTag(r, opts))));"
    )
    out = subprocess.run([NODE, "-e", script, str(module), json.dumps(rows), json.dumps(options)],
                         capture_output=True, text=True, check=True, timeout=30)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class PlayerTagsTest(unittest.TestCase):
    def test_fixture_players(self):
        got = run_tags(MODULE, [row for _, row, _ in FIXTURES])
        for (name, _, want), have in zip(FIXTURES, got):
            self.assertEqual(have, want, name)

    def test_threshold_is_a_setting(self):
        row = {"ddfTier": "waiver", "startWorthy": 0.125}
        self.assertEqual(run_tags(MODULE, [row], {"stashStartProbability": 0.1}), ["Stash"])

    def test_missing_row_has_no_tag(self):
        self.assertEqual(run_tags(MODULE, [None]), [None])

    def test_every_tag_is_reachable_and_named_plainly(self):
        tags = set(run_tags(MODULE, [row for _, row, _ in FIXTURES])) - {None}
        self.assertEqual(tags, {"Start", "Hold", "Stash", "Drop"})

    def test_no_hard_coded_starter_count(self):
        # The starter count must come from ddfTier (the roster convention).
        text = MODULE.read_text(encoding="utf-8")
        for banned in ("starters", "rank <", "rank <=", "slots", "Vegas", "VORP"):
            self.assertNotIn(banned, text.split("*/", 1)[1], banned)

    def test_guard_catches_broken_rules(self):
        source = MODULE.read_text(encoding="utf-8")
        faults = {
            "starters not tagged Start": ('if (tier === "starter") return "Start";', ""),
            "stash test dropped": ("if (finite(row.startWorthy) && row.startWorthy >= threshold) return \"Stash\";", ""),
            "stash line is strict": ("row.startWorthy >= threshold", "row.startWorthy > threshold"),
            "waiver tier held, not dropped": ('return tier === "bench" ? "Hold" : "Drop";', 'return "Hold";'),
            "tierless row tagged": ('if (tier !== "bench" && tier !== "waiver") return null;', ""),
        }
        rows = [row for _, row, _ in FIXTURES]
        want = [w for _, _, w in FIXTURES]
        for fault, (old, new) in faults.items():
            self.assertEqual(source.count(old), 1, f"stale mutation anchor: {fault}")
            with tempfile.TemporaryDirectory() as tmp:
                broken = Path(tmp) / "player-tags.js"
                broken.write_text(source.replace(old, new), encoding="utf-8")
                self.assertNotEqual(run_tags(broken, rows), want, f"not caught: {fault}")


if __name__ == "__main__":
    unittest.main()
