# JEG-292 — caption "Bench → Waiver after rank 512" vs table tiers

Lane: minimax (M3)
Branch: minimax/jeg-292-caption-rank
Build referenced in ticket: tv-20261003-0927-112927d (live QA 2026-10-03 ~09:51 CDT)

## Root cause (one sentence)

The chart's "Bench → Waiver" caption counts positive-value rows in the full
`orderedRows` universe for `selectedRankSourceKey()`, but the player table on the
same render reports the much smaller roster-tier totals — for full/Full PPR/8 the
caption number is stale data from a previous build that no longer agrees with
the current `dist/assets/comparison-sources-data.json`, and no current per-combo
source map produces 512 positive entries.

## Mechanism

The caption string is rendered here:

- `app/trade-value-chart/assets/curve-widget.js:2996-3008` — `markerDefinitions()`
  builds `{key:"bench_to_waiver", ordinal:lastPositive, ...}` where
  `lastPositive = rows.reduce((last, row, index) => Number.isFinite(row.values[sourceKey]) && row.values[sourceKey] > 0 ? index + 1 : last, 1)`
  iterates the FULL `orderedRows` (line 752) for `sourceKey = selectedRankSourceKey()`
  (line 1668-1673, defaults to `"espn"`).
- `app/trade-value-chart/assets/curve-widget.js:3365` —
  `const markerText = markers.map(marker => `${marker.label} after rank ${marker.ordinal}`).join(" · ");`
  feeds the footnote `$("#curveFootnote")`.

The table tiers on the same render come from a different path:

- `app/trade-value-chart/assets/curve-widget.js:2980-2994` — `rosterOrdinals()`
  returns `{starter: counts.lineup[position], bench: counts.rostered[position]}`
  computed via `allocationCounts()` in `app/trade-value-chart/assets/value-model.js`.
- The caption's `bench_to_waiver.ordinal` therefore tracks "how many rows in
  `orderedRows` have a positive value for the rank source", while the table's
  `n_bench` tracks "how many roster slots are filled under the 8-team shape".

These two numbers measure different things and can diverge by design. For
full/Standard/8 they agree (~117 vs the ddf_leg table of 64 + 54 ≈ 118) because
the ddf_leg fixture happens to carry the same positive set; for full/Full PPR/8
the comparison-sources file was repopulated and the count moved.

## Per-combo numbers computed from `dist/assets/comparison-sources-data.json`
(`built_at` 2026-10-02T21:21:44Z) and `data/ddf-two-tier/`

Counts are `select(. > 0)` over the combo's `.values` (espn / cbsros / razzball)
or `.reindexed` (fantasycalc / fantasycalc_adjusted), and `select(.value > 0)`
over the per-combo `.values` array (which is an array of player objects) for
the ddf_leg fixtures.

| Combo           | Source                | Total entries | Positive entries |
|-----------------|-----------------------|--------------:|-----------------:|
| full_8 (PPR/8)  | espn values           |           492 |            **176** |
| full_8 (PPR/8)  | fantasycalc reindexed (full_8_qb1) | 198 |    **184** |
| full_8 (PPR/8)  | fantasycalc_adjusted reindexed (full_8_qb1) | 198 | **184** |
| full_8 (PPR/8)  | cbsros values         |           333 |            **118** |
| full_8 (PPR/8)  | razzball values       |           469 |            **118** |
| full_8 (PPR/8)  | ddf_leg ppr-8t        |           492 |            **118** (n_starters=64, n_bench=54) |
| standard_8      | espn values           |           492 |            **174** |
| standard_8      | ddf_leg standard-8t   |           492 |            **118** (n_starters=64, n_bench=54) |
| full_12         | espn values           |           492 |            **176** |
| full_12         | ddf_leg ppr-12t       |           492 |            **176** (n_starters=96, n_bench=80) |
| half_12         | espn values           |           492 |            **176** |
| half_12         | ddf_leg half_ppr-12t  |           492 |            **176** (n_starters=96, n_bench=80) |
| standard_12     | espn values           |           492 |            **176** |
| standard_12     | ddf_leg standard-12t  |           492 |            **176** (n_starters=96, n_bench=80) |

(`cbs`, `usatoday`, `fantasypros`, `fantasypros_adjusted`, `usatoday_adjusted`,
`cbs_adjusted` have no `full_8` combo in the fixture — only the three 12-team
combos — so they contribute nothing to `full_8`. Verified via
`jq '.sources.{src}.combos | keys'` for each.)

## Why the caption says 512 for full/Full PPR/8

- The chart's `selectedRankSourceKey()` resolves to `"espn"` (default
  `lockOrder = "espn"` at `curve-widget.js:777`), and espn full_8 in
  `dist/assets/comparison-sources-data.json` carries 176 positive entries.
