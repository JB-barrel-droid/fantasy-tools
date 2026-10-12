"""JEG-558: market bench config is cited and reproducible from committed snapshots."""
import json
import unittest
from pathlib import Path

from pipelines import derive_market_bench as dmb

CONFIG = json.loads((Path(__file__).resolve().parent.parent / "config" / "market_bench.json").read_text())
TOL = 0.02


class MarketBenchTests(unittest.TestCase):
    def test_frozen_values_match_ticket(self):
        self.assertEqual(CONFIG["one_qb"]["backups_per_starter"],
                         {"QB": 0.88, "RB": 0.83, "WR": 1.03, "TE": 0.40, "K": 0.00, "DEF": 0.06})
        self.assertEqual(CONFIG["two_qb"]["backups_per_starter"],
                         {"QB": 0.28, "RB": 0.69, "WR": 0.85, "TE": 0.44, "K": 0.06, "DEF": 0.08})

    def test_derivation_reproduces_frozen_values(self):
        for fmt in dmb.FORMATS:
            derived = dmb.derive(fmt)
            for pos, frozen in CONFIG[fmt]["backups_per_starter"].items():
                self.assertAlmostEqual(derived[pos]["backups_per_starter"], frozen, delta=TOL, msg=f"{fmt} {pos}")

    def test_sources_cover_seasons(self):
        for fmt in dmb.FORMATS:
            self.assertEqual(len(CONFIG[fmt]["sources"]), len(CONFIG[fmt]["seasons"]))
            self.assertEqual(CONFIG[fmt]["seasons"], dmb.FORMATS[fmt]["years"])

    def test_truncated_table_fails_closed(self):
        snap = json.loads(dmb.snap_path("one_qb", 2022).read_text())
        with self.assertRaises(ValueError):
            dmb.year_shares(snap["rows"], "one_qb", 2022)


if __name__ == "__main__":
    unittest.main()
