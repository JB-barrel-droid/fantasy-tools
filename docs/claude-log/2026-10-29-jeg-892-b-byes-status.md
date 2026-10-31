## 2026-10-29 - Bye week and injury status on player rows, path B (JEG-892)

Contract: the second of two draft paths built on Jeremy's instruction (Oct 29: "If we need a decision but there are
only two real Paths, do the work for both, and then we'll decide after"). Path B is path A (claude/JEG-892-a, see
2026-10-29-jeg-892-a-byes.md) plus a Sleeper injury status chip (Q, D, Out, IR, PUP, Susp) on the same rows. No
filter, no value changes.

What changed beyond path A:
- `app/v2/player-flags.js`: `statusChip` and a chip in `node`. The status is the one the page already ships
  (players.json `injury_status`, dated by `window.TradeValueStatus`), under the Waivers tab's own rule
  (`TradeValueWaivers.statusFreshness` / `statusOf`, JEG-1312): shown only when dated and at most 6 days old, only for
  a player on an NFL team, with "<status>: Sleeper status as of <day>" on hover. A stale or undated copy shows no chip
  and the bye's hover says why ("Injury status is not shown: the latest Sleeper status is from Oct 9, 20 days old.").
- `app/v2/v2.css`: `.v2-inj-chip`, the Waivers tag's look.

### Verified (check named)
- `python3 -m unittest tests.test_player_flags`: 10 tests pass (path A's 7 plus fresh copy, stale and undated copy,
  and no Waivers rule loaded).
- Discrimination: `test_checks_fail_on_broken_copies` also breaks the staleness rule, the team-only rule, the hover
  date and the stale explanation one at a time; each is caught.
- `tests.test_waivers_status`, `tests.test_validate_shards` pass.

### Claimed, not confirmed
- Today the shipped status copy is from Oct 9 (the Sleeper refresh fails, JEG-1238), so on the live data B shows no
  chips, only the bye and the hover note. Chips appear once that refresh recovers (JEG-1238 / JEG-1315).
- Browser rendering: CI v2-render only (no Playwright Chromium in cloud sessions).
