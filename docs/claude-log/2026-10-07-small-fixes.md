# 2026-10-07 small fixes: GAP-FP-NAME-RESOLVE, GAP-022

Branch `fix/small-fixes` off origin/main `ae29f55`. Worktree `~/code/wt/small-fixes`.

## Changed

- `pipelines/build_ddf_two_tier_leg.py`: exact alias `"kenny gainwell": "kenneth gainwell"` added to the shared `ALIASES` map.
- `tests/test_save_espn_cbs_references.py`: `test_fantasypros_kenny_gainwell_resolves` (already in `make test-unit`).
- `docs/risk-register.md`: GAP-FP-NAME-RESOLVE and GAP-022 rows updated.
- No change to `curve-widget.js`: GAP-022 was already fixed on main.

## Verified (named checks)

- Supabase read-only `select player_key, full_name, position from players where full_name ilike '%gainwell%'`: one row, 785 "Kenneth Gainwell" RB.
- `test_fantasypros_kenny_gainwell_resolves` passes with the alias. With `build_ddf_two_tier_leg.py` stashed it FAILS. It also checks that "Kenny Gainwel" still resolves to nothing, so no fuzzy match.
- Other tests that use ALIASES pass: test_ddf_two_tier_leg, test_razzball_supabase, test_cbsros_section, test_save_espn_cbs_references, test_pull_fantasypros_parse.
- GAP-022: commit 87d1eb2 (2026-10-01) already re-appends `.lock-revert-notice` after `syncCurveStatus()` rewrites `#curve-status`. `tests.test_lock_revert_notice_render` runs in system Chrome: 2 tests pass, none skipped. With the two `activeNotices` lines deleted, the test fails with `TimeoutError` waiting for the visible notice. The row had been left Open by mistake.
- `make sync` exit 0 (build tv-20261007-2301-ae29f55). `CHROMIUM_PATH=... make validate` exit 0. Regenerated data JSON was reverted before commit.

## Claimed, not confirmed

- No live FantasyPros save was run after the change. "Next save reports 0 unresolved" is expected, not observed.
- I only searched for other unresolved Week 4/5 names in local outputs. `output/fantasypros-save-review/` and `ops/watchdog/pulls/` had no name-resolution failures. I found no USA Today unresolved list locally, so USA Today was not checked.

## Noticed, not fixed

- `tests/test_pull_fantasypros.py` fails to import (`No module named 'fantasypros'`) on clean origin/main. It is not in the Makefile.
- `make sync` printed `adj-view.json (status=bad)` on clean main data. This change did not cause it.
