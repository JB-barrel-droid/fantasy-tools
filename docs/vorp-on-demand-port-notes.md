# JEG-332: on-demand VORP view port — notes

**Branch:** `minimax/jeg-332-vorp-view`
**Migration:** `sql/migrations/007_vorp_on_demand_views.sql`
**Test:** `tests/test_vorp_view_baseline_match.py`

This document is the porting record for the on-demand VORP-family
computation. Every formula below is paired with the exact Python source
line(s) it ports from. Judgment calls and gaps are flagged
`NEEDS-REVIEW`. Nothing here is a methodology change; it is a translation
of the as-published computation into a stored `public.compute_vorp_views`
function.

---

## 1. Inputs and contract

| Param          | Type    | Source of truth                                    |
| -------------- | ------- | -------------------------------------------------- |
| `p_base`       | jsonb   | deepest shape-independent layer (per-player)       |
| `p_scoring`    | text    | `standard` \| `half_ppr` \| `ppr`                  |
| `p_teams`      | int     | positive                                           |
| `p_roster_shape` | jsonb | one of the 4 named shapes (see §3)                 |
| `p_bench_share` | numeric | `[0.01, 0.30]`, default `0.15`                    |

**`p_base` per-player shape:**
```
{
  "player_key":   "<positive integer as text>",
  "position":     "QB" | "RB" | "WR" | "TE",
  "surplus_ppg":  <numeric, >= 0>,   -- raw PPG above waiver (shape-independent)
  "native":       <numeric, >= 0>    -- OPTIONAL; for vorp_indexed
}
```
`native` is OPTIONAL — sources that don't publish trade values (granular
kdst pipelines per `preview_vorp_views.py`) carry no native and
`vorp_indexed` is `NULL` per row, never fabricated.

---

## 2. Formula → Python source map

Every formula in `public.compute_vorp_views` ports a specific Python
expression. The line numbers reference the repo at the time of writing.

| # | Step in SQL function                                | Python source                                                       |
| - | --------------------------------------------------- | ------------------------------------------------------------------- |
| 1 | `v_bench_share := _vorp_validate_bench_share(...)`  | `pipelines/build_reweighted_values.py:45` `DISPLAY_MAX = 70.0` plus module docstring on 15% bench default (`pipelines/build_reweighted_values.py:1-13`) |
| 2 | scoring whitelist `{standard,half_ppr,ppr}`         | `pipelines/build_imputed_vorps.py:58-59` `RosterConfig.__post_init__` |
| 3 | `teams > 0`                                         | `pipelines/build_imputed_vorps.py:56-57` `RosterConfig.__post_init__` |
| 4 | roster_shape keys `{QB,RB,WR,TE,FLEX,BENCH}` + ints | `app/trade-value-chart/assets/curve-widget.js:84` `DEFAULT_ROSTER` and `docs/contract/fe-read-contract-v1.md:362` `default_roster_shape` |
| 5 | duplicate canonical key detection                   | `build_imputed_vorps.py:64-68` `_canonical_number` + `:114-119` duplicate alias guard in `_validate_values` |
| 6 | position ∈ `{QB,RB,WR,TE}`                          | `build_imputed_vorps.py:33` `FLEX_ELIGIBLE` + `:120-122` `_validate_values` |
| 7 | ties broken by ascending numeric player_key         | `build_imputed_vorps.py:157` `infer_roster` sort key `(-value, _canonical_number)` |
| 8 | dedicated → flex (RB/WR/TE) → bench → cut          | `build_imputed_vorps.py:142-177` `infer_roster`                    |
| 9 | flex pool limited to FLEX_ELIGIBLE (no QB)          | `build_imputed_vorps.py:33,166` `FLEX_ELIGIBLE = ('RB','WR','TE')`   |
| 10 | group totals `sum_surplus[pos, role]`              | `build_imputed_vorps.py:200-208` group sum                         |
| 11 | per-role effective target = position_total × role_share | `pipelines/build_reweighted_values.py:78-97` `linear_reweight` semantics: budget allocation within the 8-group methodology |
| 12 | bench share split (1-bench_share / bench_share)    | `build_reweighted_values.py:119-141` `constrain_group_budgets` (the `wanted` bench fraction) |
| 13 | proportional reweight within role                  | `build_imputed_vorps.py:218-227` `compute_imputed_vorps` final block |
| 14 | `vorp[k] = imputed_vorp[k]`                        | `build_reweighted_values.py:216-218` `build_three_views` — `vorp` is verbatim imputed map |
| 15 | `adj_values[k] = imputed_vorp[k] * 70 / peak`      | `build_reweighted_values.py:164-178` `apply_70_anchor`              |
| 16 | `vorp_indexed[k] = native[k] * 70 / peak_native`   | `pipelines/preview_vorp_views.py:211-222` `display_indexed = nv * DISPLAY_MAX / peak` |

