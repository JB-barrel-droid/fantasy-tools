## 2026-10-29 - JEG-1258 review iteration: leak scan and capture coverage

Contract: address Codex's two coverage findings on PR #1115 (Linear comment 16:11Z): the player-name
scan sampled 5 names from 2 answers, and capture covered 5 console levels starting after import.

### Verified (check named)
- `--self-test` exits 0: correct log accepted, 21 mutations caught (new: late-listed name via warn,
  name via console.table, header value via raw stderr, event only as raw stdout).
- Plain run on main b8630697: exit 1, the same 5 recorded violations, md5 identical over 4 runs including
  one after `_render_env.ensure_built()` rebuilt dist.
- `python3 -m unittest tests.test_jeg_1061_logging_contract -v`: 2 OK.
- Scratch copy of main + hook-proposal.patch: full pass (exit 0), so collecting every player name gives no
  false positive against the proposed events.
- Scratch handler mutations: last-listed player name via console.warn, player name via console.table,
  client key via raw stderr write, event at module import: each exit 1. Earlier mutations rechecked
  (default/cache-hit/ip/misclassified: exit 1; limits 11 and 31: exit 2).

### Claimed, not confirmed
- Numeric `player_key` values in free text are not detected (stated as a limit in the README and harness).
