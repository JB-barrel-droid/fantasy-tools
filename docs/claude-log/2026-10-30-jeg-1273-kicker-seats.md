## 2026-10-30 - JEG-1273: count kicker and defense seats (PR #1145)

Contract: answer Codex's P2 finding on 2c0df74d. With two or three K or DEF seats (curve-widget allows up to 3), the list
checked only that a team had one, so a full roster with one kicker in a K=2 league showed "checks out". It now counts
against the seats.

### Verified (check named)
- Node check `.task-notes/cmsg_01NMFfXJm79Np7PbaxW4MsB88atSjPyoWQy27EAkDvUJFq/problems.cjs` (real ValueModel, roster
  provenance and finder modules) with K=2, every team at 17 of 17 and Team 7 holding one kicker and an extra WR:
  2c0df74d's league.js gives no items; this head gives "Team 7: 1 of 2 kickers.". At the default K=1 and DEF=1, every case's
  output is identical on both heads.
- `node --check app/v2/league.js`; `tests.test_league_problems_render` imports and skips without Chromium.

### Claimed, not confirmed
- The new two-kicker-seat render case passes in Chromium: CI render-tests runs it.
