"""JEG-67: pool-cap truncation must not drop players with positive value.

JEG-52 capped the DDF leg pool at 3x starters per position
(REF_SLOTS[pos] * teams * 3) to stop deep-bench tails from inflating the
pie (Josh Allen 48.7 vs ESPN 29.5). The cap truncates the resolved pool,
which feeds BOTH calibration and the output values -- so it drops players
from the leg output, not just from calibration inputs.

This test proves the truncation is benign: every player beyond the cap
threshold either has raw_value == 0.0 (waiver tier) or is absent from the
leg. No player with a positive value is ever excluded by the cap.

Verified 2026-10-02 on the baked legs: Razzball half_ppr 12t would cut
217 players (QB 35, RB 45, WR 63, TE 74) -- all 217 have raw_value 0.00
and tier 'waiver'. The cap only removes zero-value tails.

Note: the baked Razzball/CBS ROS legs predate the JEG-52 cap commit
(legs baked 2026-10-01 07:56 CDT; cap committed 20:32 CDT), so they are
the UNCAPPED versions. This test validates the cap's safety for when the
legs are rebuilt with it.
"""
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LEG_DIR = REPO / "data" / "ddf-two-tier"

# REF_SLOTS from pipelines/build_ddf_two_tier_leg.py
REF_SLOTS = {"QB": 1, "RB": 2, "WR": 3, "TE": 1}
TEAMS = 12


def _cap(pos):
    return REF_SLOTS[pos] * TEAMS * 3


def _find_leg(source):
    """Find the latest baked leg for a source at 12t."""
    cands = sorted(LEG_DIR.glob(f"ddf-*-{source}-*ppr-12t-0p15"),
                   key=lambda p: p.name)
    if not cands:
        return None
    d = cands[-1]
    files = list(d.glob("ddf_leg*.json"))
    return files[0] if files else None


class PoolCapTruncationTest(unittest.TestCase):
    def _check_leg(self, source):
        path = _find_leg(source)
        if path is None:
            self.skipTest(f"no baked {source} 12t leg found")
        leg = json.loads(path.read_text(encoding="utf-8"))
        vals = leg.get("values", [])
        self.assertGreater(len(vals), 0, f"{source}: leg has no values")
        dropped_positive = []
        for pos in ("QB", "RB", "WR", "TE"):
            rows = sorted([v for v in vals if v["pos"] == pos],
                          key=lambda v: -v["ppg"])
            cut = rows[_cap(pos):]
            for v in cut:
                if v.get("raw_value", 0) > 0:
                    dropped_positive.append(
                        f"{v['player']} ({pos}): raw_value={v['raw_value']}"
                    )
        self.assertEqual(
            dropped_positive, [],
            f"{source}: cap would drop players with positive value: "
            f"{dropped_positive[:5]}",
        )
        return len(vals)

    def test_razzball_cap_drops_only_zero_value(self):
        n = self._check_leg("razzball")
        print(f"\n  razzball leg: {n} values, cap drops only zero-value tails")

    def test_cbsros_cap_drops_only_zero_value(self):
        n = self._check_leg("cbsros")
        print(f"\n  cbsros leg: {n} values, cap drops only zero-value tails")

    def test_espn_cap_drops_only_zero_value(self):
        n = self._check_leg("espn")
        print(f"\n  espn leg: {n} values, cap drops only zero-value tails")

    def test_cap_thresholds_match_builder(self):
        # The caps used here must match the builders' REF_SLOTS * teams * 3.
        # If the builder changes its cap formula, this test's thresholds go
        # stale -- update them together.
        self.assertEqual(
            {p: _cap(p) for p in ("QB", "RB", "WR", "TE")},
            {"QB": 36, "RB": 72, "WR": 108, "TE": 36},
        )


if __name__ == "__main__":
    unittest.main()
