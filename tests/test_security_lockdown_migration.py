"""GAP-RLS-MONITORING / GAP-SUPABASE-ADVISORS: pins the 2026-10-08 lockdown.

The live database is checked by public.monitoring_security_posture()
(snapshotted every 6 hours into monitoring-summary.json; a regression opens an
`ops-alert` issue). These offline tests pin the migration that gets it to
clean, so an edit that reopens a hole fails here first. Each rule is
negative-tested against a mutated copy of the migration.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCKDOWN = (ROOT / "supabase/migrations/20261008_security_lockdown.sql").read_text()
POSTURE = (ROOT / "supabase/migrations/20261008_monitoring_6h_and_posture.sql").read_text()

MONITORING_TABLES = ("check_config", "check_observations", "check_heartbeats", "scheduler_heartbeats")
ADVISOR_FUNCTIONS = ("public.f_american_prob", "public.resolve_player_identity", "public.resolve_weekly_identities(",
                     "public.resolve_weekly_identities_strict", "public.enforce_never_blend",
                     "public.validate_never_blend", "api.gate_source_freshness", "monitoring.run_evaluator_cycle",
                     "monitoring.compute_heartbeat_state")


def sql_only(text):
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines())


def lockdown_problems(sql):
    s = sql_only(sql)
    out = []
    for t in MONITORING_TABLES:
        if not re.search(rf"alter table monitoring\.{t}\s+enable row level security", s):
            out.append(f"monitoring.{t}: RLS not enabled")
    if not re.search(r"revoke insert, update, delete, truncate[^;]*on all tables in schema public from anon, authenticated", s):
        out.append("anon/authenticated keep write or TRUNCATE grants on public tables (TRUNCATE ignores RLS)")
    if not re.search(r"alter default privileges for role postgres in schema public\s+revoke insert, update, delete, truncate", s):
        out.append("new public tables would hand anon a write grant again")
    if "enable row level security', t.relname" not in s:
        out.append("public tables do not get RLS enabled")
    loop = s[s.find("for t in"):s.find("end loop;\nend")]
    if "not c.relrowsecurity" not in loop:
        out.append("read policies are added to tables that already have RLS: that OPENS reads RLS blocks today")
    if "has_table_privilege(r, t.oid, 'SELECT')" not in loop:
        out.append("read policies are not limited to roles that can read today (would widen access)")
    if re.search(r"create policy[^;]*for (insert|update|delete|all)", s, re.I):
        out.append("a write policy for anon/authenticated was added")
    if "alter view public.%I set (security_invoker = true)" not in s:
        out.append("public views still run as their owner (bypass RLS)")
    for f in ADVISOR_FUNCTIONS:
        if not re.search(rf"alter function {re.escape(f)}[^;]*set search_path", s):
            out.append(f"{f}: search_path not pinned")
    return out


class LockdownMigrationTest(unittest.TestCase):
    def test_migration_is_complete(self):
        self.assertEqual([], lockdown_problems(LOCKDOWN))

    def test_mutations_are_caught(self):
        mutations = {
            "RLS not enabled": LOCKDOWN.replace("alter table monitoring.check_observations   enable row level security;", ""),
            "TRUNCATE": LOCKDOWN.replace("revoke insert, update, delete, truncate, references, trigger\n  on all tables", "revoke references\n  on all tables"),
            "OPENS reads": LOCKDOWN.replace("and not c.relrowsecurity", ""),
            "widen access": LOCKDOWN.replace("if has_table_privilege(r, t.oid, 'SELECT')", "if true"),
            "write policy": LOCKDOWN.replace("for select to %I using (true)", "for all to %I using (true)"),
            "run as their owner": LOCKDOWN.replace("security_invoker = true", "security_invoker = false"),
            "search_path not pinned": LOCKDOWN.replace("alter function public.validate_never_blend()", "-- x"),
        }
        for want, mutated in mutations.items():
            self.assertNotEqual(LOCKDOWN, mutated, want)
            self.assertTrue(any(want in p for p in lockdown_problems(mutated)), want)


class PostureFunctionTest(unittest.TestCase):
    def test_posture_counts_every_lockdown_rule_in_ok(self):
        body = POSTURE[POSTURE.index("create or replace function public.monitoring_security_posture()"):]
        ok = body[body.index("'ok',"):body.index("'details'")]
        for cte in ("no_rls", "writes", "definer_views where nsp = 'public'", "mutable_path", "anon_secdef"):
            self.assertIn(cte, ok, cte)
        self.assertIn("'TRUNCATE'", body)
        self.assertIn("'monitoring'", body[:body.index("writes as")])

    def test_monitor_rpcs_are_service_role_only(self):
        for fn in ("public.monitoring_security_posture()", "public.monitoring_refresh_summary()"):
            self.assertIn(f"revoke execute on function {fn} from public, anon, authenticated;", POSTURE)
            self.assertIn(f"grant execute on function {fn} to service_role;", POSTURE)

    def test_scheduler_down_noise_is_gone(self):
        body = POSTURE[POSTURE.index("create or replace function monitoring.compute_heartbeat_state"):]
        body = body[:body.index("$function$;")]
        self.assertNotIn("monitoring.scheduler_heartbeats", sql_only(body))
        self.assertNotIn("scheduler_down=true", body)


if __name__ == "__main__":
    unittest.main()
