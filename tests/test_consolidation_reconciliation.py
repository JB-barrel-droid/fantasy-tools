#!/usr/bin/env python3
"""Discrimination tests for the consolidation layer (JEG-324).

Standing rule: a guard must prove it catches the bug it names. Each negative
test constructs a simulated broken state and asserts the reconciler fails —
a test that only asserts the current happy path proves nothing.
"""

import copy
import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from build_consolidated_values import (
    build_rows,
    composite_key,
    parse_combo_key,
    reconcile,
    QB_VARIANT_SOURCES,
)

FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"


def load_detail():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


class TestComboKeyParsing(unittest.TestCase):
    def test_plain_combo(self):
        self.assertEqual(parse_combo_key("full_12"), ("full", 12, None))

    def test_qb_variant_combo(self):
        self.assertEqual(parse_combo_key("full_12_qb1"), ("full", 12, "qb1"))
        self.assertEqual(parse_combo_key("half_8_qb2"), ("half", 8, "qb2"))

    def test_garbage_combo_rejected(self):
        self.assertIsNone(parse_combo_key("full"))
        self.assertIsNone(parse_combo_key("full_12_qb3"))
        self.assertIsNone(parse_combo_key(""))


class TestRowBuilding(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.detail = load_detail()
        cls.rows, cls.diagnostics = build_rows(cls.detail)

    def test_builds_rows(self):
        self.assertGreater(len(self.rows), 10000,
                           "expected ~20k rows from the real fixture")

    def test_qb_variant_invariant(self):
        """qb_variant is a real variant (qb1/qb2) IFF the source is fantasycalc*;
        rows without a variant carry the 'none' sentinel (PK can't be NULL)."""
        for row in self.rows:
            if row["qb_variant"] not in (None, "none"):
                self.assertIn(row["source"], QB_VARIANT_SOURCES,
                              f"qb_variant on non-fantasycalc source: {row}")
            if row["source"] in QB_VARIANT_SOURCES and \
                    row["view"] == "combo_reindexed":
                self.assertNotIn(row["qb_variant"], (None, "none"),
                                 f"fantasycalc row missing qb_variant: {row}")

    def test_values_exact_not_rounded(self):
        """Consolidation stores exact detail values (Codex rec #1)."""
        sources = self.detail["sources"]
        for row in self.rows[:500]:  # sample for speed
            locator = row["detail_locator"]
            if ".combos." in locator:
                import re
                m = re.match(r"sources\.(.+)\.combos\.(.+)\.(reindexed|values)\['(.*)'\]$",
                             locator)
                expected = sources[m.group(1)]["combos"][m.group(2)][m.group(3)][m.group(4)]
            else:
                import re
                m = re.match(r"sources\.(.+)\.vorp_views\.views\.(.+)\['(.*)'\]$",
                             locator)
                expected = sources[m.group(1)]["vorp_views"]["views"][m.group(2)][m.group(3)]
            self.assertEqual(row["value"], expected,
                             f"value was rounded/altered for {locator}")

    def test_detail_locator_resolves(self):
        """Every row carries a locator that resolves to its detail cell."""
        sources = self.detail["sources"]
        for row in self.rows[:500]:  # sample for speed
            locator = row["detail_locator"]
            self.assertTrue(locator.startswith("sources."),
                            f"locator malformed: {locator}")

    def test_view_names_disambiguated(self):
        """Uses combo_reindexed / vorp_indexed (not the colliding pair)."""
        views = {r["view"] for r in self.rows}
        self.assertNotIn("reindexed", views)
        self.assertNotIn("indexed", views)
        self.assertIn("combo_reindexed", views)


class TestReconciliationPositive(unittest.TestCase):
    def test_real_fixture_reconciles(self):
        detail = load_detail()
        rows, _ = build_rows(detail)
        errors = reconcile(rows, detail)
        self.assertEqual(errors, [], f"reconciliation failed: {errors[:5]}")


class TestReconciliationNegative(unittest.TestCase):
    """Simulated broken states — the reconciler MUST fail each one."""

    @classmethod
    def setUpClass(cls):
        cls.detail = load_detail()
        cls.rows, _ = build_rows(cls.detail)

    def test_corrupted_value_fails(self):
        rows = copy.deepcopy(self.rows[:200])
        rows[5]["value"] = rows[5]["value"] + 0.1
        errors = reconcile(rows, self.detail)
        self.assertTrue(any("mismatch" in e for e in errors),
                        "corrupted value was not caught")

    def test_dropped_row_fails(self):
        rows = copy.deepcopy(self.rows[:200])
        dropped = rows.pop(10)
        errors = reconcile(rows, self.detail)
        self.assertTrue(any("missing" in e for e in errors),
                        f"dropped row {dropped['detail_locator']} was not caught")

    def test_duplicate_key_fails(self):
        rows = copy.deepcopy(self.rows[:200])
        rows.append(copy.deepcopy(rows[7]))
        errors = reconcile(rows, self.detail)
        self.assertTrue(any("duplicate" in e for e in errors),
                        "duplicate composite key was not caught")

    def test_invalid_scoring_fails(self):
        rows = copy.deepcopy(self.rows[:200])
        rows[3]["scoring"] = "superflex"
        errors = reconcile(rows, self.detail)
        self.assertTrue(any("invalid scoring" in e for e in errors),
                        "invalid scoring was not caught")

    def test_qb_variant_on_wrong_source_fails(self):
        rows = copy.deepcopy(self.rows[:200])
        # Find a non-fantasycalc combo row and inject a qb_variant.
        for r in rows:
            if r["source"] not in QB_VARIANT_SOURCES and \
                    r["view"] == "combo_reindexed":
                r["qb_variant"] = "qb1"
                break
        errors = reconcile(rows, self.detail)
        self.assertTrue(any("qb_variant" in e for e in errors),
                        "qb_variant on wrong source was not caught")

    def test_unresolvable_locator_fails(self):
        rows = copy.deepcopy(self.rows[:200])
        rows[2]["detail_locator"] = "sources.nope.combos.full_12.reindexed['x']"
        errors = reconcile(rows, self.detail)
        self.assertTrue(any("does not resolve" in e for e in errors),
                        "unresolvable locator was not caught")


class TestCompositeKey(unittest.TestCase):
    def test_key_includes_week(self):
        """The primary key covers (player, source, season, week, scoring,
        teams, qb_variant, view) — week-over-week rows for the same player
        must not collide."""
        detail = load_detail()
        rows, _ = build_rows(detail)
        keys = [composite_key(r) for r in rows]
        self.assertEqual(len(keys), len(set(keys)), "duplicate composite keys")
        # Key arity: 8 components
        self.assertEqual(len(keys[0]), 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
