# 2026-10-07 — JEG-414 follow-up: CI ops artifacts off main (branch ci-artifacts-off-main)

**Session model:** Claude Sonnet 4.6  
**Branch:** `ci-artifacts-off-main`  
**PR:** (open; see PR body for URL)

---

## What was done

Eliminated all bot commits to main from monitoring/ops workflows by moving the
three health-artifact files (`pipeline-checkpoints.json`,
`source-import-health.json`) and the JEG-205 code hash into Supabase
`public.ops_artifacts`. The browser dashboard reads them from Supabase via
PostgREST REST + the anon key at runtime, with a static-file fallback for local
dev.

**Design chosen:** Option (b) — Supabase storage, browser reads REST.
Rationale: all three artifacts are derived from Supabase data; returning them to
Supabase is natural. No Pages deploys are needed to refresh monitoring data.
The freshness watch (`health_artifacts_watch.py`) remains fail-closed: it reads
`produced_at` from Supabase, so a pipeline that stops writing makes the watch go
red exactly as before.

---

## Files changed (12)

- `supabase/migrations/jeg414_ops_artifacts_anon_read.sql` NEW — creates
  `public.ops_artifacts` (anon SELECT, service_role write), grants anon
  EXECUTE on `public.monitoring_summary()`.
- `pipelines/ops_artifact_store.py` NEW — upsert/fetch helpers for
  `public.ops_artifacts`.
- `.github/workflows/health-artifacts.yml` — remove 4 git-commit/push/dispatch
  steps; add "Store health artifacts in Supabase" step conditional on build
  success; `permissions.contents: read`.
- `.github/workflows/source-vintage-check.yml` — replace git commit step with
  Supabase upsert; `permissions.contents: read`.
- `.github/workflows/pages.yml` — add step to write
  `dist/modules/supabase-config.json` from `SUPABASE_URL` +
  `SUPABASE_ANON_KEY` secrets (skipped if secret absent).
- `pipelines/check_source_vintage.py` — add `record_code_hash_supabase()` and
  `_read_code_hash_supabase()`; `check_code_change()` tries Supabase when env
  vars present, file fallback for local dev.
- `pipelines/health_artifacts_watch.py` — read artifacts from
  `public.ops_artifacts` instead of GitHub Pages URL.
- `modules/dashboard.html` + `dist/modules/dashboard.html` — add `_SUPA_CFG`,
  `_fetchOpsArtifact()`, `_fetchMonitoringSummary()` with static-file fallback.
- `tests/test_health_artifacts_publish.py` — rewritten for new contract (no
  git commit, no push, store step conditional on build success); 7 tests all
  passing.
- `tests/test_no_bot_commits_to_main.py` NEW — static guard; fails if any
  workflow outside `ALLOWED_COMMITTERS` has both `git commit` and `git push`
  in non-comment lines; 4 tests passing including 2 negative tests.
- `Makefile` — add `test_no_bot_commits_to_main` to `test-unit`.

---

## Verified

- `python3 -m unittest tests.test_no_bot_commits_to_main` → 4/4 PASS
  (including 2 negative tests that inject `git commit` + `git push` into
  health-artifacts.yml and source-vintage-check.yml).
- `python3 -m unittest tests.test_health_artifacts_publish` → 7/7 PASS
  (including 6 negative tests: git commit caught, git push caught, pages
  dispatch caught, schedule caught, contents:write caught, unconditional store
  caught).
- `python3 -m unittest tests.test_health_artifacts_watch` → 6/6 PASS.
- `python3 -m unittest tests.test_health_artifacts_summary_step` → 3/3 PASS.
- `make validate` run with
  `CHROMIUM_PATH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"`;
  only pre-existing failures:
  - `test_known_full_ppr_12_team_source_values` (25.5 != 25.3) — confirmed
    identical on clean main via `git stash` + run + `stash pop`.
  - `test_published_surfaces` (consolidated-values.json) — confirmed pre-existing
    per session history.

---

## Claimed (not independently confirmed by this session)

- That the Supabase `public.ops_artifacts` table does not already exist.
  (Migration uses `CREATE TABLE IF NOT EXISTS`, so it is safe either way, but
  table presence was not verified with a Supabase read.)
- That the dashboard's `_fetchOpsArtifact` JS fallback path works in a browser
  when `supabase-config.json` is absent. (Static analysis only; no browser run
  of the fallback path.)
- That `SUPABASE_ANON_KEY` is not already set as a GHA secret. (Not checked;
  the `pages.yml` step is harmlessly skipped if the secret is absent.)

---

## Blockers before the branch is live

1. **Jeremy must add `SUPABASE_ANON_KEY`** as a GitHub Actions repository
   secret (Settings → Secrets → Actions). The value is the publishable anon key
   from Supabase project `iskiybsimubiujwuchsl` (Settings → API).
2. **Apply migration** `supabase/migrations/jeg414_ops_artifacts_anon_read.sql`
   to Supabase project `iskiybsimubiujwuchsl`. Without it, the `ops_artifacts`
   table does not exist and the store step in health-artifacts.yml will fail (the
   watch then reports stale, not broken).

---

## Risk register

Added `GAP-CI-BOT-COMMITS` (Active) and `FIX-CI-BOT-COMMITS` (Fixed/Controlled)
rows to `docs/risk-register.md`.
