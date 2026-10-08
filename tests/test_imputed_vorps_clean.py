#!/usr/bin/env python3
"""Tests for JEG-182 build_imputed_vorps (clean implementation)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "pipelines"))

from build_imputed_vorps import infer_roster  # noqa: E402


class InferRosterTest(unittest.TestCase):
    def test_infer_roster_sizes(self):
        """Roster inference produces correct counts."""
        # 12 teams: 12 QB, 24 RB, 36 WR, 12 TE dedicated = 84 starters
        # + 12 flex + 72 bench = 168 rostered
        values = {}
        for i in range(20):
            values[str(1000+i)] = ("QB", 100 - i)
        for i in range(60):
            values[str(2000+i)] = ("RB", 100 - i * 0.5)
        for i in range(80):
            values[str(3000+i)] = ("WR", 100 - i * 0.5)
        for i in range(30):
            values[str(4000+i)] = ("TE", 100 - i)

        roles = infer_roster(values)
        starters = sum(1 for r in roles.values() if r == "starter")
        bench = sum(1 for r in roles.values() if r == "bench")
        # 84 dedicated + 12 flex = 96 starters, 72 bench
        self.assertEqual(starters, 96)
        self.assertEqual(bench, 72)


    def test_flex_maps_to_starter(self):
        """Flex-eligible players selected for flex get 'starter' role."""
        values = {}
        for i in range(12):
            values[str(1000+i)] = ("QB", 100 - i)
        for i in range(24):
            values[str(2000+i)] = ("RB", 100 - i)
        # Add extra RBs/WRs that should become flex
        for i in range(24, 40):
            values[str(2000+i)] = ("RB", 50 - (i - 24))
        for i in range(36):
            values[str(3000+i)] = ("WR", 100 - i)
        for i in range(12):
            values[str(4000+i)] = ("TE", 100 - i)
        # Bench fillers
        for i in range(40, 100):
            values[str(2000+i)] = ("RB", 10 - (i - 40) * 0.1)

        roles = infer_roster(values)
        # The top flex-eligible non-starters should be starters (flex)
        # We just verify the counts are right
        starters = sum(1 for r in roles.values() if r == "starter")
        self.assertEqual(starters, 96)


if __name__ == "__main__":
    unittest.main()
