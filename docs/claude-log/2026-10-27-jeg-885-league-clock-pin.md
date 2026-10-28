## 2026-10-27 - JEG-885 takeover: league render tests pin the clock; top-10 guard reports instead of timing out

Contract: bring PR #968 (JEG-885, at most 2 rows per received player, the rest folded) up to date with main and show its render test green, so it can merge. Session `session:cma`, branch `cma/JEG-885` (continues `banana/jeg-885-cap-per-core`).

Changed (tests only):
- `tests/_league_render.py` `open_page` adds `_render_env.pin_data_week_script()` to every league render page. Without it, from the Tuesday week flip until the new week's charts land, the page excludes every chart and the opportunities table never renders (the JEG-1152 pin, missing from this helper). On 2026-10-27 every league render test using the helper failed on clean main for this reason.
- `tests/test_v2_league_top10_render.py` `check()` records a missing "Show 10 more" or "Show all" button as a failure and returns, instead of a 30 s `Page.focus` timeout. The "opens on 20" mutation crashed the guard rather than being reported. No assertion was loosened: every condition that failed before still fails.

### Verified (check named)
- `pytest tests/test_v2_league_top10_render.py` with Chromium: 5 passed and 8 subtests (top 10 and expand, the 3 main guards, the JEG-885 core-cap test and its guards). Before the pin: 5 failed, opportunities table empty.
- Clean origin/main plus the pin only: `test_guard_fails_on_broken_builds` "opens on 20" fails with the same `Page.focus` timeout, so the guard fix addresses a defect already on main.
- `pytest tests/test_v2_contract_render.py`: 6 passed (builder run on the merged head, before these test-only edits).
- `pytest tests/test_v2_league_units.py`: passed.

### Claimed, not confirmed
- `tests/test_v2_league_oppanel_render.py` fails ("viability slot or Close missing") on clean main with the pin too. It is not touched here and needs its own ticket.
- Zero-value throw-in duplicates collapse only through the 2-per-player cap. No separate dedupe exists (builder's read of the diff).
