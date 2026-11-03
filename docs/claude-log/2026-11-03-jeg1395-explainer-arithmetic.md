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
