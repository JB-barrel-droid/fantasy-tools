## 2026-10-29 - JEG-1273 review fixes on PR #1145

Contract: apply the independent review's findings on #1145 (head 679a5d2d): no teamless extra line when a team's unmatched
count wasn't recorded or a team holds only a kicker and a defense; "add it", not "add him"; the render test asserts each
case's whole list. Took the branch over from the Mac owner (sessions archived 20:52 UTC) and merged #1105's head 3418629 in
normally.

### Verified (check named)
- Node check `.task-notes/cmsg_01NMFfXJm79Np7PbaxW4MsB88atSjPyoWQy27EAkDvUJFq/problems.cjs` (real ValueModel, roster
  provenance and finder modules; the render test's cases), on 679a5d2d's league.js: "count not recorded" shows the Team 9
  line plus a teamless "Some pasted players are not matched to a team yet."; "kickers and defenses only" shows the Team 4
  line plus a teamless "A team has no players.". On this head: each shows only its team's line; every other case unchanged.
- `node --check app/v2/league.js`; `tests.test_league_problems_render` imports and skips without Chromium.
- `make test-core`: every module up to `tests.test_week_history` passed; that one needs Playwright, which this cloud
  machine lacks, and make stops there.

### Claimed, not confirmed
- `RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_league_problems_render` in Chromium (fails on the test commit
  alone, passes with the fix): to be run by the render sweep in CI or on the Mac.
