"""JEG-611: the chain's Razzball section holds what the bake holds (JEG-555).

The bake drops a Razzball per-game rate below 60% of the ESPN/CBS mean from
players.json (the chart). The DDF leg behind the chain's Razzball section (the
main table) read the snapshot directly and still priced those players on the
discounted rate, so table and chart disagreed for Lamar Jackson, Mahomes and
the other held players.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "tests"))

import build_razzball_ddf_leg as razzball_leg  # noqa: E402
from test_suffix_identity import write_snapshot  # noqa: E402

REFS = {1: {"espn_ppg": dict.fromkeys(("standard", "half_ppr", "ppr"), 21.4),
            "cbsros_ppg": dict.fromkeys(("standard", "half_ppr", "ppr"), 23.0)},
        2: {"espn_ppg": dict.fromkeys(("standard", "half_ppr", "ppr"), 20.0),
            "cbsros_ppg": dict.fromkeys(("standard", "half_ppr", "ppr"), 20.0)}}


def load(tmp: Path, with_players=True):
    fx = tmp / "comparison-sources-data.json"
    fx.write_text(json.dumps({"player_keys": {"lamar jackson": 1, "josh allen": 2}}),
                  encoding="utf-8")
    players = [{"player_key": k, "pos": "QB", **ref} for k, ref in REFS.items()]
    if with_players:
        (tmp / "players.json").write_text(json.dumps({"players": players}), encoding="utf-8")
    snap = write_snapshot(tmp, [("lamar jackson", "QB", 7.1), ("josh allen", "QB", 21.0)])
    return razzball_leg.load_razzball_lists(snap, "ppr", fx)


class ChainRazzballHold(unittest.TestCase):
    def test_discounted_rate_is_held_from_the_leg(self):
        with tempfile.TemporaryDirectory() as d:
            resolved, review, _, _ = load(Path(d))
        self.assertEqual(["josh allen"], [r["player_norm"] for r in resolved["QB"]])
        held = [r for r in review if r["reason"] == "rz_held"]
        self.assertEqual([1], [r["player_key"] for r in held])
        self.assertIn("missed-games", held[0]["detail"])

    def test_without_references_nothing_is_held(self):
        with tempfile.TemporaryDirectory() as d:
            resolved, review, _, _ = load(Path(d), with_players=False)
        self.assertEqual(2, len(resolved["QB"]))

    def test_hold_reason_uses_the_bakes_rule(self):
        row = {"rz_std_ppg": 7.1, "rz_half_ppr_ppg": 7.1, "rz_ppr_ppg": 7.1}
        self.assertIsNotNone(razzball_leg.hold_reason(row, REFS[1]))
        self.assertIsNone(razzball_leg.hold_reason({**row, "rz_ppr_ppg": 21.0,
                                                    "rz_std_ppg": 21.0,
                                                    "rz_half_ppr_ppg": 21.0}, REFS[1]))


if __name__ == "__main__":
    unittest.main()
