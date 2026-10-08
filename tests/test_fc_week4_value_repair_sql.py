"""GAP-FC-PRODUCER: supabase/migrations/fc_week4_value_repair.sql.

The week-4 FantasyCalc rows carried the raw published number (~0-10900) in
`value`. The repair must write chart-scale numbers only, touch only rows still
in the broken state, never rewrite native_value, and abort unless the result
is exactly the 591 repaired 12-team rows. Each rule is negative-tested against
a simulated broken migration.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SQL = (ROOT / "supabase/migrations/fc_week4_value_repair.sql").read_text(encoding="utf-8")
ROW_RE = re.compile(r"\('([0-9a-f-]{36})'::uuid,\s*([-0-9.eE]+)\)")


def problems(sql):
    out = []
    rows = ROW_RE.findall(sql)
    ids = [i for i, _ in rows]
    vals = [float(v) for _, v in rows]
    if len(rows) != 591 or len(set(ids)) != 591:
        out.append(f"expected 591 distinct repaired ids, got {len(rows)}/{len(set(ids))}")
    if vals and (max(vals) > 100 or min(vals) < 0):
        out.append(f"value outside chart scale: min {min(vals)} max {max(vals)}")
    upd = sql[sql.index("update public.source_trade_values"):sql.index("delete from")]
    for guard in ("t.bake_id is null", "t.value = t.native_value", "t.week = 4",
                  "t.source = 'fantasycalc'", "t.league_teams = 12"):
        if guard not in upd:
            out.append(f"update lacks guard {guard!r}")
    if re.search(r"set[^;]*native_value\s*=", upd):
        out.append("update rewrites native_value (the week history reads it)")
    dele = sql[sql.index("delete from"):sql.index("do $$")]
    for guard in ("week = 4", "league_teams <> 12", "bake_id is null", "value = native_value"):
        if guard not in dele:
            out.append(f"delete lacks guard {guard!r}")
    if "raise exception" not in sql or "n_ok <> 591" not in sql:
        out.append("no post-condition abort")
    if not re.search(r"^begin;", sql, re.M) or not re.search(r"^commit;", sql, re.M):
        out.append("not one transaction")
    return out


class RepairSqlTest(unittest.TestCase):
    def test_real_migration_is_clean(self):
        self.assertEqual(problems(SQL), [])

    def test_raw_native_in_values_is_caught(self):
        first = ROW_RE.search(SQL)
        broken = SQL.replace(first.group(0), f"('{first.group(1)}'::uuid, 10807.0)", 1)
        self.assertTrue(any("chart scale" in p for p in problems(broken)))

    def test_dropped_broken_state_guard_is_caught(self):
        broken = SQL.replace("  and t.value = t.native_value;", ";")
        self.assertTrue(any("t.value = t.native_value" in p for p in problems(broken)))

    def test_native_rewrite_is_caught(self):
        broken = SQL.replace("set value = v.value,", "set value = v.value, native_value = v.value,")
        self.assertTrue(any("native_value" in p for p in problems(broken)))

    def test_unguarded_delete_is_caught(self):
        broken = SQL.replace("  and league_teams <> 12 and bake_id is null and value = native_value;", ";")
        self.assertTrue(any("delete lacks guard" in p for p in problems(broken)))

    def test_missing_row_is_caught(self):
        first = ROW_RE.search(SQL)
        broken = SQL.replace(first.group(0) + ",\n", "", 1)
        self.assertTrue(any("591" in p for p in problems(broken)))


if __name__ == "__main__":
    unittest.main()
