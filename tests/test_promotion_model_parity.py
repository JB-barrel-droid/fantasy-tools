"""The engine's JEG-969 promotion model matches the Python reference
(value_reference._apply_promotion_model) part for part.

JEG-1152: the engine had no branch for a bench player with no lineup share
but value above waivers, so it left him at 0 where the reference gives a
promotion bonus. value-check-compare caught it only once the week-8 lineup
window put such players in the FantasyPros adj tab (engine 0 vs reference
up to 0.12). This runs both on one position with such a player.

Skips when node is missing, unless RENDER_TESTS_REQUIRED=1 (CI).
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from pipelines import value_reference as ref
from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
VALUE_MODEL = ROOT / "app" / "trade-value-chart" / "assets" / "value-model.js"

AVAIL, WAIVER, STARTERS, TEAMS, WEEKS = 0.82, 1.0, 2, 1, 10.0
XS = [20.0, 15.0, 9.0, 5.0, 3.0, 1.0]
# (start_worthy_part, fill_in_part, lineup_share); rows 5 and 6 have no
# lineup share, row 5 is above waivers (the JEG-1152 case).
PARTS = [(10.0, 4.0, 0.8), (6.0, 3.0, 0.6), (0.0, 2.0, 0.3), (0.0, 0.5, 0.05), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)]

HARNESS = r"""
const src = require("fs").readFileSync(process.argv[1], "utf8");
const start = src.indexOf("var PROMOTION_RATES");
const end = src.indexOf("function vpNormalizeBasis");
const block = src.slice(start, end);
const fn = new Function(block + "; return esApplyPromotionModel;")();
const p = JSON.parse(process.argv[2]);
const out = fn(p.es, p.work, p.starters, p.teams, p.pos, p.weeks, p.waiver);
process.stdout.write(JSON.stringify(out.parts));
"""


def _engine(pos: str) -> list[dict]:
    node = shutil.which("node")
    if node is None:
        if _render_env.required():
            raise AssertionError("node is required (RENDER_TESTS_REQUIRED=1) but not installed")
        raise unittest.SkipTest("node not installed")
    es = {"avail": AVAIL, "unavailable": 1 - AVAIL, "nPerTeam": 2, "bands": [],
          "parts": [{"sigma": 0, "startWorthy": 0, "lineupShare": ls, "starterPart": sp, "benchPart": fp,
                     "optionStarterPart": None, "optionBenchPart": None} for sp, fp, ls in PARTS]}
    payload = {"es": es, "work": [{"native": x} for x in XS], "starters": STARTERS, "teams": TEAMS,
               "pos": pos, "weeks": WEEKS, "waiver": WAIVER}
    out = subprocess.run([node, "-e", HARNESS, str(VALUE_MODEL), json.dumps(payload)],
                         capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def _reference(pos: str) -> list[dict]:
    parts = {"avail": AVAIL, "w": WAIVER,
             "parts": [{"start_worthy": 0, "lineup_share": ls, "start_worthy_part": sp, "fill_in_part": fp,
                        "option_starter_part": None, "option_fill_in_part": None} for sp, fp, ls in PARTS]}
    got = ref._apply_promotion_model(parts, XS, STARTERS, TEAMS, pos, ref.load_promotion_config(),
                                     WEEKS, 17.0)
    return got["parts"]


class PromotionModelParity(unittest.TestCase):
    def test_engine_matches_reference_every_part(self):
        for pos in ("QB", "RB", "WR", "TE"):
            eng, py = _engine(pos), _reference(pos)
            self.assertEqual(len(eng), len(py))
            for rank, (e, r) in enumerate(zip(eng, py), start=1):
                with self.subTest(pos=pos, rank=rank):
                    self.assertAlmostEqual(e["starterPart"], r["start_worthy_part"], places=9)
                    self.assertAlmostEqual(e["benchPart"], r["fill_in_part"], places=9)
                    self.assertAlmostEqual(e["lineupShare"], r["lineup_share"], places=9)

    def test_bench_player_with_no_share_above_waivers_gets_a_bonus(self):
        self.assertGreater(_engine("WR")[4]["starterPart"], 0)

    def test_engine_rates_match_config(self):
        cfg = ref.load_promotion_config()
        src = VALUE_MODEL.read_text(encoding="utf-8")
        for pos, rates in cfg["promotion_rate_per_remaining_week"].items():
            if pos.startswith("_"):
                continue
            line = re.search(rf"^\s*{pos}: (\{{.*?\}})", src, re.M).group(1)
            self.assertEqual({k: float(v) for k, v in json.loads(line).items()}, rates)


if __name__ == "__main__":
    unittest.main()
