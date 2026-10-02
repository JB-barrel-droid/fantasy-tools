"""Guard tests for SQL migration files."""

import re
from pathlib import Path

import unittest

MIGRATIONS_DIR = Path(__file__).parent.parent / "sql" / "migrations"


class TestMigration005ConstraintSyntax(unittest.TestCase):
    """Test that migration 005 uses correct DROP CONSTRAINT syntax."""

    def test_migration_005_uses_drop_constraint_not_index(self):
        """Migration 005 must use ALTER TABLE DROP CONSTRAINT for source_trade_values_grain.

        The original source_trade_values_grain was a UNIQUE CONSTRAINT (created via
        ADD CONSTRAINT), not a plain index. Using DROP INDEX would fail at runtime
        in Supabase with: "index does not exist".

        This guard ensures the fix for JEG-90 stays in place.
        """
        migration_file = MIGRATIONS_DIR / "005_source_trade_values_grain_bake_aware.sql"
        content = migration_file.read_text()

        # Must contain DROP CONSTRAINT for the grain
        assert "DROP CONSTRAINT IF EXISTS source_trade_values_grain" in content, (
            "Migration 005 must use ALTER TABLE DROP CONSTRAINT IF EXISTS "
            "source_trade_values_grain"
        )

        # Must NOT use DROP INDEX for this constraint
        # (allowing DROP INDEX for other unrelated indexes is fine)
        # Look for DROP INDEX specifically targeting source_trade_values_grain
        drop_index_pattern = re.compile(
            r"DROP\s+INDEX\s+.*source_trade_values_grain",
            re.IGNORECASE
        )
        match = drop_index_pattern.search(content)
        assert match is None, (
            f"Migration 005 must NOT use DROP INDEX for source_trade_values_grain. "
            f"Found: {match.group(0) if match else 'none'}"
        )

    def test_migration_005_alter_table_form(self):
        """Migration 005 must use ALTER TABLE form, not standalone DROP INDEX."""
        migration_file = MIGRATIONS_DIR / "005_source_trade_values_grain_bake_aware.sql"
        content = migration_file.read_text()

        # Verify it uses ALTER TABLE DROP CONSTRAINT
        assert "ALTER TABLE" in content and "DROP CONSTRAINT" in content, (
            "Migration 005 must use ALTER TABLE ... DROP CONSTRAINT syntax"
        )
