## 2026-10-29 - Default league entry: paste-box edges and heading (JEG-1281)

Contract: on the default site (no `?design=fieldnotes`), "Find a trade: league-wide" needed a visible paste-box edge and the "Your league" heading beside its arrow. Merged as 7f212319 (`app/v2/v2.css`, `tests/test_v2_league_entry_default_render.py`, `tests/test_v2_tokens.py`, Makefile). Rules are scoped to `:root:not([data-design="fieldnotes"])`, so the flagged page (JEG-1137) is unchanged.

### Verified (check named, as recorded in the commit message)
- `.v2-find-import-body` inputs/textareas/selects and `.v2-find-paste` use `--v2-field-border`: 3.34:1 light and 3.39:1 dark, up from 1.28:1 and 1.35:1.
- League card summary starts its heading 15px from the arrow's centre on the same line at 320, 390 and 1280 (was 742px away at 1280; arrow alone on a line on phone).
- `tests.test_v2_league_entry_default_render` (3 tests) OK at 320/390/1280, light and dark; the edge/heading test fails on origin/main's `v2.css` at all six views; `test_checks_fail_without_fix` and `test_fieldnotes_unchanged` cover the fix and the flagged page.
- JEG-1298 review follow-up: `tests.test_v2_tokens` `check_fieldnotes()` now accepts only `:root:not(<flag>) <descendant>` rules that set no custom property, with three new mutations; the render module was wired into `test-unit-modules`. Unscoped default rules were tried first and rejected: `test_fieldnotes_unchanged` failed, and #1143's slice 2a guard failed.

### Claimed, not confirmed
- CI results on the merged head were not re-checked for this log.
- The PR number is not in the merge commit subject; the commit is 7f212319.
