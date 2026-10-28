## 2026-10-28 - Render sweep shard 1: targets combos, finder chips, league panel

Contract: diagnose three render-sweep failures on main and fix them as local commits on `fix/sweep-shard1-b`
(no push, no PR). Chromium cannot run in this environment, so every finding below is from code and history.

### Changed

- `tests/test_v2_targets_combos_render.py`: the sub-line check required "<count> of ". JEG-977 (57f1c1b2) removed the
  "N of M players" count by Jeremy's brief; the sub-line reads "<count> players · ranked by ...". The check now requires
  "<count> players · ". It still ties the count to the engine list, so a stale list is still caught.
- `tests/test_v2_finder_chips_render.py`: the week's data has no player without a DDF Value, so the test now makes one
  (wraps `getAllRows` to null one mid-ranked player's DDF Value, data only) and checks its chip reads "no value".
- `tests/test_v2_league_oppanel_render.py`: Close and viability are reported as separate failures. The viability rule
  is unchanged.

### Verified (check named)

- Sub-line and engine count come from the same list: `app/v2/v2.js` renderTargets writes `${list.length} players`
  with `list = targetsView[side]`, and the test's count is `TradeValueV2.targets()[side].length` (read in code).
- "N of M players" is forbidden on the page: `tests/test_v2_consistency_render.py` line 43 (read in code).
- League panel has a Close button: `app/v2/league.js` oppPanel builds `button("Close", {id: "v2LgOppPanelClose"})`.
- The JEG-1108 panel viability display never reached main: `git show e696bf25:app/v2/league.js` and current main both
  carry the placeholder "Checks that this trade is workable ... not shown here yet."; `git log --all -S viabilityText`
  finds the name only in e696bf25's message; `origin/be/jeg-viability-rework` does not touch league.js.
- The three files compile (`python3 -m py_compile`).

### Claimed, not confirmed

- The three render tests pass or fail as described: not run (no Chromium here). The sweep in CI must confirm.
- `test_v2_league_oppanel_render` stays red until the viability lane (JEG-1129) puts the fit and viability in the panel.