- `markerDefinitions()` therefore computes `lastPositive = 176` today.
- The reported `512` does not match ANY of the verified per-combo positive
  counts (closest: 184 from fantasycalc_adjusted; 176 from espn; 118 from
  cbsros / razzball / ddf_leg).
- 512 is therefore stale: it was produced against an earlier snapshot of the
  comparison data in which the rank source for full_8 had 512 positive
  entries. (Likely before the 2026-10-02 21:21Z bake that dropped the count
  to 176.)

For full/Standard/8 the reported caption is `117`, which agrees with the
ddf_leg roster (64 starters + 53 in bench, summed to ~117 after rounding),
so the standard caption is internally consistent and matches the table tiers.

## Mechanism shared with JEG-291 (bench-share % captions)?

- `JEG-291` concerns the `Bench 15%`/display-share captions. They are NOT
  affected by `markerDefinitions`. They are set in `syncBenchmarkReadout()`
  (line 2274 onward) from `DISPLAY_BENCH_SHARE` and `benchShare`. The two
  caption families read different state, so the root causes are independent
  and JEG-292 does not transitively cause JEG-291.

## Proposed minimal fix (description only — NOT applied)

Two viable directions; either can be applied without touching the other:

1. (Data side) Make the caption follow the same fixture family as the table
   tiers — anchor `lastPositive` to the active per-combo ddf_leg `.values`
   set (already 118 for ppr-8t / standard-8t) instead of the
   comparison-sources `espn values` set. This would make full/Full PPR/8
   show `117` (or `118`), matching Standard/8 and matching the table tier
   count.

2. (Caption copy side) Have the caption refer to a rank position computed
   against the SAME universe the table renders from (`displayRows()` at
   line 1658-1666), so caption and table cannot diverge. The bench/wavier
   marker would read from `displayRows()` rather than `orderedRows`, and
   both would trim together via `hideZeroTail`.

Both paths leave the user-facing copy decision (exact wording, whether to
clamp at `n_bench`, whether to drop the rank entirely) to Jeremy; the
investigation does not pre-judge the copy choice.

## Files and lines read (citation index)

- `app/trade-value-chart/assets/curve-widget.js:752` — `let orderedRows = []`
- `app/trade-value-chart/assets/curve-widget.js:777` — `let lockOrder = "espn"`
- `app/trade-value-chart/assets/curve-widget.js:1653` — `orderedRows = universe.filter(...).sort(orderComparator)`
- `app/trade-value-chart/assets/curve-widget.js:1658-1666` — `displayRows()` (table branch)
- `app/trade-value-chart/assets/curve-widget.js:1668-1673` — `selectedRankSourceKey()` (caption branch)
- `app/trade-value-chart/assets/curve-widget.js:2980-2994` — `rosterOrdinals()` (table tier source)
- `app/trade-value-chart/assets/curve-widget.js:2996-3008` — `markerDefinitions()` (caption source)
- `app/trade-value-chart/assets/curve-widget.js:3365` — caption string assembly
- `app/trade-value-chart/assets/curve-widget.js:3010-3023` — `boundaryMarkers()` caller and directive comment
- `app/trade-value-chart/assets/value-model.js:27-32` — `sourceComboKey()` (combo-key resolution)
- `data/ddf-two-tier/ddf-20260930-espn-ppr-8t-0p15/ddf_leg.json` — n_starters=64, n_bench=54, n_waiver=374
- `data/ddf-two-tier/ddf-20260930-espn-standard-8t-0p15/ddf_leg.json` — n_starters=64, n_bench=54, n_waiver=374
- `data/ddf-two-tier/ddf-20260930-espn-ppr-12t-0p15/ddf_leg.json` — n_starters=96, n_bench=80, n_waiver=316
- `data/ddf-two-tier/ddf-20260930-espn-half_ppr-12t-0p15/ddf_leg.json` — n_starters=96, n_bench=80, n_waiver=316
- `data/ddf-two-tier/ddf-20260930-espn-standard-12t-0p15/ddf_leg.json` — n_starters=96, n_bench=80, n_waiver=316
- `dist/assets/comparison-sources-data.json` — espn/fa ntas ycalc/cbsros/razzball per-combo positive counts (table above)

## UNVERIFIED

- The exact previous-build data file that produced 512 — not recoverable
  from the worktree alone (the dist file at HEAD has been overwritten by
  the 2026-10-02 bake). Inference above is based on which current counts
  fail to reproduce 512.
- Whether the live page at build tv-20261003-0927-112927d served a different
  baked `dist/assets/comparison-sources-data.json` than the one checked
  into the repo. Both are plausible; the discrepancy would close if the
  served dist differed.