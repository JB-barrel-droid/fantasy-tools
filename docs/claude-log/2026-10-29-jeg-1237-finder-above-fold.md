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

### Update 22:40 UTC (takeover)
- Jeremy picked A (fold after Find, one "Trade settings" line in the summary), Oct 29 12:01 UTC; this is the layout
  here. Settings also fold on phones (there is no desktop-only condition); the PR text said otherwise and is corrected.
- Took over the idle branch (last push 08:08 UTC) and merged `origin/main` c03eb05 in normally: no conflicts. The
  JEG-1219 backup-button fix and saved-team picker are now on main, so they come in with the merge.
- Verified: `node --check app/v2/finder.js`; `make validate` on the merged head (result in the PR thread).

### Claimed, not confirmed
- Collapse/eval render tests on the merged head: they are not in the v2-render workflow and there is no local
  Chromium here, so they need the Mac (command on JEG-1237). Delta review of the main merge, merge and live checks are
  pending. Nothing deployed.
- The eval "ESPN mine, Yahoo theirs" natural-group failure is data or fixture drift, separate from this layout fix,
  and the Natural rule itself is being changed under JEG-1324; tracked as its own follow-up ticket.