---

## 3. The 4 named roster shapes

Per `docs/contract/fe-read-contract-v1.md:84` there are 4 named shapes:
**default 1QB, default SUPERFLEX, custom-A, custom-B**.

| Shape              | Definition in this repo?                                                                                  | Status          |
| ------------------ | --------------------------------------------------------------------------------------------------------- | --------------- |
| `default_1QB`      | Yes — `{"QB":1,"RB":2,"WR":3,"TE":1,"FLEX":1,"BENCH":6}` (`curve-widget.js:84`, `fe-read-contract-v1.md:362`) | Pinned          |
| `default_SUPERFLEX` | No — the widget toggles `shape.SUPERFLEX` (`curve-widget.js:878`) and adds QB to flex-eligible, but slot counts are not pinned | **NEEDS-REVIEW** |
| `custom_A`         | No — mentioned by name only; no definition in `docs/contract/fe-read-contract-v1.md`                     | **NEEDS-REVIEW** |
| `custom_B`         | No — mentioned by name only; no definition in `docs/contract/fe-read-contract-v1.md`                     | **NEEDS-REVIEW** |

This migration takes `p_roster_shape` as a **validated jsonb parameter**
and never defaults it. The shape must define `{QB,RB,WR,TE,FLEX,BENCH}`
as nonnegative integers; out-of-schema shapes FAIL CLOSED. The three
unpinned shapes are NOT inventoried here; landing their definitions is
out of scope for this PR and is left for the FE widget to surface a
JSON-shape error from `public._vorp_validate_roster_shape`.

---

## 4. `bench_share` failure mode

| Input value | Behavior                                                       |
| ----------- | -------------------------------------------------------------- |
| `NULL`      | defaulted to `0.15`                                            |
| `< 0.01`    | `RAISE EXCEPTION` (e.g. `0.0`, `-0.1`)                         |
| `> 0.30`    | `RAISE EXCEPTION` (e.g. `0.31`, `0.5`, `1.0`)                  |
| `[0.01, 0.30]` | accepted                                                      |

This is the **fail-closed** identity the task spec requires. There is NO
silent clamp. The test
`tests/test_vorp_view_baseline_match.py::ValidatorTests::test_bench_share_bounds_fail_closed`
enforces the contract at the unit level (the Python mirror raises
`ValueError` for every out-of-bounds value).

---

## 5. What the port deliberately leaves out

The migration ports the **single-source on-demand** semantics. It
deliberately does **not** port:

1. **Multi-source shared budget (`constrain_group_budgets`).** The
   shared-batch70 computation in
   `pipelines/build_reweighted_values.py:100-142` distributes one shared
   8-group budget across multiple inputs by computing a cap per
   position. The on-demand view is single-source: each call gets one
   `p_base`. Multi-source consolidation is upstream of the deepest
   layer.

2. **`SOURCE_KINDS` distinction (`published`/`derived`/`granular`).**
   The Python code skips the within-position inversion diagnostic for
   derived sources (`build_reweighted_values.py:181-195`). The SQL
   function does not model source kind; that distinction is upstream
   of the deepest layer.

4. **`AVG` cross-source averaging (`cross-source-average-v1`).**
   Lives in `pipelines/build_consolidated_values.py` and is upstream of
   the deepest layer.

5. **Provenance / hashing / `option-c-imputation-manifest-v1`.** The
   Python pipeline stamps sha256 hashes (`build_reweighted_values.py:303-367`)
   for every source. The on-demand function trusts the `p_base` it
   receives; provenance is owned by the writer.

