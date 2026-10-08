## 2026-10-08 - superflex roster spot, option A (feat/superflex)

Contract (Jeremy's decision, JEG332-SUPERFLEX-FLEX option A): a dedicated
superflex slot filled by best value with QBs eligible, without the per-position
slot weighting. Engine + Python mirrors + parity; publisher superflex values
where published; defaults unchanged (12-combo sweep, zero diffs); tests that
fail on the broken state; the v2 control spec.

Branch pushed. Not merged.

### What changed
- `SUPERFLEX` is a roster count (0 or 1 on the page, default 0) in
  `DEFAULT_ROSTER`. `setRosterSpot('SUPERFLEX', n)` accepts it, clamped to
  0..1 (`ROSTER_BOUNDS`). The classic page's roster grid has a "Superflex" input.
- Fill order everywhere: dedicated slots, then superflex (best remaining at any
  position), then FLEX (RB/WR/TE), then bench.
  - `value-model.js`: `superflexCount`, `roleMap` (by value), `projectionRoles`
    (by projected points, like FLEX; the old surplus rule for a QB-eligible
    flex is gone), `translationSuperflex` (by the chart's values, ties QB/RB/WR/TE
    then rank), flex window offset after superflex, `translationRostered` /
    `projectionMaxVorp` / `positionalMaxForSetup` / `translatePublishedVorp`
    (`superflexCount`, `n_superflex` reported only when > 0), `settingForShape`,
    `isSavedSetup`, `derivePublishedViews` (starter = dedicated + superflex + flex).
  - `flexEligible` no longer adds QB (the SUPERFLEX flag that made QB eligible
    for every FLEX slot was unreachable and is replaced).
  - Python: `vorp_via_roster.allocate_superflex`, `allocate_flex_vorp_weighted(superflex_alloc=)`,
    `rostered_for_teams(superflex_count=)`; `unified.translate_ranked` /
    `projection_max_vorp` / `positional_max_for_setup(superflex_count=)`;
    `pipelines/parity/value_model_parity.py` mirrors roleMap / projectionRoles.
  - Versions bumped: `unified-py-jeg62/3`, `league-settings-001/5`,
    `published-views-001/3`.
- Publisher superflex values: `product-data.js` view `native_superflex` reads
  `combo.native_superflex`; `curve-widget.js savedPublishedNative` overlays it on
  the 1-QB natives when SUPERFLEX > 0 (Indexed, both views, and peers).
  `publishedDerivation[src].superflex` says "publisher superflex values" or
  "derived from 1-QB values". No producer writes it yet (below).
- docs/methodology.md "Superflex" section; risk register JEG332-SUPERFLEX-FLEX
  updated, GAP-SUPERFLEX-PUBLISHER-VALUES added.

### Verified (check named)
- **Default identity, 12-combo x 3 views.** `make sync` builds of origin/main
  (dac0ff2, worktree superflex-base) and this branch, system Chrome, every
  scoring x 8/10/12/14 teams in Indexed, VORP vs waivers and Adjusted values:
  fixedPieIndexed, sourceScaleAgreement, sourcePeaks, roles and all getAllRows
  values compared -- 255,556 values, **0 moved**, no field differs. (The sweep
  ran before a final cosmetic edit: `rosterOrdinals` reads
  `(rosterShape.SUPERFLEX || 0)`; it only affects boundary markers, and
  SUPERFLEX is 0 there.) The same pre-existing CBS ROS fixed-pie-direction
  ChartHealth fails appear on both builds.
- **tests/test_superflex.py** (in `make test-core`), each check with its broken state:
  - SUPERFLEX:0 = default: Python `translate_ranked(superflex_count=0)` equals
    the omitted argument, and the browser derivation with SUPERFLEX:0 equals
    the server reference for the default roster, on 4 sources x 3 scorings x 4
    team counts. Broken: `superflexCount` defaulting to 1 -> 60 problems.
  - QBs fill superflex on real ESPN projections (players.json), 3 scorings x
    10/12 teams: projectionRoles starts 2 x teams QBs; the translation's
    superflex slots go to QBs, and Python and JS rosters are equal. Broken:
    slot-weighted apportionment -> 12 problems; superflex ranked on surplus ->
    6 problems (e.g. "starts 12 QBs, want 20").
  - Live page (served app/): `setRosterSpot('SUPERFLEX', 5)` clamps to 1, 0
    resets, the classic Superflex input works, fixedPieIndexed stays true, and
    all four published charts plot exactly the Python reference derivation with
    the slot (ppr 12). Broken: widget without the SUPERFLEX roster key -> 7 problems.
- **Parity suites extended:** test_vorp_translation_js_parity (1,493 vectors,
  0 diffs, incl. sf0/sf1/sf1-flex2/sf2 on real charts; 459 max vectors; 432
  derived-max translation vectors), test_published_league_settings_engine
  (+ superflex shape, 240 settings, 0 diffs), test_published_views_engine
  (+ superflex shape, 60 batches, 0 diffs; new "superflex-as-bench" mutation
  caught with 16 failures), test_published_*_render, check_valuemodel_parity
  (53 vectors).
- **Changed pinned assertions (the model changed, by decision):** the four
  SUPERFLEX vectors in tests/fixtures/valuemodel_vectors.json encoded the old
  flag semantics (QB eligible for FLEX); renamed and regenerated, plus two new
  ones (SF 0 = default; SF slot takes a QB when the QB is the best value).
  test_two_tier_frontend's `test_projection_roles_keep_superflex_on_surplus`
  pinned the rule that kept QBs out (QB2 at 24 ppg lost to RB2 at 17.5);
  replaced by the option A assertion. Version pins bumped with the versions.
  The engine-test references now pass `superflex_count` instead of a
  QB-eligible `flex_eligible`.
- **Publisher superflex values are not saved anywhere** (Supabase read-only
  query: `source_trade_values`, `cbs_trade_values`, `api.source_inputs_weekly`
  all have only qb_slots = 1). Code read: `pull_fantasycalc_12team.py` hardcodes
  `numQbs=1`; `pull_fantasypros.py` reads only `Value`; the CBS and USA Today
  savers write the 1QB column only (USA Today's pull JSON keeps all headers).
- `CHROMIUM_PATH=<Chrome> make validate` rc=0 on the branch.

### Values with SUPERFLEX = 1 (full PPR, Indexed; QB1 / QB12 / QB24)
| Setting | ESPN QB starters | ESPN anchor | FantasyCalc | USA Today | CBS | FantasyPros |
| --- | --- | --- | --- | --- | --- | --- |
| 10 teams, SF0 | 10 | 22.3 / 3.6 / 0 | 23.6 / 2.5 / 0 | 23.6 / 8.4 / 0 | 23.6 / 4.7 / 0 | 23.6 / 3.9 / 0 |
| 10 teams, SF1 | 20 | 23.1 / 3.7 / 0 | 35.6 / 3.8 / 0 | 35.6 / 12.6 / 0 | 35.6 / 7.0 / 0 | 35.6 / 5.8 / 0 |
| 12 teams, SF0 | 12 | 29.5 / 6.5 / 0 | 25.0 / 3.6 / 0 | 25.0 / 9.8 / 0 | 25.0 / 5.6 / 0 | 25.0 / 4.1 / 0 |
| 12 teams, SF1 | 24 | 30.9 / 6.8 / 0 | 70.0 / 11.1 / 0 | 70.0 / 27.6 / 0 | 70.0 / 16.0 / 0 | 70.0 / 11.5 / 0 |

Sanity:
- QBs fill every superflex slot in the ESPN roles (24 QB starters at 12 teams).
- The published charts' QB values rise through the league-following maxes. At
  12 teams QB becomes the top position (QB1 70, FantasyCalc RB1 66.5): with 24
  starting QBs plus bench, the QB waiver line is a backup. At 10 teams QB1 is 35.6.
- SF1 sits just below QB = 2 (QB stepper, 12 teams: FantasyCalc QB12 12.4 vs
  11.1, USA Today 31.1 vs 27.6). That is the expected order: the superflex slot
  may go to a non-QB in a 1-QB chart's own values.
- QB24 is 0 everywhere: the 24th QB is at or below the superflex waiver line.
- **Not sane, and not fixed here:** the ESPN anchor barely moves (QB1 29.5 -> 30.9),
  and espn_vorp's QB1 falls 27.5 -> 26.6. Neither the anchor (the built leg, which
  follows roster shape only through applyRosterShape's top-N factor) nor the raw
  value-above-waivers pies (fixed at the reference roster) are repriced. This
  is the same open anchor question as the QB stepper. sourceScaleAgreement turns
  false at ppr_12 with SF1 (non-blocking).

### Claimed, not confirmed
- The `native_superflex` overlay path is exercised only with the field absent.
  No fixture carries it, so the "publisher superflex values" branch has not run
  on real data. Producer work is needed (risk register
  GAP-SUPERFLEX-PUBLISHER-VALUES).
- I did not compare the derived superflex values with FantasyCalc's own
  `numQbs=2` page (no network pull).
- History (`getWeekValues`) derives with the active roster but reads 1-QB
  natives only. Superflex history uses the 1-QB values.
- The TwoTier live pools (cbsros/razzball live cells, `twoTierConfig`) stay at
  the reference roster, as they do for every roster stepper.
