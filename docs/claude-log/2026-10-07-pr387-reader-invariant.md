## 2026-10-07 — Claude (helper session): PR #387 reader invariant red after the Week 5 merge

Contract: `make validate` was red on merge commit 177cdb7 (origin/main 0b0ddee merged into
published-views-every-setting): `test_published_views_engine.test_reader_invariants`
`AssertionError: 6 not less than 5 : fantasycalc half_ppr/10/bench8-flex2-rb3`. Decide whether this
is an engine defect or a brittle assertion, fix, validate, sweep, and push.

### Verified (check named)
- **The 6 players.** All are FantasyCalc, half_ppr / 10 teams / RB3 FLEX2 BENCH8. Values come from the
  fixture at 0b0ddee. I recomputed them in a scratch script with `unified.translate_ranked` (the Indexed
  engine's own maxes) and the node driver.

  | player | pos | native | waiver line | value above waivers (native) | unrounded Indexed | Indexed | VORP view | Adjusted |
  |---|---|---|---|---|---|---|---|---|
  | Caleb Douglas | WR | 27 | 18 | 9 | 0.045 | 0.0 | 0.053 | 0.108 |
  | Antonio Williams | WR | 25 | 18 | 7 | 0.035 | 0.0 | 0.041 | 0.084 |
  | Mack Hollins | WR | 24 | 18 | 6 | 0.030 | 0.0 | 0.035 | 0.072 |
  | Tre Harris | WR | 23 | 18 | 5 | 0.025 | 0.0 | 0.029 | 0.060 |
  | De'Zhaun Stribling | WR | 19 | 18 | 1 | 0.005 | 0.0 | 0.006 | 0.012 |
  | George Holani | RB | 7 | 1 | 6 | 0.042 | 0.0 | 0.035 | 0.128 |

  All 6 are strictly above the setting's waiver line. Indexed shows 0 only because
  `translated = round(vorp * scale, 1)`, and FantasyCalc's native scale (thousands) makes
  `scale` about 0.005 (WR) or 0.007 (RB). That is the exception the test's own comment already
  allows: "a player just above the line whose Indexed value rounds to 0.0". It is not an engine
  defect. The count of such players grows with any publisher whose scale is large and whose tail is
  thick, so `< 5` was fitted to Week 4 data. The other 11 charts in the test have 0 such players,
  except FantasyCalc standard/14/qb2-te2, which has 1 (Holani again).
- **Why the old assertion was wrong.** It used a count as a stand-in for "only rounding explains the
  difference". The count failed on legitimate data (this run). It also passed a real leak: a mutation
  that gives the first sub-waiver player at each position a sliver of value in the views (4 players
  per chart) failed the old zero checks on only 1 of 12 charts, and that one only because of this
  week's 6 boundary players. With Week 4 data it would have failed on 0 of 12. Not a test adjusted to
  go green: the replacement is strictly stronger.
- **Replacement** (tests/test_published_views_engine.py): `zero_set_failures()` +
  `rounding_band_violations()`. Every player who is 0 in Indexed but non-zero in the views must meet
  both conditions:
  - the server's own translation, at that setting and on the Indexed engine's own positional maxes
    (driver `ourMax`), prices them strictly above the waiver line;
  - their unrounded Indexed value is in (0, 0.05), half of the 0.1 display precision.

  The unrounded value is read from `translate_ranked` with the maxes scaled by 1e6. The other zero
  checks are unchanged: VORP zero set == Adjusted zero set, views zero set is a subset of Indexed's,
  and at least one player is 0.
- **Negative test** (`test_zero_set_guard_catches_waiver_leaks`). It first checks the guard is green
  on the real engine, then on three mutated engines:
  - leak-first-below-waiver: 24 failures
  - views-waiver-deeper (the views use a waiver line one bench slot deeper): 31 failures
  - indexed-drops-small (Indexed zeroes above-waiver values under 1.0): 95 failures

  The failure messages show the band check is the one that fires (for example "at/below the waiver
  line but priced in the views" and "unrounded Indexed value is 0.593220").
- **Second red, from main** (tests/test_static_export.py
  `test_known_full_ppr_12_team_source_values`: `25.5 != 25.3`). It fails identically on a clean
  origin/main 0b0ddee checkout. FantasyCalc refetched 2026-10-06: Josh Allen's native moved
  6331 -> 5949, he is still that chart's 25.0 top QB, and the fixture's fantasycalc_adjusted
  full_12_qb1 value moved 25.5 (0b0ddee^) -> 25.3 (0b0ddee). This is a stale data pin, updated with
  a dated comment in the file's existing style. Risk row GAP-MAIN-WK5-PIN: main stays red until this
  merges or main gets its own fix.
- `make validate` exit 0 on the worktree (Python 3.12 via ~/code/py312; CHROMIUM_PATH = Google
  Chrome).
- **12-combo headless sweep.** Playwright with Google Chrome, serving the built dist/ from
  `make validate`'s sync (build tv-20261007-1005-177cdb7). It was compared with origin/main 0b0ddee
  built by `make sync` in a scratch worktree (tv-20261007-1502-0b0ddee). 0 page errors on both.

  | scoring | teams | fixedPieIndexed PR / main | sourceScaleAgreement PR / main |
  |---|---|---|---|
  | standard | 8, 10, 12, 14 | true / true | false / false |
  | half_ppr | 8, 10, 12, 14 | true / true | false / false |
  | ppr | 8, 10, 12, 14 | true / true | false / false |

  The scale-agreement offenders are identical in all 12 combos. `sourcePeaks` are identical except
  the FantasyCalc Adjusted peak at 8 and 10 teams, which is 0.00 to 0.034 lower on the PR (for
  example ppr/8 61.170 vs 61.204). This session changed tests and docs only, so that difference
  belongs to PR #387's engine, not to this change.
- Generated build outputs from `make validate`'s sync (dist/, app/ assets) are not committed. main
  ships the same stale committed dist/assets, and the deploy runs `make sync` itself.

### Claimed, not confirmed
- The 0.034 FantasyCalc Adjusted peak shift at 8 and 10 teams is assumed to come from the PR's
  below-waiver = 0 change (league-settings-001/3) feeding the adjustment refit. Not traced.
- The rebuild run 37641559947 failed at "Build consolidation layer" (null player_key; risk row
  GAP-CONSOL-PLAYERKEY-NULL). Seen in the run log only, not investigated.
