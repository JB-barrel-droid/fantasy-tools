## 2026-11-03 - Values explainer arithmetic / JEG-1395

Contract: make the explainer's contributing sources, player aggregates and surplus divisions agree with the current engine. Explanation and read-only exports only; no valuation math or published data changes. JEG-1396 remains sequential on this template.

### Verified (check named)
- Linear JEG-1395 had no comments or active claim; GitHub open-PR searches for JEG-1395 and explainer found no duplicate. Prerequisite #1229 merged on November 1 (`b2809cd3`). Claimed JEG-1395 before creating `codex/JEG-1395-explainer-arithmetic` from main `698368f3`.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_values_explainer_arithmetic`: 8 tests passed. The build renders and compares all 741 players in all three versions (2,223 aggregates, no discrepancies); it checks the displayed final value, contributing-source list and divisor against engine exports, with 0.051 tolerance for a one-decimal display from three-decimal source exports. Kenneth Walker III uses the four chart inputs, not the three projections.
- `python3 -m unittest tests.test_values_explainer_arithmetic tests.test_validate_shards tests.test_jeg1140_explainer_fieldnotes_render` with the same browser environment: 28 tests passed before adding the two final divisor/single-allocation tests. The final arithmetic suite includes those additional two tests.
- Regression discrimination: the raw-surplus export sentinel fails against origin/main's builder (`KeyError: surplusTotal`); mutations reproducing the seven-source mean, a displayed divisor of 7, and a displayed result of 999 all fail the new rendered check.
- Current engine inspection exposed nine fractional-seat allocations (JEG-1335). Its source multiplier is the weighted mean of each allocation's pie/raw-surplus multiplier, not pie divided by the averaged raw surplus. The template explains that distinction instead of printing another false equality. Raw surplus and expected-start-weighted group totals remain separately exported and labelled; the single-allocation branch shows the numeric raw-surplus divisor. The initially added test asserting equality for mixed totals was incorrect and was replaced with checks of the current per-allocation rule; no existing assertion was removed or weakened.
- `git diff --check` and Python compilation passed. Generated app/dist output is excluded from the commit.

- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 make validate`: passed (reference build, sync, guard harness, all core suites, strict value comparison and integration checks). Full receipt: `/tmp/jeg1395-validate.log`; strict comparison: `output/value-check.json`.

### Claimed, not confirmed
- Independent review, full ready-for-review CI, merge, deployment and live verification remain release gates. Draft CI intentionally skips expensive jobs under the repository policy.
- JEG-1396 can follow in this same lane after JEG-1395 lands; it was not started or run in parallel.

## 2026-11-03 - P2 optional render dependencies and setup cleanup

Contract: correct review thread `discussion_r4450955324` on PR #1289, on the existing ticket branch. Parent explicitly advanced this narrow correction. Local/remote head and ticket comments reconciled at `2995ab873f9544092b37a923389f4fbc46908885`, with no competing writer. No speculative #1084 integration, template/wording edit, or risk-register resolution.

### Verified (check named)
- Dependency probing now precedes the build: missing Playwright imports and unavailable Chromium go through `_render_env.unavailable`, which skips only when rendering is optional and raises a hard error when `RENDER_TESTS_REQUIRED=1`.
- An ExitStack registered with `addClassCleanup` closes the browser before stopping Playwright, including failed class setup. Actual build and bundle-read errors are outside the dependency exception handler and remain errors in either mode.
- `python3 -m unittest tests.test_values_explainer_arithmetic.ExplainerHarnessSetupTest`: five bounded controls passed. They cover optional/required missing packages and browsers, genuine build failures, missing bundles and successful cleanup. They use simulated dependencies and do not launch browsers or builds.
- The same controls against the old setup at `2995ab87` fail ten subcases (no unexpected control-run errors), proving discrimination.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_values_explainer_arithmetic tests.test_jeg1140_explainer_fieldnotes_render`: 19 tests passed, no skips. This includes the existing arithmetic/mutation checks and Fieldnotes browser checks. Receipt: `/tmp/jeg1395-p2-affected.log`; discrimination: `/tmp/jeg1395-p2-discrimination.log`.
- `git diff --check` passed. The shared template, separate JEG-1398 wording patch and risk-register file are unchanged. Generated build output is excluded.

### Claimed, not confirmed
- Test-integrity **review-high-risk** floor retained: this delta introduces conditional skips by the documented dependency policy. The coordinator must apply that floor before an independent current-head delta review; the author has not downgraded it or claimed independent review.
- No duplicate full local validation. Full CI on `2995ab87` is the parent receipt, not a receipt for this new delta. New-head CI and independent review remain pending.
- Serial release remains #1084 before #1289; retain both risk-register entries when that integration is authorized. JEG-1398 wording remains separate and unapplied, and JEG-1396 starts only after #1289 is live. No merge or deployment performed.
