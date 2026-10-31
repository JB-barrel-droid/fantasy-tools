## 2026-10-29 - JEG-1283: document how projections price the chart DDF Value

Contract: write Jeremy's JEG-1280 decision ("A.", 2026-10-29: keep the
measured projection-to-chart coupling and document it) into
`docs/methodology.md`, from the ledger memo on PR #1146. Docs only; no
number, default, weight or hold changes.

### Verified (check named)
- `docs/methodology.md`: new block "How projections price the chart DDF
  Value" under VP-6.3, plus one cross-reference sentence each in the VP-2
  intro and VP-4.5. Every size quoted (median 0.11, up to 1.8, 2.1 on a
  flex flip, 86% through the weights) matches the memo
  `docs/research/projection-influence-ledger/README.md` at PR #1146 head
  `9da1fa8c` (read by `git show`).
- #1077 (seven-player waiver line) is open and unmerged (GitHub PR read,
  2026-10-29 19:47 UTC), so the ledger was not rerun; the text says the sizes
  are at main `430791c4` with the one-player line.
- Values explainer narrative (`app/values-explainer/template.html`) checked
  by hand: its DDF Value, hidden-source and allocation text already agree
  with the new section; no narrative edit. `reviewed.json` re-records the
  logic-file hashes (only `docs/methodology.md` changed, to `29aba03caac6`).
- `python3 -m unittest tests.test_methodology_consistency
  tests.test_methodology_payload`: 12 tests OK.
- `make validate`: the build passed; `test-core` stopped at
  `tests.test_week_history` with one error, `ModuleNotFoundError: No module
  named 'playwright'` in `value_check.run_engine` (this cloud session has no
  Playwright). The 25 `test-core` commands after it, run one by one, all
  passed. Preview CI runs the full gate with Playwright.

### Claimed, not confirmed
- `make values-explainer MARK_REVIEWED=1` could not run here: this cloud
  session cannot download Playwright Chromium. `reviewed.json` was written by
  hand with the same fields `--mark-reviewed` writes (date, HEAD short SHA,
  the five logic-file hashes). A machine with Playwright should confirm the
  page shows no logic-changed flag.
- The ledger memo is on PR #1146, not yet on main; the methodology links its
  path.
