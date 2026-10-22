# JEG-799 B2: fidelity hold identity matching

Session implementing the B2 fix from docs/design/fidelity-all-hold.md.

## What changed

- `pipelines/fidelity_pulse.py`: `hold_decision` now accepts and writes
  `measured_site` (the live page's `snapshot_fetched_at`) into hold dicts.
  Both callers (`check_projection` and `check_source`) pass
  `site_meta(site_doc, source).get("snapshot_fetched_at")`.

- `pipelines/fidelity_hold.py`: `apply_fidelity_holds` compares
  `hold.get("measured_site")` against `_candidate_identity(target)` (the
  candidate section's `source_provenance.snapshot_fetched_at`). If they differ,
  the hold was measured on a different build and is skipped. Safe defaults:
  legacy holds (no `measured_site`) and candidates without provenance are held
  unconditionally.

- `tests/test_fidelity_hold.py`: 5 new tests in `HoldIdentitySkipsMismatch`.
  Negative-tested: old code holds all 7 sources (deadlock), new code holds 0.

- `pipelines/bake_players.py` (JEG-791): free-agent ppg divisor fix.
  `espn_has_team` now checks raw CSV team, not registry-resolved team.
  `games_remaining` uses the universe team's schedule (bye-aware); `ppg_divisor`
  uses window length for free agents (matching the DDF leg). These are separate
  values: games_remaining for display/Razzball, ppg_divisor for ESPN rates.

## PRs

- PR #756 (merged): Fidelity hold applies only to the measured build (JEG-799)
- PR #761 (merged): Fix free-agent ppg divisor: check raw CSV team, not
  registry-resolved (JEG-791)
- PR #762 (merged): Split games_remaining from ppg divisor for ESPN free agents
  (JEG-791)

## Verified

- `make validate` green locally (all tests pass) after each PR
- 55/55 tests in test_fidelity_hold.py pass
- Negative test confirms old code deadlocks, new code does not
- test_espn_ppg_basis.py: 4/4 pass (free agent ppg + games_remaining correct)
- test_games_remaining.py: 11/11 pass (both parity tests green)

## Chain status

First chain run after B2 (39712899686) failed: the published fidelity pulse
JSON (`dist/modules/fidelity-pulse.json`) was written before B2 and lacks
`measured_site` in the holds. Those are treated as legacy holds (applied
unconditionally). Dispatched a fidelity pulse run (39713304808) to regenerate
the holds with `measured_site`.

Second chain run (39714687832) after pulse update: B2 worked, all 7 holds are
amber (not blocking). Chain failed at a different gate:
`test_players_json_matches_leg_per_game` for Deuce Vaughn (0.162727 bake vs
0.15 leg). Root cause: PR #751's fix for `espn_has_team` used
`bool(team)` (registry-resolved) instead of `bool((espn_row["team"] or "").strip())`
(raw CSV team). Free agents with registry-resolved teams divided by team games
instead of window length. Fixed in PR #761.

Third chain run (39717026471) after PR #761: failed on
`test_players_json_games_match_window` for DAL free agents (Deuce Vaughn et al:
games_remaining=12 vs want=11). Root cause: the free-agent fix set both
games_remaining AND ppg divisor to window length, but games_remaining must match
the team's bye-aware schedule. Fixed in PR #762 by splitting games_remaining
(team schedule) from ppg_divisor (window length for free agents).

Fourth chain run (39718604445) dispatched after PR #762 merge. Result: GREEN.
nfl_week=7, outcome=green. All 7 sources held (fidelity holds, expected with B2
identity matching). Rebuild committed to main (b7862455), Pages deploy recorded
success. Week 7 is live.
