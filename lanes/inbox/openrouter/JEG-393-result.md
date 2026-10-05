# OpenRouter lane result — JEG-393

_Model: z-ai/glm-5.3-flash. Review-only unless the brief says otherwise. Roman integrates; OpenRouter results never merge/push/deploy._

---

# Review findings first (three real problems with the brief as written)

1. **Brief §1, "validate ... candidate exists"**: The function must distinguish "not found" from "already current" — the brief implies raising the same error. If the loader retries after a *successful* promote that it never heard back about (classic RPC timeout), the retry would fail on "not current". Fix: idempotent no-op return when candidate is already current **and** signal count still matches, so retries are safe. Diff below does this.
2. **Brief §3, unique index backstop**: This is the one-way door. If the table currently has **two** current rows (the bug already happened in prod once — that's why this ticket exists), `CREATE UNIQUE INDEX` fails and the migration aborts. The comment alone doesn't prevent that. Fix: the migration includes a guard that raises if a violation exists *before* attempting the index, so failure is explicit and diagnosable, plus a documented remediation query.
3. **Regression check ordering**: `(season, week)` comparison must be tuple-safe across season rollover — `week` alone resets to 1 each season. Use row comparison `(season, week) > (cur.season, cur.week)` or reject only when strictly older. Row-comparison in Postgres does the right thing; use it.

# Migration SQL

```sql
-- JEG-393: atomic weekly dashboard run promotion.
-- PRECONDITION: at most ONE row in public.weekly_dashboard_runs with is_current = true.
-- This migration will fail loudly (exception) if that precondition is violated.
-- Remediation if it fails: manually clear stale rows first:
--   UPDATE public.weekly_dashboard_runs SET is_current = false WHERE run_id = '<stale_run_id>';
-- After this migration, the unique index makes >1 current row impossible.

BEGIN;

DO $$
DECLARE v int;
BEGIN
  SELECT count(*) INTO v FROM public.weekly_dashboard_runs WHERE is_current;
  IF v > 1 THEN
    RAISE EXCEPTION 'JEG-393 precondition violated: % current rows exist; must be <= 1', v;
  END IF;
END $$;

CREATE OR REPLACE FUNCTION public.promote_weekly_dashboard_run(
  p_run_id uuid,
  p_expected_signals int
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  candidate public.weekly_dashboard_runs;
  actual_signals bigint;
  cur_season int;
  cur_week int;
BEGIN
  -- Serialize concurrent promotions. Transaction-scoped: auto-released at commit/abort.
  PERFORM pg_advisory_xact_lock(hashtext('weekly_dashboard_promotion'));

  SELECT * INTO candidate
  FROM public.weekly_dashboard_runs
  WHERE run_id = p_run_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'run % not found', p_run_id
      USING ERRCODE = 'P0002';
  END IF;

  SELECT count(*) INTO actual_signals
  FROM public.weekly_dashboard_signals
  WHERE run_id = p_run_id;

  -- Idempotent success path: already current with matching count => return true (safe retry).
  IF candidate.is_current THEN
    IF actual_signals = p_expected_signals THEN
      RETURN true;
    END IF;
    RAISE EXCEPTION 'run % is current but has % signals, expected %',
      p_run_id, actual_signals, p_expected_signals
      USING ERRCODE = 'P0003';
  END IF;

  IF actual_signals <> p_expected_signals THEN
    RAISE EXCEPTION 'signal count mismatch for run %: got %, expected %',
      p_run_id, actual_signals, p_expected_signals
      USING ERRCODE = 'P0003';
  END IF;

  SELECT season, week INTO cur_season, cur_week
  FROM public.weekly_dashboard_runs
  WHERE is_current;

  IF FOUND AND (candidate.season, candidate.week) < (cur_season, cur_week) THEN
    RAISE EXCEPTION 'refusing regression: run % is season % week %, current is season % week %',
      p_run_id, candidate.season, candidate.week, cur_season, cur_week
      USING ERRCODE = 'P0004';
  END IF;

  UPDATE public.weekly_dashboard_runs SET is_current = false WHERE is_current;
  UPDATE public.weekly_dashboard_runs SET is_current = true WHERE run_id = p_run_id;

  RETURN true;
END;
$$;

REVOKE ALL ON FUNCTION public.promote_weekly_dashboard_run(uuid, int)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.promote_weekly_dashboard_run(uuid, int)
  TO service_role;

CREATE UNIQUE INDEX weekly_dashboard_one_current
  ON public.weekly_dashboard_runs (is_current)
  WHERE is_current;

COMMIT;
```

Notes on choices:
- `SET search_path = public, pg_temp` + fully qualified tables: meets the fixed-search_path requirement; `pg_temp` first-attack is not possible since nothing is referenced unqualified, but keep it belt-and-braces.
- SECURITY DEFINER bypasses RLS on the two tables for the promote path only; EXECUTE is restricted to service_role so the widening is bounded.
- Advisory lock key uses `hashtext` — fine for a single coordinator lock. If other code adds advisory locks later, standardize on a documented int8 key instead.

# Loader diff

```diff
--- a/pipelines/load_weekly_dashboard.py
+++ b/pipelines/load_weekly_dashboard.py
@@
-    # Promote: clear other runs, then set this one current (two PATCHes).
-    # Crash window: zero or two current rows.
-    postgrest.patch(
-        "weekly_dashboard_runs",
-        params={"is_current": "eq.true", "run_id": f"neq.{run_id}"},
-        body={"is_current": False},
-    )
-    postgrest.patch(
-        "weekly_dashboard_runs",
-        params={"run_id": f"eq.{run_id}"},
-        body={"is_current": True},
-    )
+    # Promote atomically via RPC. Idempotent: safe to retry on timeout.
+    resp = postgrest.rpc(
+        "promote_weekly_dashboard_run",
+        body={"p_run_id": run_id, "p_expected_signals": signal_count},
+    )
+    if not resp.ok:
+        raise RuntimeError(
+            f"promote_weekly_dashboard_run failed for {run_id}: "
+            f"{resp.status_code} {resp.text}"
+        )
```

The read-back count check (step 3) stays untouched and its count is reused as `p_expected_signals` — if that's not how the existing variable is named, rename in the diff accordingly; the important thing is one count, verified pre-promotion, passed to the DB for re-verification.

# Test plan

1. **Crash between signal insert and promote**: run loader with a fault injected after batch insert (kill -9 or exception before the RPC). Expected: run exists with `is_current=false`, view still points at previous run, zero-current window does not exist. Re-run loader (or call RPC directly with the same count) → succeeds, exactly one current row.
2. **Two concurrent promotions** for two different new runs of the same week: launch two RPC calls simultaneously. Expected: one commits, the other blocks on the advisory xact lock then commits (later run_id wins; both succeed, exactly one current row). For two loaders at *different* weeks, the older one must be rejected with P0004. Verify via `SELECT run_id FROM weekly_dashboard_runs WHERE is_current` → exactly 1 row at all times; observe with a concurrent reader loop that `v_current_weekly_signals` never returns mixed weeks and never returns empty.
3. **Older-week promotion attempt**: after promoting season 2026 week 10, attempt RPC for season 2026 week 9 with correct count. Expected: exception P0004, no rows mutated (`is_current` unchanged). Also test season rollover: season 2027 week 1 must be *accepted* over season 2026 week 53 (this is the row-comparison case).

# One-way doors

- **The partial unique index.** Once live, any future write path that sets two current rows in the same statement/transaction (e.g., an innocent `UPDATE ... SET is_current = NOT is_current` without ordering) will throw at runtime. All future writers must go through the RPC or be aware of the index. This is the intended constraint, but it forecloses any legitimate multi-current use (e.g., "current per season"). If that's plausible, use a unique index on `(season, week) WHERE is_current` instead — cheaper to add now than to unwind later. Flag for Roman to confirm before applying.
- **Function ownership**: SECURITY DEFINER runs as the migration role. If that role is later dropped/renamed, EXECUTE breaks. Pin ownership explicitly (`ALTER FUNCTION ... OWNER TO` a stable role) in the same migration rather than leaving it implicit.
- The REVOKE cannot be undone safely once loaders depend on the RPC — fine, but note it in the runbook.

One thing the brief missed: the loader's step 2 batch INSERT is still not atomic with the run INSERT (REST = autocommit per call). A crash there leaves an orphan run with partial signals. The count check catches it (mismatch → promote refuses), but the orphan rows accumulate. Worth a JEG-394 note: either insert signals via the same RPC's transaction or add a cleanup for stale `is_current=false` runs older than N days. Not a blocker.