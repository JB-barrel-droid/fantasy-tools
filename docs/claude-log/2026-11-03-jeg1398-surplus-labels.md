## 2026-11-03 - Advanced series units (JEG-1398)

Contract: label displayed Value above waivers as surplus rescaled to the league
pie, retaining each source's own weighting. Copy only in `app/v2/v2.js` and
`app/v2/shell.html`; the JEG-1395 owner retains the explainer template.

### Verified (check named)

- Ownership check: JEG-1398 had no comments or duplicate open PR; JEG-1394/#1240
  is merged, #1225 is parked Todo, and #1096 is a separate private preview.
  Based on production main `698368f366b8b438c1adfd70e452c34370b57abd` (#1277).
- `tests.test_v2_rescaled_copy.AdvancedSurplusCopyTest`: three new tests fail
  with 11 failures on the original UI sources, then pass after the copy fix.
  Covers Fieldnotes group copy, Customize, player detail, Compare captions,
  static panels and retired native-unit claims.
- `python3 -m unittest tests.test_v2_rescaled_copy tests.test_jeg1130_v2_copy
  tests.test_v2_copy_names`: all 11 tests pass. No existing assertion weakened.
- `node --check app/v2/v2.js` and `git diff --check` pass. Line comparison
  masking double-quoted strings confirms identical non-copy JavaScript;
  valuation engine and excluded explainer template have no diff.
- The first `make validate` stopped during sync because bundled Chromium was
  missing. `/usr/bin/chromium` exists; the subsequent gate uses
  `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1`.
- Full `make validate` with that explicit browser passed (exit 0): reference,
  sync, guard harness, every core module, strict comparison and hermetic
  integration tests. `output/value-check.json` reports 1,234,507 values
  compared, verdict `agree`, no disagreeing sources, no composite
  disagreements and no page errors across 25 settings. The view-invariant
  audit passed 270 checks across 15 settings.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest
  tests.test_v2_contract_render`: all six tests pass, including live contract
  lines and mutation guards, with no skips (451.372 seconds).
- `tools/engine_dump.py --out /tmp/jeg1398-engine.json`, with that same
  browser: all 13 settings pass `fixedPieIndexed` and `indexedOrderOk`, covering
  all three scorings times four league sizes plus 12-team PPR superflex.
  Position curve starts are recorded and finite for each displayed series.
  Summary: `/tmp/jeg1398-sweep-summary.json`.
- Current-main AGENTS was checked after discovering the starting checkout was
  stale. The claim now uses only the Codex label and branch
  `codex/JEG-1398-surplus-labels`; the initial `fe/` branch remains unpushed.

### Claimed, not confirmed

- Draft-PR CI and independent review are pending. `v2.js` is a hot file, so the
  coordinator must apply the deterministic high-risk floor despite copy-only
  scope and the ticket's older review-standard label.
- No production verification, merge, deployment or Supabase operation occurs
  in this lane. Generated build output is excluded from the PR.

Explainer handoff for its existing owner: use "Value above waivers is surplus
rescaled to the league pie, keeping each source's own weighting" in the display
description and display-step captions (template's display step around line 557,
source formula around line 748 and player trace around line 814 at the base).
Keep the native-input explanation around line 543 in native units: that stage
precedes the display conversion. The display multiplier in the unchanged engine
is `pie / surplusTotal` (value-model.js:1843), applied to `r.vorp` at line 1850;
JEG-1395 owns the arithmetic/divisor corrections. This lane does not edit the
template or its tests.
