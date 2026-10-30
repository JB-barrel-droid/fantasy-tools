## 2026-10-30 - Compare's header toolbar stays one row with a held source (JEG-1383)

Finding: `tests.test_v2_waterfall_render` `test_example_fold_guard_fails_on_the_old_header` fails on main after the
137c5531 bake (CI job 123887970944). It stayed hidden because v2-render stops at the earlier guardrails red (JEG-1382).
At 1366x768 the example's boxes moved down exactly 56 px (631.0 to 687.0; job 123879022139 at 7b5a6c3 before the bake),
one 44 px picker row plus the toolbar's 12 px gap. The bake held USA Today. A held source's disabled option reads
"... held this week (data check)" (app/v2/v2.js), which widened the closed `#v2CShown` select, so Compare's header
toolbar wrapped and the compact header (JEG-1112) saved nothing. The guard's assertion was right.

Change:
- `app/v2/v2.css`: from 1280 px, cap the closed picker in Compare's header at 300 px.
- `tests/test_v2_waterfall_render.py`: `check_example_state` fails when that toolbar is taller than 1.5 picker
  rows, and the example print logs both boxes.
No value math changes.

### Verified (check named)

- `py_compile` on the test file.
- CI v2-render on the test-only commit c533b094 (run 41004500179) for failing-before, and on the fix commit for
  passing-after: see the runs named on JEG-1383.

### Claimed, not confirmed

- The wrap's cause (the held option's length) is inferred from the CI numbers and the code; the cloud session can't
  run Chromium. The toolbar and picker sizes now print in CI to confirm it.
- The branch carries the JEG-1381 and JEG-1382 fixes with the same file content as #1202 and #1203.
