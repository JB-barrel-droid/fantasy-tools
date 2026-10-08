"""Guard the constraint-backed legacy grain migration (JEG-104)."""
from pathlib import Path
import re
import unittest


MIGRATION = Path(__file__).resolve().parents[1] / "sql/migrations/005_source_trade_values_grain_bake_aware.sql"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.sql = re.sub(r"--[^\n]*", "", MIGRATION.read_text(encoding="utf-8"))

    def test_legacy_grain_dropped_as_constraint(self):
        self.assertRegex(self.sql, r"(?is)ALTER\s+TABLE\s+public\.source_trade_values\s+DROP\s+CONSTRAINT\s+IF\s+EXISTS\s+source_trade_values_grain\s*;")

    def test_no_drop_index_on_constraint(self):
        self.assertNotRegex(self.sql, r"(?is)DROP\s+INDEX\s+(?:IF\s+EXISTS\s+)?(?:public\.)?source_trade_values_grain\b")


if __name__ == "__main__":
    unittest.main()
