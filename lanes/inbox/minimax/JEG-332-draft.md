# JEG-332 — repo-side draft: on-demand VORP view port

**Lane:** MiniMax M3 (worker lane; no merge/push/deploy authority)
**Branch:** `minimax/jeg-332-vorp-view`
**Date:** 2026-10-04

## Files changed

| Path                                                  | Kind                          |
| ----------------------------------------------------- | ----------------------------- |
| `sql/migrations/007_vorp_on_demand_views.sql`         | new — versioned migration     |
| `tests/test_vorp_view_baseline_match.py`              | new — hermetic regression     |
| `docs/vorp-on-demand-port-notes.md`                   | new — port record + NEEDS-REVIEW |
| `lanes/inbox/minimax/JEG-332-draft.md`                | this report                    |

No files outside the four listed above were touched.

---

## Port map (formula → Python source lines)

| # | SQL step in `public.compute_vorp_views`                                | Python source                                                              |
| - | ----------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| 1 | bench_share validation in `[0.01, 0.30]`, default 0.15                 | `pipelines/build_reweighted_values.py:45` (`DISPLAY_MAX=70.0`) + module docstring on 15% bench default (`pipelines/build_reweighted_values.py:1-13`) |
| 2 | scoring whitelist `{standard,half_ppr,ppr}`                             | `pipelines/build_imputed_vorps.py:58-59` `RosterConfig.__post_init__`      |
| 3 | `teams > 0`                                                             | `pipelines/build_imputed_vorps.py:56-57`                                   |
| 4 | roster_shape keys `{QB,RB,WR,TE,FLEX,BENCH}` as nonnegative ints       | `app/trade-value-chart/assets/curve-widget.js:84` `DEFAULT_ROSTER` + `docs/contract/fe-read-contract-v1.md:362` |
| 5 | duplicate canonical key detection                                       | `pipelines/build_imputed_vorps.py:64-96` `_canonical_number` and `:114-119` `_validate_values` duplicate-alias guard |
| 6 | position ∈ `{QB,RB,WR,TE}`                                              | `pipelines/build_imputed_vorps.py:33,120-122`                              |
| 7 | ties broken by ascending numeric player_key                            | `pipelines/build_imputed_vorps.py:157` `infer_roster` sort key             |
| 8 | dedicated → flex (RB/WR/TE) → bench → cut                              | `pipelines/build_imputed_vorps.py:142-177` `infer_roster`                 |
| 9 | flex pool limited to FLEX_ELIGIBLE (no QB)                              | `pipelines/build_imputed_vorps.py:33,166`                                  |
| 10 | group totals `sum_surplus[pos, role]`                                  | `pipelines/build_imputed_vorps.py:200-208` group sum                       |
| 11 | per-role effective target = position_total × role_share                | `pipelines/build_reweighted_values.py:78-97` `linear_reweight`             |
| 12 | bench share split `(1-bench_share)` / `bench_share`                    | `pipelines/build_reweighted_values.py:119-141` `constrain_group_budgets` `wanted` bench fraction |
| 13 | proportional reweight within role                                      | `pipelines/build_imputed_vorps.py:218-227` final block                     |
| 14 | `vorp[k] = imputed_vorp[k]`                                            | `pipelines/build_reweighted_values.py:216-218` `build_three_views`         |
| 15 | `adj_values[k] = imputed_vorp[k] * 70 / peak`                          | `pipelines/build_reweighted_values.py:164-178` `apply_70_anchor`           |
| 16 | `vorp_indexed[k] = native[k] * 70 / peak_native`                       | `pipelines/preview_vorp_views.py:211-222` `display_indexed = nv * DISPLAY_MAX / peak` |

Detailed in `docs/vorp-on-demand-port-notes.md` §2.

---

## NEEDS-REVIEW list

* **4 named roster shapes.** Per `docs/contract/fe-read-contract-v1.md:84`
  there are 4 shapes: default 1QB, default SUPERFLEX, custom-A,
  custom-B. Only **default 1QB** has a repo-pinned definition
  (`{"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"BENCH":6}`,
  `curve-widget.js:84`, `fe-read-contract-v1.md:362`). The other three
  are NEEDS-REVIEW:
  - `default_SUPERFLEX`: the widget toggles `shape.SUPERFLEX`
    (`curve-widget.js:878`) and adds QB to flex-eligible, but the slot
    counts are not pinned.
  - `custom_A`, `custom_B`: no definition exists in this repo or in
    the contract doc.
  The SQL function takes shape as a validated jsonb parameter and
  never defaults it; callers passing an unknown shape get a
  `RAISE EXCEPTION` from `_vorp_validate_roster_shape` until someone
  lands definitions.

