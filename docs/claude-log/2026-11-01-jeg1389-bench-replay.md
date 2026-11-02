## 2026-11-01 - JEG-1389: replay the approved bench correction on the Mac

Contract: reproduce the `760a1cb9` standard-bench and switch findings in Standard,
Half PPR and PPR; restore approved behavior without new math; draft PR only.
Jeremy's ruling: "When a starter level player is on your bench, the market still
values them as a starter."

### Finding

The runtime correction already shipped in #1227 (`31e53bec`). No additional
value formula or runtime patch is needed. The remaining ticket description
incorrectly treats the standard-bench gap as unexplained. League import/share
settings were applied for the visit but not saved: reload returned to PPR,
2 WR, 7 bench. Independently, a switch update did not invalidate the drawn
player lines. #1227 saves imported settings, clears the switch's pairing cache,
and invalidates those lines.

This PR expands the two existing render tests to all three scorings, checks
all six reported players across reload, checks every team's displayed total
against its unrounded engine values, and checks the saved off state. It also
moves starter-level JSN from WR to ordinary BN while retaining ownership:
his standard price, market-level prices and source roles must stay identical.
IR/taxi behavior and the underlying bench allocation are unchanged.

### Verified (check named)

The two expanded JEG-1389 render modules were copied into an isolated checkout
of `760a1cb9` and run with `RENDER_TESTS_REQUIRED=1` using installed Playwright
Chromium 1243. **All six original regression cases fail** (reload and redraw
for each scoring). The six-player reload output exactly matches the ticket's
reported live numbers (Hockenson 4.1, within its reported range).

Then only the exact `app/v2/v2.js` and `app/v2/league.js` patch from #1227 was
applied to that same checkout. Its fixtures, engine, both Python references
and lineup config remained byte-identical to `760a1cb9`. Both modules pass
all three scorings, including the new totals checks. The slot-ruling assertion
was added afterward and is checked on the current branch.

Reproduction commands (the historical checkout was already built from its own
fixtures, so `_render_env._built = True` prevents a redundant build):

```sh
RENDER_TESTS_REQUIRED=1 .venv/bin/python -m unittest \
  tests.test_jeg1389_link_settings_reload_render \
  tests.test_jeg1389_switch_redraw_render
git diff 31e53bec^ 31e53bec -- app/v2/v2.js app/v2/league.js > /tmp/jeg1389-fix.patch
git apply /tmp/jeg1389-fix.patch
```

**Same-input before/after, DDF Value at standard bench.** 2026 snapshot at
`760a1cb9`, 12 teams, QB1/RB2/WR3/TE1/FLEX1/BN5 requested by the link. CBS
explicitly visible through the harness; the ordinary render fixture holds CBS.
Each cell is **before reload correction → after correction**. Before, all
three reloads incorrectly use default PPR/WR2/BN7. After, link and reload agree.

| Scoring requested | JSN | Kyren Williams | Josh Allen | Aaron Jones | Dallas Goedert | T.J. Hockenson |
| -- | -- | -- | -- | -- | -- | -- |
| Standard | 67.0 → 66.6 | 45.9 → 58.2 | 31.2 → 34.8 | 4.9 → 10.3 | 3.7 → 2.2 | 4.1 → 1.5 |
| Half PPR | 67.0 → 69.6 | 45.9 → 55.8 | 31.2 → 33.0 | 4.9 → 9.1 | 3.7 → 2.6 | 4.1 → 2.4 |
| PPR | 67.0 → 76.2 | 45.9 → 49.6 | 31.2 → 31.7 | 4.9 → 6.4 | 3.7 → 1.4 | 4.1 → 1.9 |

**Why those restored Half PPR numbers differ slightly from approval:** approval
used inputs frozen at `9614452c`, not the refreshed `760a1cb9` inputs. The
current JS engine and independent spec reference, with that frozen fixture
and its original hard-seat rule (`seat_sigma: 0`), both reproduce all six
approved numbers exactly:

| Player | Approved | Replayed JS | Replayed spec |
| -- | -- | -- | -- |
| JSN | 69.4 | 69.4 | 69.4 |
| Kyren Williams | 55.9 | 55.9 | 55.9 |
| Josh Allen | 33.9 | 33.9 | 33.9 |
| Aaron Jones | 9.7 | 9.7 | 9.7 |
| Dallas Goedert | 2.6 | 2.6 | 2.6 |
| T.J. Hockenson | 2.3 | 2.3 | 2.3 |

That fixture contains Half PPR natives only; merely changing its `scoring`
field does not turn it into another scoring's data. The three-scoring render
cases above actually select the scoring-specific source inputs.

Current main also includes #1242's fractional-seat change (`dcf7b4cc`). It
prices the frozen fixture differently with its new default sigma (e.g. JSN
71.7, Kyren 53.7), while sigma 0 reproduces the approved historical table.
This PR preserves that subsequent change. Forcing today's values to equal a
historical input/sigma snapshot would be a different task and require Jeremy's
decision; it is not a correction to the reload bug.

Focused reference checks: `tests.test_league_levels_real.TestRealLeagues.test_no_league_baseline_unchanged`
and `.test_js_matches_spec_reference` pass (2 tests); the former checks every
player and allocation in both frozen league fixtures at sigma 0.

On branch base `76f3a46f`, the expanded render modules pass (2 tests, three
scoring subcases each, including the slot ruling). With CBS explicitly visible,
the same-input link/reload values are:

| Scoring | JSN | Kyren | Allen | Jones | Goedert | Hockenson |
| -- | -- | -- | -- | -- | -- | -- |
| Standard | 67.0 | 56.8 | 35.0 | 9.8 | 2.4 | 1.9 |
| Half PPR | 71.2 | 52.6 | 33.2 | 8.3 | 3.0 | 2.6 |
| PPR | 76.0 | 48.4 | 31.8 | 5.6 | 2.8 | 3.2 |

All 12 teams' displayed totals equal the engine sum at both switch states and
remain equal across reload. No current value is changed by this PR.

### Claimed, not confirmed

No fresh production QA was performed. Jeremy's actual browser storage and
historical source holds were not inspected. The local historical replay
matches the reported numbers with CBS explicitly visible.

`make validate` was already running in another Mac session at intake, so this
lane uses the requested focused/render checks and relies on CI for the full
gate. No engine/config/reference change is proposed; a new value-check,
rank-guard or 12-combo math sweep is not warranted for this tests-only delta.
F1 is not applicable: no Cyrus runtime workflow or F1 harness changes.

Next turn: existing coordinator reads exact-head CI and obtains independent
Claude review of the draft. JEG-1389 stays In Progress while work remains.
No merge, deploy, Supabase access, credentials access or HANDOFF.md edit.
