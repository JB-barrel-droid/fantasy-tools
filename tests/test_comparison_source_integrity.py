"""Fixture integrity checks for source-specific coverage decisions."""
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
COMPARE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"


class TestComparisonSourceIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(COMPARE.read_text(encoding="utf-8"))

    def test_cbs_reindexed_values_do_not_impute_unpublished_players(self):
        combo = self.doc["sources"]["cbs"]["combos"]["full_12"]
        native_slugs = set(combo["native"])
        reindexed_slugs = set(combo.get("reindexed") or combo.get("values") or {})
        self.assertTrue(reindexed_slugs <= native_slugs)
        self.assertNotIn("bo nix", native_slugs)
        self.assertNotIn("bo nix", reindexed_slugs)


if __name__ == "__main__":
    unittest.main()
