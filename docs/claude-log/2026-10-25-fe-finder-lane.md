## 2026-10-25 - FE finder lane (parent JEG-1093)

Contract: Find a trade front-end fixes from Jeremy's Mac review: JEG-1103, JEG-1094, JEG-1095, JEG-1098, JEG-1099.

### JEG-1103 Risers and Fallers duplicate DDF
Cause: the Risers picker passed every series in `TradeValueMovers.SERIES` to `renderSeriesPicker`, including `ddf_value_charts`, which is the same series as `ddf_value` (`sameAs`, JEG-1073) and carries the same label "DDF Value". Other pickers already hide it via `ddfPickKey`. Fix: Risers picker filters to pickable keys.
#### Verified (check named)
- `tests.test_v2_risers_render` passes; `check_picker` now asserts unique option labels; new mutation "duplicate DDF option in Risers picker" (filter removed) is caught by the checks (negative test).
#### Claimed, not confirmed
- Live site not reproduced; cause found from code.

### JEG-1094 two screens
Find a trade is now two routes: `#find-trade` (tab "Find a trade: your team", the one-roster finder) and `#find-league` (tab "Find a trade: league-wide", league, team summary and opportunities cards in a new `main#v2FindLeague`). Names are provisional (PMM pass is a separate ticket). The assessment table lives only in finder.js and is untouched (league uses the same finder code for fit and impact). Old `#find-trade?workspace=` league share links are rewritten to `#find-league?workspace=` in `canonicalizeHash`; plain `#find-trade` still lands on the one-team screen.
#### Verified (check named)
- `tests.test_v2_find_split_render` (new): each route shows only its own cards, own tab, own empty state, old share link moves; two mutations (both screens shown; league cards mounted on the team page) are caught.
- `tests.test_v2_polish_render` (new route assertions), `tests.test_v2_modules_render` (league cards on `#find-league`) pass.
#### Claimed, not confirmed
- League render suites re-pointed at `#find-league` (`tests/_league_render.py`); see end of entry for their run.
