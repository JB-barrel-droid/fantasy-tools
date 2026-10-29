## 2026-10-29 - Connector trade rows show both sides; the league link keeps every team (JEG-1329)

Contract: slice 10 of `docs/specs/trade-page-parity.md`. `find_trades` and `find_trades_league` rows carry the other
team's side (Trade chart average net, starters change) and both teams' roster construction, from the finder's own
`tradeFit`; the league scan's site link opens `#find-league` with every team. No value math, default or ranking change.
Stacked on #1119 (`be/jeg-1179-superflex-link`); #1124 and #1156 carry the same `slimOffer` and league handler.

### Verified (check named)
- `tests/node/connector_both_sides_check.mjs` (run by `tests/test_mcp_remote.py`): each row's `theirs.marketNet`,
  `theirs.starters` and both `constructionOk` flags equal `finder.tradeFit` on the same trade, for `find_trades`,
  league candidates and the package; the text shows their starters change; the league link is read back by
  `workspace.js` `decodeShare` with every team in order (yours first, `wm=0`, a team with no matched players
  included, a 5-digit key included), with scoring and team count; `leagueShareText` equals `encodeShare`.
- The check fails without the change: with `tools.ts` and `fit.ts` reverted, "find_trades #1: both sides present";
  with the `teams` argument removed, "league link opens the league finder" (the link was `#find-trade?mine=...`).
- `python3 -m unittest tests.test_mcp_remote tests.test_mcp_week tests.test_mcp_finder_loader` green (11 tests),
  including the JEG-1123 reply size budgets; `tests/node/mcp_superflex_link_check.mjs` ok.
- Reply size on the `mcp_remote_check.mjs` size fixture (rows shown under the unchanged budgets, before -> after):
  `find_trades` default 5 -> 4, limit 50 27 -> 22; `find_trades_league` default 4 -> 2, limit 100 11 -> 6. The
  league link grows from 146 to 875 characters on that fixture (12 teams of 15).

### Claimed, not confirmed
- The live site opens the connector's `#find-league` link and offers to load every team (same format the page's
  own share button writes; not opened in a browser here).
- Not deployed: the mcp function deploy needs Jeremy's yes.
