## 2026-10-29 - Share links keep the league setup, finder controls and both teams (JEG-1328)

Contract: slice 9 of `docs/specs/trade-page-parity.md`. The league link and the pair finder's search link carry the
route's discovery controls, both teams and TradeContext `common`; the league finder's selected trade is keyed by the
opponent's team id, not its name; older links still open. No number, default or ranking change. Compare's v2.js hash is
out of scope (it lands with the Trade screen work).

What changed:
- `app/v2/workspace.js`: `shareHash(ws, leagueQuery, {trade})` adds the league finder's controls (`size`, `hf`, `fit`,
  `opp`, `mcap`, `mch`, written only when they differ from today's defaults) and the selected trade. A reader's league
  gets new team ids, so the link names a team by its position in the link, as `wm` already does; `readShareExtras`
  turns positions into the new teams' ids. `tradePick` / `legacyTradePick` / `parseTradePick` are the pick's codec;
  `shareSettingsQuery` leaves only the league query and the value context (valuecontext, basis, ov) as the settings.
- `app/v2/league.js`: the address pick is `trade=1~<opponent id>~<give>~<receive>`; an old name-keyed address still
  selects its trade and is rewritten; `readShareHash` applies the link's controls and pick; Copy link carries the pick.
- `app/v2/finder.js`: the search link adds `viable=1` and the saved teams its rosters came from (`ws`, `mt`, `tt`). The
  teams are adopted only when the reader has that same saved league and each team in it, and only for the rosters that
  link put in (`linkTeamsFor`); elsewhere the rosters stay a working copy (TradeContext's rule for another workspace).
- `tests/node/share_link_context_check.cjs` + `tests/test_jeg1328_share_links.py` (in `make test-unit`).

### Verified (check named)
- Every field round-trips and an old-format link opens to the same view: `python3 -m unittest
  tests.test_jeg1328_share_links` (11 checks on app/v2; 8 mutations each caught by the named check).
- The checks fail without the change: `node tests/node/share_link_context_check.cjs <origin/main copies of the five
  files>` gave 11 of 11 failing.
- Existing link and league units still pass: `tests.test_v2_share_links`, `tests.test_v2_league_units`,
  `tests.test_jeg1229_trade_context`, `tests.test_jeg1213_import`, `tests.test_v2_finder_guardrails`.
- `make validate` (cloud): build and `make test-core` pass except `tests.test_week_history`, which errors on
  `ModuleNotFoundError: playwright` (no Playwright here; unrelated to this change). The 24 test-core steps after it,
  run one by one, all pass.

- Review follow-up (2026-10-30, on head ac87878 after the main merge): a link's saved teams no longer stick to a later
  state with other rosters; `finder_link_teams_label_only_the_link_rosters` plus a mutation that drops the roster check.
  12 checks, 9 mutations; the five link and league units pass; `make validate` as above (only `test_week_history` on
  Playwright), the 33 test-core steps after it all pass.

### Claimed, not confirmed
- In-browser behaviour (reading a link on the League page, the pair finder's saved-team picker showing the link's
  teams, the viable-only tick after a link) is read from source only. The render suites need Playwright Chromium,
  which cloud sessions cannot download; a browser check belongs on the Mac.
- Merge order: after JEG-1320 (slice 1), #1105 (workspace.js, league.js `readShareHash`) and #1123 (finder.js
  `applyHash`). This branch was built on main without those; its hunks avoid theirs (checked with `git diff` on each
  PR head), but each still needs a main merge here after they land. When slice 1's record is wired into the routes
  (slices 2 and 3), the league link's `size` and the pair link's controls should read and write that one record.
