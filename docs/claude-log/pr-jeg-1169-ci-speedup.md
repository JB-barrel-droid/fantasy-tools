## 2026-10-27 - JEG-1169: CI speed-up (Ba-Nana, grok-box)

Not written by Jeremy; a Ba-Nana run approved by him on 2026-10-27.

### Changed

- The informational full test suite (`make test-unit`) leaves the PR workflow. It now lives in
  `.github/workflows/full-suite.yml`, nightly (07:17 UTC) plus `workflow_dispatch`, job-level
  `continue-on-error`, 120-minute timeout (it never finished inside the old 45). It is listed in
  `config/monitoring_coverage.json` as unmonitored (informational, gates nothing).
  Note: this is a GitHub `schedule:`, not pg_cron (GAP-GHA-SCHEDULES), because a pg_cron job needs a
  migration; move it if the pg_cron rule should hold here too.
- Playwright browsers are cached (`~/.cache/ms-playwright`, key carries the pinned 1.49.1) in
  preview, pages, v2-render and full-suite. The second Chromium install
  (`npx playwright-core install --with-deps chromium`) is gone: python playwright 1.49.1 and
  rendered_gate's playwright-core 1.49.1 use the same browser build. `--with-deps` still runs apt.
- Timeouts: preview 60 minutes, v2-render 25 (was 15).
- Docs-only PRs skip preview and v2-render (`paths:` with `!**/*.md`, `!docs/**`). Docs the build
  reads are re-included: `docs/methodology.md`, `docs/math-review-agenda.md`,
  `docs/use-ddf-in-claude-chatgpt.md`, `app/llm/**`. Tests-only PRs still run validate.
  pages.yml (deploy) is not path-filtered; its only change is the cache.

### Tests

- `tests/test_preview_workflow_matches_pages.py`: the suite must not be in preview.yml; new
  `check_full_suite` (no PR/push trigger, schedule + dispatch, runs `make test-unit`, non-blocking).
- `tests/test_v2_render_runs_on_data_push.py`: the path-filter mutation targets the push filter.
- New `tests/test_ci_speedup_workflows.py` (in `test-unit-modules`): browser pin, cache-before-install,
  no second install, timeouts, and a `paths` simulator for the docs-only rule, each with a mutation test.

### Verified

- The three modules above and the monitoring, deploy-gate and other workflow guards: OK.
- 42 workflow-reading modules: same 5 failures before and after (render-sweep shards,
  rebuild-chain post-validation), pre-existing on main.
- actionlint 1.7.7 on the four workflows: clean.
