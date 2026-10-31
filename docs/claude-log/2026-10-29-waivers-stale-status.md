## 2026-10-29 - Waivers: hide a stale Sleeper injury status (JEG-1312, part of JEG-1238)

Contract: the Waivers tab must not show an old Sleeper injury status as current. The page now ships the date of
the status it carries, and the tab hides every status past 6 days (or with no date) and says when the copy is from.
No values change.

What changed:
- `pipelines/build_v2_page.py` `player_status_js()` writes `dist/v2/player-status.js`
  (`window.TradeValueStatus = {source, as_of}`), with `as_of` taken from players.json
  `meta.universe.nfl_active.identity_base_pulled_at`: the base the bake read, so the date of the status the rows carry.
  It is loaded before `waivers.js`.
- `app/v2/waivers.js`: `statusFreshness()` (shown when dated and at most `STATUS_MAX_AGE_DAYS` = 6 days old; the
  refresh runs Tue + Thu, so a healthy copy is at most 5 days old), `statusOf()`, and `injuryNote()` now take the
  freshness. A stale or undated copy gives no status tag, no "Your X is Out" line, and the candidates card says
  "Injury status is not shown: the latest Sleeper status is from Oct 9, 20 days old." A fresh one says
  "Injury status: Sleeper, as of <day>." and each tag carries "Sleeper status as of <day>" on hover.
- `Makefile`: `tests.test_waivers_status` added to test-core and test-core-shard-3.

### Verified (check named)
- `python3 -m unittest tests.test_waivers_status`: 5 tests pass. The rules checked: fresh, stale (20 days), exactly
  6 days, 6 days plus a minute, no file, no date, a bad date; `statusOf` per row; the reason text on the
  `waiver-thin-rb` fixture with Rex RunOne Out (fresh shows the note, stale and missing context do not);
  `player_status_js` reads the field and gives null when it is missing.
- Failing before: main's `waivers.js` on the same fixture puts "Your Rex RunOne is Out" in all three RB candidates'
  reasons with no date check (scratch run of the EVALUATE body against `git show origin/main:app/v2/waivers.js`).
- Discrimination: `test_checks_fail_on_broken_builds` breaks the age limit, the note's check, the row's check and the
  undated case one at a time; each is caught.
- `tests.test_waivers_math`, `tests.test_waivers_views`, `tests.test_build_v2_page`, `tests.test_validate_shards` pass.
- `make validate`: see the PR description for the result on the pushed head.

### Claimed, not confirmed
- The rendered tab: no browser here (cloud sessions cannot install Playwright Chromium), so the status line and the
  absence of tags were not seen in a render. The waivers render suites in CI cover the tab loading.
- Live: not checked; the proxy refuses github.io from this session.
- The 6-day limit and the wording are my defaults, put to Jeremy on JEG-1312.
