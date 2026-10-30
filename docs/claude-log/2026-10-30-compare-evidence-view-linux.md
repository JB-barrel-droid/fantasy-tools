## 2026-10-30 - Compare evidence view render test green on Linux CI (PR #1136; JEG-1319)

Contract: confirm in a real browser the JEG-1319 fixes to the isolated Compare evidence view (toggle grid, net-name column, mutant guard), which `2026-10-29-compare-evidence-view.md` lists as claimed, not confirmed. No value, default, ranking or page change.

This entry supersedes the two "Claimed, not confirmed" bullets in `2026-10-29-compare-evidence-view.md`; that entry is left as written.

### Verified (check named)
- `tests.test_compare_evidence_view_render` passed on Linux Chromium: Render sweep run 40990858701, shard 3 of 3, head 54fb1ef, "Ran 2 tests in 22.337s, OK". That covers 320/390/1280 overflow, keyboard, retained focus and slot, frozen input and the broken-build mutants. The only commit after 54fb1ef is the normal merge of `origin/main` (3686d7b), which touches none of the view's files.
- The overflow cause is named. The disclosure toggle row (glyph pushed right with `margin-left: auto`) was about 5 px wider than its disclosure box at every width. Commit 2637f6e fixes it with a two-column grid. At 320 px a long split-read value took the whole auto column and squeezed the net name to 0 px. Commit 33854a3 fixes that by capping the value column at `fit-content(50%)`.
- The "no wrapping" mutant was vacuous: its `.cev-row-name` target holds short names that fit unwrapped. The assertion itself was wrong. Commit 54fb1ef moves it to the verdict and explanation text, and the guard now reports it.
- CI on head 3686d7b: preview shards 1 to 4, preview-build (rendered gate, 0 page errors, fixed pie 0 of 12 failing), v2-render and settings-render are all green (PR check runs).

### Claimed, not confirmed
- The same run's shard 2 (`test_v2_finder_collapse_render`, 1366x768) and shard 3 (`test_v2_finder_eval_render`, 1366x768 headline off screen) are red on Finder layout. They are not this PR's: the PR changes no Finder code, and the sweep is red on main too (run 40837644855). The two Finder failures were not re-run on main to confirm they are identical.
