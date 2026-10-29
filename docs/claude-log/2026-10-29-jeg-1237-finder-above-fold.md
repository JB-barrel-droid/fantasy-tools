## 2026-10-29 - JEG-1237 finder above-fold regressions

Contract: restore the approved JEG-972 / JEG-1019 above-fold behavior (after Find, results start inside the first
screen at 1366x768 and the fit headline is on screen) without enlarging the viewport, hiding results, removing
assertions or changing search, values, fit or defaults.

### Verified (check named, Linux CI via render-sweep dispatch on scratch branches; no local Chromium here)
- Failing before, main 3cb2fe4 (run 40834667934): `test_v2_finder_collapse_render` "[1366px] results start at 818px of
  a 768px screen"; `test_v2_finder_eval_render` headline at 734-777 in a 768px viewport (both scenarios). Same numbers as
  the coordinator's Mac sweep on dbe06a7e. Render sweep on main 31ccf10e (Oct 28) passed both.
- Cause, measured after Find at 1366x768: JEG-1184 put two fieldsets between the Find toolbar and the headline,
  Protect my starting group (418-535) and Minimum bench backups (547-664), then Advanced (676-720). Results need to
  start above 614. Side-by-side compaction cannot get there with both settings still showing.
- Fix: the two fieldsets fold with the roster input after Find (one `#v2FindGuardrails` wrapper toggled by
  setCollapsed), the folded summary reads them back as one "Trade settings:" line, Edit rosters reopens them, Advanced
  trade minimums stays on the page as its own closed disclosure.
- After (run 40835849792): results at 1366x768 inside the first screen; eval headline errors gone at every viewport;
  `test_v2_finder_guardrails_render`, `test_v2_finder_render`, `test_interactive_trades_release_render` pass.
- With PR #1094 (JEG-1219 saved-team picker) merged in (run 40835884597): results at 556, headline 472-515 at
  1366x768; `test_v2_finder_saved_team_render` 9/9 pass; guardrails render passes.
- Mutation guards: the collapse test now fails when the settings stay open after Find and when the summary line is
  missing (both caught in CI).

### Not this lane, reported
- `test_v2_finder_eval_render` still fails on the "ESPN mine, Yahoo theirs" scenario at every viewport: "meant to have
  natural groups, it has 0 of 1". Same on the pre-fix layout, so not layout. Fit rules are Codex's; not changed here.
- JEG-1184 bug: bench-backup "+" buttons start disabled on a fresh page because `el()` calls
  `setAttribute("disabled", false)`. Posted to JEG-1219 for its owner; tests here avoid relying on it.

### Claimed, not confirmed
- Jeremy has not chosen this behavior (settings hidden after Find). Exact-head PR CI, independent review, merge and
  live checks are pending. Nothing deployed.
