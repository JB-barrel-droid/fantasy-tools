"""ESPN-zero staleness signal (JEG-51).

The first version of the check read only a combo literally named "half_12". FantasyCalc
has no such combo (its keys carry a QB suffix) and USA Today's row for the zeroed player
sat in full_12, so it reported ok while the chart showed the player. These tests pin the
corrected behaviour against a synthetic fixture shaped like the real one.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import check_data_accuracy as cda  # noqa: E402

DASHBOARD = (ROOT / "modules" / "dashboard.html").read_text()


def fixture(**sources):
    base = {
        "espn_zeroed": [4237],
        "player_keys": {"devon achane": 4237, "jahmyr gibbs": 2227},
        "sources": {
            "espn": {"combos": {"full_12": {"values": {"devon achane": 0.0, "jahmyr gibbs": 70.0}}}},
            "usatoday": {"combos": {"half_12": {"reindexed": {"jahmyr gibbs": 45.0}},
                                    "full_12": {"reindexed": {"jahmyr gibbs": 49.0}}}},
            "fantasycalc": {"combos": {"half_12_qb1": {"reindexed": {"jahmyr gibbs": 60.0}}}},
        },
    }
    base["sources"].update(sources)
    return base


class StalenessSignalTest(unittest.TestCase):
    def check(self, fx):
        violations, err = cda.check_espn_zeroed_staleness(fx)
        self.assertIsNone(err)
        return violations

    def test_clean_fixture_has_no_signal(self):
        self.assertEqual([], self.check(fixture()))

    def test_flags_a_source_in_a_combo_other_than_half_12(self):
        fx = fixture(usatoday={"combos": {"full_12": {"reindexed": {"devon achane": 28.1}}}})
        found = self.check(fx)
        self.assertEqual([("usatoday", "devon achane", ["full_12"])],
                         [(v["source"], v["player"], v["combos"]) for v in found])
        self.assertEqual(0.0, found[0]["espn_value"])
        self.assertEqual(28.1, found[0]["source_value"])

    def test_flags_fantasycalc_whose_combos_carry_a_qb_suffix(self):
        fx = fixture(fantasycalc={"combos": {"full_10_qb1": {"reindexed": {"devon achane": 51.6}},
                                             "half_10_qb1": {"reindexed": {"devon achane": 55.6}},
                                             "full_12_qb1": {"reindexed": {"jahmyr gibbs": 60.0}}}})
        found = self.check(fx)
        self.assertEqual(1, len(found))  # one violation per (source, player)
        self.assertEqual(55.6, found[0]["source_value"])  # the highest value
        self.assertEqual(["full_10_qb1", "half_10_qb1"], found[0]["combos"])
        self.assertEqual(2, found[0]["n_combos"])

    def test_zero_or_missing_values_are_not_flagged(self):
        fx = fixture(usatoday={"combos": {"full_12": {"reindexed": {"devon achane": 0.0}}}},
                     fantasycalc={"combos": {"half_12_qb1": {"reindexed": {}}}})
        self.assertEqual([], self.check(fx))

    def test_espn_itself_and_adjusted_derivatives_are_not_flagged(self):
        fx = fixture(usatoday_adjusted={"combos": {"full_12": {"reindexed": {"devon achane": 30.0}}}})
        fx["sources"]["espn"]["combos"]["full_12"]["values"]["devon achane"] = 5.0
        self.assertEqual([], self.check(fx))

    def test_no_zeroed_list_or_unknown_ids_are_quiet(self):
        fx = fixture(usatoday={"combos": {"full_12": {"reindexed": {"devon achane": 28.1}}}})
        fx["espn_zeroed"] = []
        self.assertEqual([], self.check(fx))
        fx["espn_zeroed"] = [999999]
        self.assertEqual([], self.check(fx))

    def test_wording_does_not_claim_ir(self):
        fx = fixture(usatoday={"combos": {"full_12": {"reindexed": {"devon achane": 28.1}}}})
        reason = self.check(fx)[0]["reason"]
        self.assertIn("ESPN zeroed", reason)
        self.assertNotIn("IR", reason)

    def test_the_real_fixture_is_readable_and_violations_are_well_formed(self):
        # Deliberately does not pin WHICH sources are stale today: that is data, and
        # it should be allowed to improve (GAP-025/026) without turning this red.
        violations, err = cda.check_espn_zeroed_staleness()
        self.assertIsNone(err)
        for v in violations:
            self.assertEqual({"player", "player_id", "source", "espn_value", "source_value",
                              "combos", "n_combos", "reason"}, set(v))
            self.assertEqual(0.0, v["espn_value"])
            self.assertGreater(v["source_value"], 0)


class MonitorWiringTest(unittest.TestCase):
    def test_the_dashboard_has_a_card_that_reads_the_check(self):
        self.assertIn('id="espnZeroCard"', DASHBOARD)
        self.assertIn('fetch("data-accuracy.json"', DASHBOARD)
        self.assertIn('c.name === "espn_zeroed_staleness"', DASHBOARD)
        self.assertTrue(re.search(r"^loadEspnZeroSignal\(\);$", DASHBOARD, re.M),
                        "the loader is defined but never called")

    def test_the_built_dashboard_copy_matches(self):
        self.assertEqual(DASHBOARD, (ROOT / "dist" / "modules" / "dashboard.html").read_text())


if __name__ == "__main__":
    unittest.main()
