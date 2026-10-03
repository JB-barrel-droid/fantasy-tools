"""JEG-211: K/DST are fail-closed exclusions until a reviewed K/DST contract lands.

Acceptance: the 8 skill groups produce identical totals/maps with K/DST
absent or present; no division by an absent group can throw; K/DST input is
rejected loudly rather than silently priced.
"""
import unittest

from pipelines.build_imputed_vorps import (DEDICATED, GROUPS, RosterConfig,
                                           compute_imputed_vorps, infer_roster)


def skill_pool():
    rows = {}
    for j, (pos, n) in enumerate([("QB", 40), ("RB", 100), ("WR", 130), ("TE", 70)]):
        for i in range(n):
            rows[str(1000 + j * 1000 + i)] = (pos, 1000 - i)
    return rows


class KdstOptionalTests(unittest.TestCase):
    def test_kdst_rows_are_rejected_fail_closed(self):
        cfg = RosterConfig(12, dict(DEDICATED), 1, 72, "half_ppr")
        for key, pos in (("9001", "K"), ("9002", "DST")):
            rows = dict(skill_pool())
            rows[key] = (pos, 100.0)
            with self.assertRaisesRegex(ValueError, "skill position"):
                infer_roster(rows, cfg)

    def test_skill_groups_invariant_to_kdst_absence(self):
        cfg = RosterConfig(12, dict(DEDICATED), 1, 72, "half_ppr")
        roles = infer_roster(skill_pool(), cfg)
        # all eight skill groups populated; no K/DST group ever exists
        present = {(skill_pool()[k][0], r) for k, r in roles.items() if r != "cut"}
        self.assertEqual(present, set(GROUPS))
        g = {group: (j + 1) * 10.0 for j, group in enumerate(GROUPS)}
        out = compute_imputed_vorps(skill_pool(), g, cfg)
        for group in GROUPS:
            members = [r for r in out.values() if r["group"] == f"{group[0]}|{group[1].title()}"]
            self.assertGreater(len(members), 0)
            total = sum(r["imputed_vorp"] for r in members)
            self.assertAlmostEqual(total, g[group], places=9)

    def test_no_division_by_absent_group(self):
        # a group with no funded pool and zero budget yields zeros, never an error
        cfg = RosterConfig(1, {"QB": 1, "RB": 0, "WR": 0, "TE": 0}, 0, 1, "standard")
        rows = {"1": ("QB", 5.0), "2": ("QB", 1.0)}
        g = {group: 0.0 for group in GROUPS}
        g[("QB", "starter")] = 20.0
        out = compute_imputed_vorps(rows, g, cfg, require_complete=True)
        vals = [r["imputed_vorp"] for r in out.values() if r["group"].endswith("Starter")]
        self.assertAlmostEqual(sum(vals), 20.0, places=9)


if __name__ == "__main__":
    unittest.main()