* **Rounding precision.** SQL rounds `vorp` to 9 dp and the
  proportional reweight step to 12 dp. The Python mirror does the
  same. `apply_70_anchor` in Python does NOT round (it propagates
  full precision). 9-dp rounding is chosen for SQL determinism; the
  test asserts equality to 6 dp against the baseline anchor.

* **`native` on cut players.** `pipelines/preview_vorp_views.py`
  derives `display_indexed = native * 70 / peak` for every player with
  a native value, including the cut tier. The on-demand function
  preserves that exactly: a cut player with `native` supplied still
  gets a scaled indexed value. No data is invented. Same semantics as
  `preview_vorp_views.py:222`.

* **Numeric key as text.** `p_base` keys are passed as text (matches
  the JSON cache format). The function rejects duplicate canonical
  numeric keys and rejects non-positive integer strings (mirrors
  `_canonical_number` in `build_imputed_vorps.py:87-96`).

---

## What I could not execute and why

* **Python test execution.** The task spec notes Python execution may
  be unavailable (`HOST_CAPABILITY_UNAVAILABLE`). I did not attempt
  to run the test or the Python mirror. Tests were written
  carefully and the syntax-check on the file (manual review)
  passes, but no runtime confirmation is in this report. **Out-of-
  sandbox verification needed.**

* **Supabase DDL apply.** Per standing rule: I did NOT apply the
  migration to Supabase. The migration file is repo-only; Roman owns
  the apply step.

* **Linear CLI / merge / push / deploy / browser.** None used.

* **Mac-only files / `~/Projects/"fantasy tools"` data.** Untouched.

* **`make test-unit` execution.** Could not run the make target
  here. The new test file is added to the unit tier by being a
  standard `unittest.TestCase` module under `tests/` — but the
  Makefile (`test-unit:` block, lines 115-202) enumerates tests by
  name. **Out-of-sandbox addition to the Makefile** is needed to
  wire `tests.test_vorp_view_baseline_match` into the `test-unit`
  target. I deliberately did NOT edit the Makefile in this slice;
  the next step (out of this PR scope) should add
  `python3 -m unittest tests.test_vorp_view_baseline_match` to the
  block. Flagged in `docs/vorp-on-demand-port-notes.md` §7 acceptance-
  criteria mapping: the test exists and is hermetic, but wiring the
  Makefile call is the human/operator step.

---

## Exact test command for outside-sandbox verification

```
python3 -m unittest tests.test_vorp_view_baseline_match -v
```

Expected output (synthesised; reflects the test plan in this PR):

```
test_baseline_anchor_cuts_emit_zero_vorp ... ok
test_baseline_anchor_matches_mirror_exactly ... ok
test_baseline_anchor_uses_70_peak ... ok
test_baseline_anchor_vorp_indexed_uses_native_peak ... ok
test_bench_share_bounds_fail_closed ... ok
test_bench_share_default_is_0_15 ... ok
test_bench_share_inclusive_bounds ... ok
test_bench_share_split_within_one_percent ... ok
test_default_1qb_definition_is_pinned ... ok
test_mirror_fail_closed_when_bench_share_out_of_bounds ... ok
test_mirror_matches_build_reweighted_values_on_canonical_fixture ... ok
test_roster_shape_required_keys ... ok
test_scoring_whitelist ... ok
test_superflex_custom_a_custom_b_are_needs_review ... ok
test_teams_positive_int ... ok
```

Total: 15 tests.

If the Makefile is wired (see above), the full unit tier runs via:

```
make test-unit
```

---

## Commit plan (small coherent slices)

Slice 1: `sql/migrations/007_vorp_on_demand_views.sql`
Slice 2: `tests/test_vorp_view_baseline_match.py`
Slice 3: `docs/vorp-on-demand-port-notes.md` + `lanes/inbox/minimax/JEG-332-draft.md`

I commit each slice separately with a clear message; the lane owner
reviews and merges. I do NOT push or merge (per standing rules).