# League-settings inventory (JEG-332, step 1)

Decision: `docs/decisions.md` league-settings-001. The backend saves one setup
(12 teams, standard roster) for each of the three scoring formats. The browser
derives team count, roster shape and bench share. This file maps every chart view to
the saved input the browser derives it from, and lists what is missing.

Evidence: `data/fixtures/current/comparison-sources-data.json` at main (2026-10-06),
`app/trade-value-chart/assets/*.js`, `pipelines/vorp_translation/unified.py`.

## Summary

Every chart view can be derived in the browser from inputs that are **already
saved at 12 teams**. No new saved field is needed. One server-only formula has
to be ported to JavaScript: the value-above-waivers translation of published
charts (JEG-62/64).

## What the browser does today

| Chart series | How the site gets the value for a league setting | Code |
| --- | --- | --- |
| ESPN, CBS ROS, Razzball (`espn_vorp`, `cbsros_vorp`, `razzball_vorp`) | **Already derived in the browser** from per-game points on the player records (`espn_ppg`, `cbsros_ppg`, `rz_ppg`, per scoring), using the TwoTier model for any team count, roster and bench share. The fixture's per-setup blocks for these sources are not what the chart reads. | `curve-widget.js` `PURE_VORP_KEYS` (l.66), `sourceComboExists` (l.899), `TwoTier` (l.195) |
| CBS, FantasyPros, USA Today | **Lookup** of a saved per-setup block through `product-data.js` `getPlayerValues({source, scoring, teams, qbVariant:"qb1", view:"combo_reindexed"})`. Only `*_12` blocks exist, so at 8/10/14 teams these sources show as unavailable; `sourceComboKey` deliberately never borrows another size. | `curve-widget.js` `buildPublishedSourceMap` (l.1036), `value-model.js` `sourceComboKey` (l.27) |
| FantasyCalc | **Lookup**, as above. 24 saved blocks (3 scorings × 4 sizes × 1-QB/superflex). | same |
| `*_adjusted` (bias-corrected) | **Lookup** of the saved block. The browser refits live adjustment cells from `adjustment-inputs.json`. | `curve-widget.js` `refitLiveCells` (l.1646) |
| `vorp_views` (indexed / value above waivers / adjusted values) for FantasyCalc, FantasyPros, USA Today | Saved for full PPR, 12 teams only (JEG-331). | `curve-widget.js` `buildVorpViewSourceMap` |

## How each saved value is made at 12 teams, and whether the browser can redo it at any setting

| View | Recipe (12 teams today) | Inputs, all saved at 12 teams | Browser can derive any setting? |
| --- | --- | --- | --- |
| Model sources (ESPN, CBS ROS, Razzball) | TwoTier value above waivers from per-game points | per-game points by scoring, position | **Yes, already does** |
| Published charts: rescaled (`reindexed`) | Flex-aware fixed pie: position × role buckets (dedicated / flex / bench, sized by teams × starters) scaled onto the ESPN leg's bucket totals (`fit.flex_aware_pie`, `index_total`) | source's published values (`native`), positions; ESPN totals come from the browser's own ESPN series at that setting | **Yes**: `ValueModel.roleMap`, `allocationCounts`, `normalizeToFixedPie` already exist in JS |
| Published charts: value-above-waivers translation (`translation.method = vorp-supabase`; replaces the rescaled value for most players, e.g. CBS full/12: 103 of 116) | Count rostered players per position for the team count; waiver line = first unrostered player's published value; subtract it; scale by our position maximum (QB 25 / RB 70 / WR 55 / TE 30 at the saved setup; since 2026-10-07 the browser moves these with the setting: OUR_MAX x ESPN top-player value-above-waivers ratio, top position rescaled to 70 -- `positionalMaxForSetup`, JEG332-DERIVED-PEAKS) | `native`, positions, team count, bench and flex counts | **Yes, after porting** `pipelines/vorp_translation/unified.py` + `vorp_via_roster.py` (about 80 lines of pure arithmetic) to JS |
| `*_adjusted` | Bias correction fitted against the ESPN 12-team leg (`fit.method = bias_adjusted`, bake `ddf-…-espn-ppr-12t-0p15`) | saved fit + the same published values | **To confirm**: check whether the fit's parameters are scale-free (apply at any team count) or tied to the 12-team ESPN pie |
| `vorp_views` | Same translation + rescale family | as above | **Yes, after the port** |

## Findings along the way

1. **ESPN's 8/10/14-team fixture blocks are byte-identical copies of 12-team**
   (native, values and reindexed, 493 players each). The chart doesn't read them
   (it derives ESPN in the browser), but the review chain, monitors and
   `consolidated_values` do, so they report one ESPN answer for every league size.
2. **FantasyCalc's 12-team superflex block is identical to 1-QB** (all 196
   players). Superflex isn't really sourced; under league-settings-001 it becomes a
   browser roster setting like the rest.
3. **CBS ROS and Razzball per-game points are identical across team sizes**, and
   only the derived values change. That confirms per-game points are the right
   base layer for model sources.
4. Published editorial charts (CBS, FantasyPros, USA Today) publish one list per
   scoring. Under league-settings-001 they gain 8/10/14-team support, which they
   don't have today.

## Work this implies (JEG-332 steps 2–3)

1. **Done (2026-10-06):** `ValueModel.translatePublishedVorp` (version
   `unified-py-jeg62/1`) ports `unified.translate_ranked` + `vorp_via_roster`.
   `tests/test_vorp_translation_js_parity.py` runs both on 1,299 identical
   inputs (4 sources × 3 scorings × 8/10/12/14 teams × bench/flex/slot shapes,
   plus edge vectors) and requires exact equality. At 12 teams it reproduces
   the saved values for CBS and FantasyPros; USA Today and FantasyCalc saved
   values are stale (risk register JEG332-STORED-DRIFT).
2. **Done (2026-10-06):** published sources derive in the browser at every
   non-saved setting (`ValueModel.derivePublishedSetup`, wired in
   `curve-widget.js` and `comparison-dashboard.js`); the saved setup still reads
   the saved values (12-team maps byte-identical in the 12-combo sweep).
   `tests/test_published_league_settings_engine.py` (pure) and
   `tests/test_published_league_settings_render.py` (live page, JEG-334) gate it.
3. **Answered:** `*_adjusted` needs no saved fit at other settings: the browser
   already refits its cells live (`refitLiveCells`, OLS of the ESPN two-tier
   leg on the published raw values) at the active team count, so it refits on
   the derived raw values. The cache key now includes the roster.
4. Then (JEG-329) stop saving non-12-team blocks and rows, back up and remove the
   existing ones, and drop the duplicated ESPN blocks.