6. **Three-view `indexed` from native map (`AVG-backstopped rows absent`).**
   `pipelines/preview_vorp_views.py:210-229` excludes AVG-backstopped
   rows from indexed by design. The SQL function does the same
   implicitly: a player whose `native` is `NULL` in `p_base` gets
   `vorp_indexed=NULL`. Players whose native IS supplied get indexed.

---

## 6. Judgment calls flagged

* **NEEDS-REVIEW (default SUPERFLEX / custom-A / custom-B shapes):**
  the FE widget reads these from a JSON form, the contract doc names
  them, but their slot counts are not pinned anywhere in this repo.
  The SQL function accepts a jsonb shape parameter and validates it
  structurally; it does NOT default to any of the four. Until
  someone lands the four definitions, callers passing an unknown shape
  get a `RAISE EXCEPTION` from `_vorp_validate_roster_shape`.

* **NEEDS-REVIEW (rounding precision):** SQL rounds `vorp` to 9 dp and
  the proportional reweight step to 12 dp. The Python mirror does the
  same. `build_reweighted_values.apply_70_anchor` does NOT round; it
  uses `math.fsum` for sums and `_nonnegative_finite` for validation
  but propagates full precision. The 9-dp rounding is chosen so SQL
  results are deterministic and comparable across calls; the test
  asserts equality to 6 dp against the baseline anchor.

* **NEEDS-REVIEW (numeric key as text):** `p_base` keys are passed as
  text (matches the JSON cache format used by `preview_vorp_views.py`).
  The function rejects duplicate canonical numeric keys
  (`_canonical_number` equivalent) and rejects non-positive integer
  strings.

* **NEEDS-REVIEW (cut → scaled native vs cut → NULL indexed):** Python
  `preview_vorp_views.py` derives `display_indexed = native * 70 / peak`
  for every player that has a native value, including the "cut" tier
  (waiver players). The on-demand function preserves native semantics:
  a cut player with `native` supplied still gets a scaled indexed
  value. This matches `preview_vorp_views.py:222` `views["indexed"][src]
  = display_indexed`. No data is invented.

---

## 7. Acceptance-criteria mapping

| Criterion                                                                  | Where it lives                                    |
| -------------------------------------------------------------------------- | ------------------------------------------------- |
| bench_share ∈ [0.01, 0.30] FAIL CLOSED                                     | `_vorp_validate_bench_share` + `ValidatorTests.test_bench_share_bounds_fail_closed` |
| bench_share default 0.15                                                    | `_vorp_validate_bench_share` + `ValidatorTests.test_bench_share_default_is_0_15` |
| bench_share inclusive on both bounds                                        | `ValidatorTests.test_bench_share_inclusive_bounds` |
| scoring whitelist `{standard,half_ppr,ppr}`                                | `_vorp_validate_scoring` + `ValidatorTests.test_scoring_whitelist` |
| teams > 0                                                                   | `_vorp_validate_teams` + `ValidatorTests.test_teams_positive_int` |
| roster_shape required keys + nonnegative ints                              | `_vorp_validate_roster_shape` + `ValidatorTests.test_roster_shape_required_keys` |
| 4 named shapes documented / NEEDS-REVIEW                                    | `RosterShapeDefinitionTests`                      |
| Python mirror == build_reweighted_values on inline fixture                  | `PythonMirrorEqualityTests.test_mirror_matches_build_reweighted_values_on_canonical_fixture` |
| bench_share=0.15 baseline anchor matches SQL exactly                        | `BaselineAnchorContractTests.test_baseline_anchor_matches_mirror_exactly` |
| 70 anchor (adj_values / vorp = 70 / peak)                                   | `BaselineAnchorContractTests.test_baseline_anchor_uses_70_peak` |
| indexed = native * 70 / peak_native                                         | `BaselineAnchorContractTests.test_baseline_anchor_vorp_indexed_uses_native_peak` |
| cut players emit vorp=0, adj_values=0                                       | `BaselineAnchorContractTests.test_baseline_anchor_cuts_emit_zero_vorp` |
| bench_share sweep respects the split                                       | `BenchShareSweepTests.test_bench_share_split_within_one_percent` |
| Python mirror fails closed on bench_share out of bounds                    | `PythonMirrorEqualityTests.test_mirror_fail_closed_when_bench_share_out_of_bounds` |