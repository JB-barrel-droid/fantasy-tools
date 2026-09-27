# Risk And Gap Register

Last updated: 2026-09-27.

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
| GAP-002 | Fresh Playwright browser diagnostics are blocked by local browser sandboxing. | Medium | Open | On 2026-09-27 the CLI daemon and direct Playwright launch both reached Chromium, then Chromium aborted on macOS Mach port registration (`bootstrap_check_in ... Permission denied`) before diagnostics could be read. | Run browser sweeps from a host/profile where Chromium can launch, or add a non-browser diagnostic fallback for publish-affecting chart changes. |
| GAP-004 | Adjustment-cell coverage is incomplete for some source/tier combinations. | Medium | Open | 2026-09-27 inspection: FantasyCalc and FantasyPros have 8 cells; USA Today has 7; CBS has 5. Missing cells fall back to raw values before anchor shaping. | Decide whether missing cells are acceptable with explicit labeling, or require cell-completeness gates per source before default display. |
| GAP-005 | CBS published-player coverage is thinner than other sources. | Medium | Open | Prior fixture review found CBS has fewer priced players/QBs and omits some players present elsewhere; downstream matching preserves this rather than imputing. | Verify against the current CBS source when the next source refresh runs. Do not impute missing CBS values. |
| GAP-006 | Source refresh/review can confuse genuine week-over-week movement with corruption. | Medium | Open | 2026-09-25 refresh notes say review holds were manually overridden after native drift vs prior-week fixtures; same-vintage review methodology is still needed. | Update review methodology to compare against same-vintage evidence where available before relying on manual override. |

## Fixed Or Controlled

| ID | Gap | Severity | Status | Evidence | Follow-up |
| --- | --- | --- | --- | --- | --- |
| FIX-001 | Required read-first entrypoints were missing. | Medium | Fixed 2026-09-27 | Added `SYSTEM_MAP.md`, `docs/methodology.md`, `docs/director_operating_model.md`, and `execution/current-plan.md`. | Keep these as maps to the authoritative docs; do not duplicate detailed rules. |
| FIX-002 | ESPN indexed curve was a browser-derived projection model instead of the built ESPN leg. | High | Fixed 2026-09-25 | `buildEspnIndexedMap()` now prefers the fixture leg and only falls back below `ValueModel.MIN_SHARED_FOR_PIE`; tests cover both renderers. | Keep raw ESPN value above waivers separate and clearly labeled. |
| FIX-003 | Adjusted curves sat above the ESPN anchor scale at QB. | High | Fixed 2026-09-26 | Live adjusted curves now use `ValueModel.shapeToAnchorPeaksThenSharedTotal()` after applying adjustment cells; prior QB peak ratios were 1.5x-2.0x. | Continue checking `adjustedAgreement` in browser diagnostics after chart changes. |
| FIX-004 | Comparison dashboard adjusted columns lagged the curve widget's live adjustment logic. | High | Fixed 2026-09-27 | `comparison-dashboard.js` now loads `adjustment-inputs.json`, builds live adjusted maps from cells, and uses the same anchor-shaping normalizer as the curve widget. | Regression tests in `test_two_tier_frontend.py` assert both renderers share this path. |
| FIX-005 | Importer/health assumed one vintage per Supabase table. | High | Fixed 2026-09-25 | Import and health now scope to the latest complete week/snapshot and direct vintage checks still fail closed on mixed rows. | Preserve scoped import manifests and health checks during future source-table changes. |
| FIX-006 | Adjusted source projects could read like native upstream adjusted artifacts. | Medium | Fixed 2026-09-27 | Dashboard health cards and comparison table badges now say derived adjusted project/project; regression tests reject the old "bias adjusted" and "Bias-corrected best estimate" copy. | Keep adjusted labels tied to the derived-project contract while cells are fitted locally. |
| CTL-001 | This workspace uses `.gitstore` instead of a normal `.git` directory. | Medium | Controlled | Plain `git status` fails, but `git --git-dir=.gitstore --work-tree=. status` works on `main`; sandbox refused creating a `.git` pointer file. | Use explicit `.gitstore` flags for commit/push from this workspace, or repair local Git metadata outside the sandbox. |
| CTL-002 | Production Supabase writes can damage live data. | High | Controlled | Repo rules require explicit approval before production writes or schema changes. | Continue using dry-run/read-only paths unless the user explicitly approves writes. |
| CTL-003 | Missing values can be mistaken for zero. | High | Controlled | Pipeline rules and tests enforce null/absent for missing values and preserve genuine zeros. | Keep null-vs-zero tests on every source ingestion path. |
| CTL-004 | Raw ESPN value above waivers can be confused with indexed trade value. | Medium | Controlled | Raw series is separate (`espn_vorp`) and labeled as raw value above waivers. | Do not use it as the common trade-value anchor. |

## Required Approval Gates

Stop for user approval before:

- Any production Supabase write or schema change.
- Any public cutover or publish when validation is red.
- Any credential/login action.
- Any destructive Git/history operation.
- Any business-rule change not inferable from current implementation.
