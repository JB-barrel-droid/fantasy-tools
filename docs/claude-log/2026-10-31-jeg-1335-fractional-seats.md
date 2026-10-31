## 2026-10-31 - Fractional flex and bench seats in the engine (JEG-1335)

Contract: build option A of the JEG-1333 before/after (Jeremy, 2026-10-30 23:41 UTC, "Letter A."): fractional flex everywhere, fractional bench only when no league is loaded, sigma 0.75 PPG (JEG-1286 "Go with B"). Value math change: needs his yes by PR number before merge, and a separate yes to deploy get-values and mcp.

### What changed
- `pipelines/value_reference.py`: `allocation_mix` (seat shares from `lib/fractional_seats.py`, JEG-1334), `allocate` takes fixed flex and bench counts, `run_pipeline` runs once per whole allocation and blends (`blend_values`, `_blend_runs`). New output fields `allocation_mix` and `allocation_expected`; `allocation`, `slot_fill` and the fill sets are the heaviest allocation's. `League.seat_sigma` (None = 0.75, 0 = the hard rule).
- `pipelines/spec_reference/value_pipeline.py`: the same, written against the spec (`Setting.seat_sigma`, `allocation_mix`, `blend`, `assign_tiers`, `default_ranking`).
- `app/trade-value-chart/assets/value-model.js`: its own copy of the seat functions (the page, the edge functions and the headless check load only this file), `vpAllocationMix`, the per-allocation run and `vpBlendRuns`. `setting.seat_sigma`. `ValueModel.seatFunctions` exposes the copy for its parity test.
- `pipelines/lib/roster_convention.py`: `vorp_bench_discount` split out of `vorp_bench_allocate` (same numbers) so the soft bench uses the same discount.
- `docs/methodology.md` VP-2.2 g, `docs/decisions.md` JEG-1286 entry.

### Tests
- New `tests/test_fractional_seats_stability.py` (test-core, shard 2): for the 12 settings plus USO and Charlotte, each fringe flex and bench player's first projection source moved by -1 and +1 PPG with the allocation free; no other player moves more than 1.0 DDF Value. Passes (worst 0.59, standard/14). Its mutation test runs the hard rule (sigma 0) on Charlotte and requires the bound to break (3.76). On main the test errors (no `SEAT_SIGMA`); the hard-rule numbers per setting, measured with the same script: 13 of 14 settings over 1.0 (Charlotte 3.76, half PPR/8 2.72, USO 2.43; only standard/8 under, 0.39).
- New `tests/test_fractional_seats_engine.py` (test-unit-modules): the engine's seat copy equals the Python helper on 200 random leagues (soft select and decomposition to 1e-12, the whole mix weights to 1e-12 and counts exact). A mutated bench sigma in the engine turns it red.
- New `tests/test_fractional_seats_worked_example.py` and `tools/worked_example_fractional_seats.py`: the worked example's `variant_fractional_seats` block, reproduced by the reference, the spec reference and the engine.
- Changed because the rule changed (Jeremy's answer), not to go green: the worked example fixture now says `seat_sigma: 0`, so its hand-checked hard-rule numbers stand; the test league builders pass `seat_sigma` through; `tests/test_fractional_seats.py` captures the allocate calls at sigma 0; `tests/test_league_levels_real.py` checks its frozen pre-JEG-1188 baseline and pinned counts at sigma 0 (its engine-vs-spec parity and invariants run at the default); `tests/test_waiver_band_line.py` holds the whole seat mix (weights included) when it holds the slots, and counts only a change of whole allocations as a slot flip.
- Found by the league-levels sweep and fixed in all three: after blending, a source position's estimated count and `extended` flag come from the blended estimates (the union over allocations), not the heaviest allocation.
- 41 suites that touch the pipeline, run on this branch and on main: same results except `test_league_levels_real` (fixed above). The rest that fail, fail identically on main because the session has no Chromium.
- Engine against the Python reference on live inputs, 30 settings (grid with and without superflex, USO and Charlotte with no league, loaded and market): largest value difference 1e-13, allocations and tiers identical.
- Python reference against the approved JEG-1333 prototype numbers (half PPR, USO and Charlotte, loaded and no league): identical, so the JEG-1333 before/after (`/mnt/project-files/ddf/jeg1333-fractional-flex-before-after.md`) is the before/after of this build.

### Claimed, not confirmed
- value_check compare, the rank guard, the 12-combo sweep, make validate and `make values-explainer MARK_REVIEWED=1` need Chromium, which the cloud session can't download; they run in CI or on the Mac.
- Engine run time per setting goes from about 0.06 s to about 0.35 s (one run per allocation, 3 to 12 allocations). Not measured on the page or the edge functions.
- `tests/test_basis_overrides.py` fails 20 tests on main as well (it runs in no make target); not this change's.
