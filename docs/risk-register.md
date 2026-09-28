# Risk And Gap Register

Last updated: 2026-09-28.

This is the durable register for repo gaps, risks, unresolved questions, and
recently fixed correctness defects. A gap is not considered recorded if it only
exists in chat or a session transcript.

## How To Use

- Add a row whenever a session discovers a durable issue future sessions would
  otherwise rediscover.
- Update the same row when the issue is fixed, controlled, or deliberately
  deferred.
- Put session-by-session evidence in `docs/claude-log.md`; keep this file to
  current status, evidence, and next action.
- Do not create another gap tracker or backlog. The live plan is
  `execution/current-plan.md`.

## Active Gaps

| ID | Gap | Severity | Status | Evidence | Next Action |
| --- | --- | --- | --- | --- | --- |
| GAP-007 | Canonical freshness gate is red because the comparison source artifact is stale. | High | Open | On 2026-09-28, `make validate` failed at `freshness-check`: `comparison.built_at` is `2026-09-25T22:38:27Z`, age 3 days with `MAX_STALE_DAYS=2`. `make sync && make test` still passed 386 tests / 6 skipped. | Run the source-refresh pipeline with current source data, then rerun `make validate` before any validation-clean deploy claim. |

## Fixed Or Controlled

| ID | Gap | Severity | Status | Evidence | Follow-up |
| --- | --- | --- | --- | --- | --- |
| FIX-001 | Required read-first entrypoints were missing. | Medium | Fixed 2026-09-27 | Added `SYSTEM_MAP.md`, `docs/methodology.md`, `docs/director_operating_model.md`, and `execution/current-plan.md`. | Keep these as maps to the authoritative docs; do not duplicate detailed rules. |
| FIX-002 | ESPN indexed curve was a browser-derived projection model instead of the built ESPN leg. | High | Fixed 2026-09-25 | `buildEspnIndexedMap()` now prefers the fixture leg and only falls back below `ValueModel.MIN_SHARED_FOR_PIE`; tests cover both renderers. | Keep raw ESPN value above waivers separate and clearly labeled. |
| FIX-003 | Adjusted curves sat above the ESPN anchor scale at QB. | High | Fixed 2026-09-26 | Live adjusted curves now use `ValueModel.shapeToAnchorPeaksThenSharedTotal()` after applying adjustment cells; prior QB peak ratios were 1.5x-2.0x. | Continue checking `adjustedAgreement` in browser diagnostics after chart changes. |
| FIX-004 | Comparison dashboard adjusted columns lagged the curve widget's live adjustment logic. | High | Fixed 2026-09-27 | `comparison-dashboard.js` now loads `adjustment-inputs.json`, builds live adjusted maps from cells, and uses the same anchor-shaping normalizer as the curve widget. | Regression tests in `test_two_tier_frontend.py` assert both renderers share this path. |
| FIX-005 | Importer/health assumed one vintage per Supabase table. | High | Fixed 2026-09-25 | Import and health now scope to the latest complete week/snapshot and direct vintage checks still fail closed on mixed rows. | Preserve scoped import manifests and health checks during future source-table changes. |
| FIX-006 | Adjusted source projects could read like native upstream adjusted artifacts. | Medium | Fixed 2026-09-27 | Dashboard health cards and comparison table badges now say derived adjusted project/project; regression tests reject the old "bias adjusted" and "Bias-corrected best estimate" copy. | Keep adjusted labels tied to the derived-project contract while cells are fitted locally. |
| FIX-007 | Adjustment-cell incompleteness could silently mix raw published values into adjusted projects. | High | Fixed 2026-09-28 | Adjustment inputs now record complete/missing cell coverage, both renderers only activate adjusted source projects when all 8 position/tier cells are present, and partial sources return empty adjusted maps instead of raw fallback. `make diagnostics` covers the rule. | Refit cells during source refreshes; a source returns to default only when `cell_coverage.complete` is true. |
| FIX-008 | Source review confused newer-vintage movement with same-vintage corruption. | Medium | Fixed 2026-09-28 | Reindex now preserves candidate vintage metadata; review reports native vintage context, keeps same-vintage/unknown drift fail-closed, and reports different-vintage drift as measured source movement. Tests cover all three cases. | Keep `week_designated`, `published`, or `content_vintage` on candidate artifacts so review has evidence. |
| CTL-001 | This workspace uses `.gitstore` instead of a normal `.git` directory. | Medium | Controlled | Plain `git status` fails, but `git --git-dir=.gitstore --work-tree=. status` works on `main`; sandbox refused creating a `.git` pointer file. | Use explicit `.gitstore` flags for commit/push from this workspace, or repair local Git metadata outside the sandbox. |
| CTL-002 | Production Supabase writes can damage live data. | High | Controlled | Repo rules require explicit approval before production writes or schema changes. | Continue using dry-run/read-only paths unless the user explicitly approves writes. |
| CTL-003 | Missing values can be mistaken for zero. | High | Controlled | Pipeline rules and tests enforce null/absent for missing values and preserve genuine zeros. | Keep null-vs-zero tests on every source ingestion path. |
| CTL-004 | Raw ESPN value above waivers can be confused with indexed trade value. | Medium | Controlled | Raw series is separate (`espn_vorp`) and labeled as raw value above waivers. | Do not use it as the common trade-value anchor. |
| CTL-005 | Fresh Playwright browser diagnostics are blocked by local browser sandboxing. | Medium | Controlled 2026-09-28 | Local Chromium still cannot be launched in this host, but `make diagnostics` now runs dependency-free chart/value diagnostics through the Node harness and fixture integrity checks. | Use `make diagnostics` locally when browser launch is blocked; run browser sweeps on a host/profile where Chromium can launch. |
| CTL-006 | CBS published-player coverage is thinner than other sources. | Medium | Controlled 2026-09-28 | Current fixture has CBS `full_12` at 119 native/reindexed players and omits Bo Nix; `tests/test_comparison_source_integrity.py` asserts CBS reindexed values never add unpublished players. | Keep no-imputation behavior; re-evaluate coverage after the next real CBS source refresh. |

## Required Approval Gates

Stop for user approval before:

- Any production Supabase write or schema change.
- Any public cutover or publish when validation is red.
- Any credential/login action.
- Any destructive Git/history operation.
- Any business-rule change not inferable from current implementation.
