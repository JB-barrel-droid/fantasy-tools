# OpenRouter lane result — JEG-396

_Model: z-ai/glm-5.3-flash. Review-only unless the brief says otherwise. Roman integrates; OpenRouter results never merge/push/deploy._

---

# JEG-396 — Freshness SLA Design Review & Plan

One structural criticism before the design: your requirements conflate "the load ran" with "the data is fresh." They are independent failure modes and must be separate checks. A NOOP on a stale bundle passes check #2 and fails check #3; a successful load of a stale bundle passes both. The plan below separates them.

## 1. Staleness rules

Cron is `16:07 UTC` daily.
- **CST (winter):** 16:07 UTC = 10:07 CST. SLA deadline end-of-day Monday 23:59 CST = Tue 05:59 UTC.
- **CDT (summer):** 16:07 UTC = 11:07 CDT. Same absolute deadline: Tue 05:59 UTC.
- **Critical:** 16:07 UTC is *always* after NFL Monday-night games end (~04:15 UTC Tuesday at the latest). So the load on Tuesday's run is the first that can see the completed prior week. That means the "expected week" is the week whose Monday-night games concluded before `now` — i.e., expected week = week containing *yesterday* (see §2, Check 3), and grace deadline is **Wednesday 05:59 UTC** (24h buffer) for warning, **Thursday 05:59 UTC** for critical.

| # | Condition | Severity | Action |
|---|-----------|----------|--------|
| S1 | `bundle_built_at` > 8 days old at load time | Warning | Page slack channel; check morning pipeline health |
| S2 | Load completed but `published_season/week` ≠ expected week after Wed 05:59 UTC | Critical | On-call: rerun workflow, then inspect bundle in `data/weekly/` |
| S3 | Most recent run is `failed` or `zero_signal` | Critical | On-call: rerun workflow with `--force`; if exit 2 persists, check bundle contract (JEG-399) |
| S4 | Two consecutive NOOPs while published week ≠ expected week | Critical | This means the bundle is stale but the loader keeps "succeeding" — the worst silent state. On-call: investigate upstream pipeline |
| S5 | `run_created_at` of newest run > 8 days old | Critical | Load has not run at all — workflow disabled/scheduler dead |
| S6 | `signal_count` = 0 on the current run | Warning | Data-quality; hand to JEG-397 scope, but flag |

## 2. SQL checks (pg_cron, read-only)

Run daily at 16:20 UTC via pg_cron, 15 min after the load, writing to `ops.weekly_freshness_health` (new table in `ops` schema — allowed; no prod-table DDL).

```sql
-- Check 1: publication lag (S1/S2)
select
  case
    when s.bundle_built_at < now() - interval '8 days' then 'S1'
    when s.published_week <> ops.expected_nfl_week(now())
         and now() > date_trunc('week', now()) + interval '2 days 5 hours 59 minutes'
    then 'S2'
  end as breach, s.*
from api.weekly_dashboard_status s
where s.has_current;

-- Check 2: run age (S5)
select 'S5' as breach from api.weekly_dashboard_status
where not has_current or run_created_at < now() - interval '8 days';

-- Check 3: failed/zero run (S3/S6)
select case when r.status = 'failed' then 'S3' else 'S6' end as breach
from api.weekly_dashboard_status s
join runs r on r.id = s.last_run_id
where s.last_run_status in ('failed','zero_signal');

-- Check 4: repeated NOOP on outdated bundle (S4) — needs NOOP history, see below
select 'S4' as breach
from api.weekly_dashboard_status s
where s.last_two_run_outcomes = ARRAY['noop','noop']
  and s.published_week <> ops.expected_nfl_week(now());
```

**Expected-week rule (`ops.expected_nfl_week(ts)`):** NFL weeks are labeled by the Sunday *ending* the week. Given `ts`, take `date_trunc('week', ts + interval '1 day')` (Monday of the current NFL week), and the expected published week is the week whose label matches the most recently completed week — i.e., if `ts` is Mon–Wed, expect the prior week's label; Thu–Sun expect the same week (mid-week refresh of in-progress week is allowed but not required). Encode as a small function in `ops`; state the mapping explicitly against your season-start anchor date (hardcode the 2025 week-1 Tuesday as a constant; bump yearly — flag this as an annual maintenance item in the runbook).

**Gap in your brief:** "repeated NOOP" requires run-outcome history, but `weekly_dashboard_status` as scoped (single current run) can't express it. **JEG-397 must expose `last_two_run_outcomes text[]` or equivalent** — listed in §5. This is a real dependency, not a nice-to-have; S4 is unimplementable without it.

## 3. Alerting split

- **Primary (Supabase):** pg_cron job `weekly-freshness-checks` → writes breach rows to `ops.weekly_freshness_health` → a `pg_net` call (or Database Webhooks) POSTs critical breaches to the on-call webhook. Justification: zero dependency on GitHub Actions availability — if Actions is down (S5's exact cause), Supabase-side alerting still fires. This is the entire point of the standing direction.
- **Fallback (Actions):** the workflow's *own* step after load — query the status view; if breach, set a workflow annotation and job-failure. Do **not** make this primary: it inherits the same failure domain as the loader.
- On-call actions per severity: Warning → slack channel only; Critical → pager + runbook link `runbooks/weekly-dashboard-freshness.md` (create it — JEG-396 scope).

## 4. Failure semantics confirmation

Check 3 confirms fail-closed behavior: after a `failed` run, `has_current` must still be true and point at the *prior* run's `published_season/week` — i.e., the status view must expose the current run's `run_created_at` (not the failed run's). The checks assert exactly that. If JEG-397's view exposes the *latest* run rather than the *serving* run, S3/S5 will both misfire. Add `serving_run_id` vs `last_run_id` distinction (§5).

## 5. Required from JEG-397

1. `published_season`, `published_week`, `bundle_built_at`, `run_created_at`, `signal_count`, `has_current` (as briefed)
2. `last_run_status` (`success` | `noop` | `failed` | `zero_signal`)
3. `last_run_id` **and** `serving_run_id` (or document that run_created_at refers to the serving run)
4. `last_two_run_outcomes text[]` — required for S4
5. Timestamps in `timestamptz`, UTC — the CST/CDT logic in the expected-week function assumes it

## 6. Workflow YAML diff

```diff
       - name: Load weekly dashboard
         run: uv run python pipelines/load_weekly_dashboard.py
+      - name: Freshness fallback check
+        if: always()
+        run: |
+          uv run python scripts/check_weekly_freshness.py --exit-on-breach
+        env:
+          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
+          SUPABASE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}
```

`scripts/check_weekly_freshness.py` executes the same checks via the status view (never the Muse runtime — it's a read-only HTTP query). `if: always()` is deliberate: the check must run and alert even when the load step exits 2.

**Open question for you:** who owns the annual expected-week anchor bump? If nobody, S2 will silently fire false-positives every August until someone adds it to the runbook — put it in the runbook now with an owner.