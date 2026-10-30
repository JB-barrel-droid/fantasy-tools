## 2026-10-28 - JEG-1134 phone context row collapses to one summary line

Contract: build option B of JEG-1134 on the JEG-1119 context row (#v2Context). Jeremy picked C on 2026-10-27
(measure, then A if the row is one line, B if taller). Below 768 px the row is now one line, a summary
("Full PPR · 12 teams · 4 sources") and the freshness chip; tapping the summary opens the roster line, Edit league,
Customize, the ⋯ menu and the "On the chart" line under it. Wider screens are unchanged. Jeremy's two decisions on
option A (2026-10-26) carry over: the "On the chart" line hides while closed, and the count leaves out DDF Value.
Supersedes PR #967 (built on the league bar JEG-1119 replaced).

### Verified (check named)
- The row is taller than one line below 1024 px on main: v2.css forces a break after the league and freshness
  (`.v2-context-inner::before`, flex-basis 100%) and puts the basis on its own line (`order: 10; flex: 1 1 100%`),
  so three lines; the 48 px one-line layout applies only from 1024 px. That decides B.
- `node --check app/v2/v2.js` passes; `pipelines/sync_dashboard_artifacts.py` builds.
- Static tests that read the shell pass locally (test_launch_copy_guard, test_launch_front_door,
  test_public_copy_no_vorp, test_v2_assist, test_v2_rescaled_copy); the render tests skip here (no local browser).

### Claimed, not confirmed
- tests/test_v2_phone_context_row_render.py passes in CI and its guard fails with the JEG-1134 CSS removed
  (CI run on the PR; it prints one JEG1134-MEASURE line per width with the row's height closed and open).
- The render tests that tap Edit league, Customize or ⋯ at phone width now open the row first through
  `_render_env.open_phone_context` (public copy, assist, customize cleanup, league live, optimize caption, panels,
  phone tap targets); test_v2_phone_header_render measures the summary line as the league summary below 768 px.
  No assertion changed. CI is the check.

### Picks (logged in docs/picks-log.md for reversal)
- Breakpoint 768 px (the site's phone breakpoint), not 1024 px; tablets keep the wrapped row.
- The freshness chip stays on the closed line beside the summary.
- Closed by default on every visit; the open state is not remembered.
- With no outside source shown the summary says "DDF Value only" instead of "0 sources".
