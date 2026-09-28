# Run Report

Newest entry first. This is the human audit trail for completed work; keep
forward-looking priorities in `execution/current-plan.md`.

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
