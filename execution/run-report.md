# Run Report

Newest entry first. This is the human audit trail for completed work; keep
forward-looking priorities in `execution/current-plan.md`.

## 2026-09-28 - Live deploy attempt blocked by source-refresh access

### Scope

- Tried to get the pushed gap-cleanup commit live through the normal GitHub Pages
  workflow without weakening validation.

### Commands / evidence

- `gh run list --repo JB-barrel-droid/fantasy-tools --workflow "Deploy dashboard"
  --limit 5` showed push run `36463813393` and scheduled run `36466759302`
  failed on `main`.
- `make supabase-import SOURCE=fantasycalc` failed before any snapshot write:
  `ModuleNotFoundError: No module named 'sbclient'`.
- Filesystem search found no local `sbclient.py` and no
  `~/workspace/skills/supabase-football-signal/bin` helper directory.
- No `SUPABASE_*` environment variables were present in this task. Supabase and
  Claude MCP calls were not usable because the task's approval policy was
  `never`.
- Sibling/temp checkouts only had older or same-vintage generated
  `comparison-sources-data.json` files; no newer validated source snapshot was
  available to promote.

### Result

- Not live yet. The repo is intentionally still fail-closed: no timestamp bump,
  freshness-threshold relaxation, or forced deploy was made.
- Added `GAP-008` to `docs/risk-register.md` and updated
  `execution/current-plan.md` so the next session starts with the missing
  Supabase import helper/access problem.

## 2026-09-28 - Open gap cleanup

### Scope

- Closed or controlled the open rows in `docs/risk-register.md` for adjustment
  cell completeness, source-review vintage handling, CBS no-imputation
  coverage, and non-browser diagnostics fallback.

### Changes made

- `pipelines/build_adjustment_inputs.py` and the adjustment-input artifacts now
  record expected/present/missing cell coverage and mark incomplete sources as
  `partial-stage2`.
- `curve-widget.js` and `comparison-dashboard.js` now require complete live
  adjustment cells before rendering/defaulting an adjusted source project.
  Partial sources return no adjusted map instead of silently falling back to raw
  or stale baked adjusted values.
- `pipelines/reindex_comparison_section.py` now preserves candidate vintage
  metadata for review.
- `pipelines/review_comparison_candidate.py` now treats same-vintage or
  unknown-vintage native drift as corruption-sensitive, while different-vintage
  drift is reported as measured source movement.
- Added `make diagnostics` as a named non-browser diagnostic fallback and
  documented it in `README.md`.
- Added CBS no-imputation fixture coverage in
  `tests/test_comparison_source_integrity.py`.
- Updated `docs/risk-register.md` and `execution/current-plan.md`.

### Validation

- `make diagnostics` -> pass: 103 tests OK, 6 skipped.
- `make validate` -> fail at `freshness-check`: `comparison.built_at` is
  `2026-09-25T22:38:27Z`, age 3 days on 2026-09-28 with
  `MAX_STALE_DAYS=2`.
- `make sync && make test` -> pass: dashboard artifacts synced; 386 tests OK,
  6 skipped.

### Artifacts / state observed

- Canonical generated reports exist in `output/`; `reference-freshness.json`
  records the stale enforced comparison artifact.
- Local Claude Code MCP setup is authenticated and ready, but starting a
  delegated Claude session was blocked because the MCP call required approval
  while this task's approval policy was `never`.

### Decisions / follow-ups

- Do not claim a validation-clean deploy until the source-refresh pipeline
  updates the comparison source artifact and `make validate` passes.
- Use `make diagnostics` when local Playwright/Chromium browser diagnostics are
  unavailable.
