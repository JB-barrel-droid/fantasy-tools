# Methodology

This file is the required methodology entrypoint. It summarizes the stable
contract and points to the detailed rules that own each section.

## Why

`docs/manifesto.md` states the project's reasoning: player value splits into
market, fundamental (value above waivers, usable production) and portfolio
value, and decisions come from the gaps between them. Judge features against it.

## Trade-Value Contract

The dashboard compares source values on a common, ESPN-anchored fixed-pie scale.
The public chart should answer: how do current source trade values differ after
identity matching, per-position reindexing, and shared-scale normalization?

The stable rules are:

- Identity resolves to canonical numeric `player_key`; names are display only.
- Source values stay native until the reference-compute step reindexes them.
- Missing source values stay absent/null and display as unavailable.
- Genuine source zeros stay zero.
- A player ESPN lists but projects at 0 (injured or out) is a genuine ESPN zero:
  0.0 on the ESPN series, with a badge, so a chart still paying for him shows a
  gap (Jeremy, 2026-10-07). The zero is shown, not added to the anchor: the pie
  every chart is indexed against is unchanged. A player with no ESPN row is
  missing, not 0.
- The same holds below a leg's pricing line: a player ESPN, CBS ROS or Razzball
  projects at or below the lowest projection that leg prices at his position is
  0.0 on that leg, not missing (Jeremy, 2026-10-07); display only, like the
  injured case. A player above that line whom the leg lacks stays missing.
- Published/direct charts are compared against the built ESPN indexed leg.
- Raw ESPN value above waivers is a separate comparison mode, not the indexed
  trade-value anchor.
- Adjusted source projects are derived estimates from raw source values plus
  versioned adjustment cells.

## The Three Views (Jeremy, 2026-10-07)

1. **Value above waivers.** Every source, projections and published trade
   charts alike, is translated to implied value above waivers. The ranker's
   assumed roster, bench shape included, is the standard default league
   settings unless the publisher's own materials state otherwise. From that
   roster and the source's values come the ranker's implied weights by
   position and by starter/bench (flex counted). The waiver line then gives
   each player's implied value above waivers. Position counts always account
   for flex.
2. **Adjusted values.** All value above waivers is re-weighted to DDF weights
   by position x starter/bench group.
3. **Indexed.** The original published trade charts are indexed to match the
   value range of the other charts.

**Indexed is one factor per chart (JEG-482, Jeremy 2026-10-08).** "There
shouldn't be some secondary correction layer, the math is clearly off and this
finding is a signal that it is." A published chart's Indexed values are its
native values times ONE factor per chart and combo:

    factor  = anchor total / native total, over the players the chart prices
              that the ESPN anchor also prices
    indexed = native x factor

so the chart's pie equals the anchor's over the same players and its own
ranking survives exactly, across and within positions, at every league setting
(`reindex_comparison_section.order_preserving_rescale` for the saved 12-team
values against the fixture's ESPN leg; `ValueModel.derivePublishedSetup` /6
against the live anchor everywhere else). Per-position and starter/bench
repricing belongs only to VORP vs waivers and Adjusted values. The rank guard
(`pipelines/check_rank_guard.py`, `tests/test_rank_guard.py`, written to
`output/rank-guard.json` and `dist/modules/rank-guard.json` on every
`make sync`) fails the build on any pair of players a chart ranks apart whose
Indexed order differs. What it replaced: from 2026-10-01 each chart was scaled
per (position, starter/flex/bench) bucket to the anchor's total for that bucket
(d4629423, 6a824749), and from JEG-64 the saved values were the chart's value
above waivers put onto our positional maxes (`translate_via_vorp.py`, removed)
-- both repriced positions against each other, so on Week 5 FantasyCalc's #3
(Smith-Njigba) showed #5 and the 12 saved combos carried 15,279 pairwise
inversions.

Value above waivers and DDF values follow the user's league-settings inputs
(teams, scoring, roster). There is no cap at the anchor's top value: a
publisher whose implied weighting puts its top player above ours shows that.
CBS ROS and Razzball are matched to the ESPN anchor by total only (Jeremy,
2026-10-08): one factor makes their total over the players they share with ESPN
equal ESPN's, so each keeps its own weighting across positions and its own top
values. Aligning each position's top to ESPN's applies only to the fitted
`*_adjusted` series.

### Inspecting the math

Internal page: `modules/math-inspector.html` (live:
https://jb-barrel-droid.github.io/fantasy-tools/modules/math-inspector.html).
Noindex, linked from no public page. It runs the chart engine off-screen and
shows, for any scoring, team count, roster and bench share: each source's saved
inputs and provenance (content week, URL, bake, identity rows not resolved to a
charted player); the translation (rostered counts, waiver line and how it was
set, value above waivers in the chart's own units, implied weights by position
and starter/bench); the Indexed pie split by position x starter/bench beside
the anchor's on the same players; VORP vs waivers and Adjusted values per
player side by side with every factor; a one-player drill-down across all
sources and views with the prior week's change; and a CSV/JSON download of
every table. It reads only `TradeValueCurveControls.getInspection()` (a
read-only accessor); `tests/test_math_inspector.py` holds its tables to the
engine's `getAllRows()` in all three views at three settings. Built by
`pipelines/build_inspector_page.py` from `app/inspector/` on every `make sync`.

**What the views guarantee today (views-audit, measured 2026-10-08).** Jeremy
stated the invariants on 2026-10-08. Indexed: "the positions and bench/starter
have different weights but the total pies are the same". VORP vs waivers:
"the differences in deconstructed values of each player on the same exact
scale". Adjusted: "the differences in value of each player, when their
positional and bench/starter weights have been normalized". They are measured
on the players a source and the ESPN anchor both price (QB/RB/WR/TE).

What holds and is gated by `make validate` (`tests/test_view_invariants.py`):
- In every tab, CBS ROS, Razzball, the `*_adjusted` series and the raw
  value-above-waivers series total exactly the anchor's total.
- The raw series are therefore on one scale in VORP vs waivers.

What does not hold yet (measured; options on `docs/math-review-agenda.md`,
"From views-audit" and MR-01/03/04/05; not changed before the review):
- (Fixed by JEG-482: the published charts' Indexed totals now equal the
  anchor's over the players they price -- exactly off the saved setup, against
  the fixture's leg at it.)
- Their VORP vs waivers totals run 0.71-1.00x.
- Their Adjusted group totals are not the DDF weights (70 cap, mixed basis).

The page reports all of it as `TradeValueCurveDiagnostics.viewInvariants`.
`fixedPieIndexed` does not gate published charts. Its rows for them carry the
measured gap, labelled "not gated (published)".

## Source Families And Adjustments

The same transformation rules apply to every source within a family:

| Family | Sources | Native input | Derived output |
| --- | --- | --- | --- |
| Projection-derived | ESPN, CBS ROS, Razzball | The publisher's own per-game projections | DDF value above waivers, priced with starter/bench utilization under the active league settings |
| Published trade charts | CBS, FantasyCalc, FantasyPros, USA Today | The publisher's own trade values | Published/common-scale comparison plus a derived estimate under our valuation assumptions |

ESPN, CBS ROS, and Razzball are exempt from separate `*_adjusted` fixture
sections (JEG-58). Their base sections already apply our DDF methodology to
their own projections. The browser computes their raw value-above-waivers
comparison and utilization-adjusted DDF values separately. Applying the
published-chart adjustment again would double-transform the same input;
adding an alias would create a duplicate output rather than a new estimate.
The three sources must retain their own projection inputs, never substitute
the ESPN projections for CBS ROS or Razzball.

The current published-chart `*_adjusted` sections are fitted transformations
against DDF outputs, not empirical corrections fitted against prior-season
actuals. `build_adjustment_inputs.py` fits position/tier affine cells; its
DDF-native entries use identity targets to support live repricing. Those
entries do not imply a separate projection-source fixture variant.

The VORP translation work (JEG-32/JEG-61/JEG-62) defines the intended next
published-chart transformation: publisher values plus league roster settings
determine the waiver line, publisher-native surplus determines implied
positional weights, and our valuation assumptions determine derived values.
This translation is the VORP vs waivers view's math (the browser's
`translatePublishedVorp`, held to `unified.translate_ranked` by
`tests/test_vorp_translation_js_parity.py`). Since JEG-482 it is no longer
written into the saved Indexed values (JEG-64's `translate_via_vorp.py` stage is
removed): those are the natives times one factor (The Three Views, above).

Every derived output inherits the input's immutable source vintage. Acquisition,
processing, fitting, and promotion times are separate operational timestamps;
none can advance source vintage. Missing cells or unsupported configurations
remain unavailable and must never be presented as an adjusted estimate.

## Published-Chart Configuration Coverage

Table and curve views use the same exact scoring/team configuration key.
Standard is `standard`, half-PPR is `half`, and PPR is `full`, for raw and
adjusted sources alike. No missing configuration borrows a 12-team chart,
another scoring format, or another QB variant. A missing combo disables the
source tile/curve toggle, removes its table column and reference choices,
and yields null values rather than zeros. The source remains listed as
unavailable for the selected scoring/team settings.

**League-settings engine (league-settings-001, JEG-332, 2026-10-06).** Every
published chart (CBS, FantasyPros, USA Today, FantasyCalc) is saved once per
scoring at 12 teams and the standard roster (QB1 RB2 WR3 TE1 FLEX1 BENCH6). At
that setup the chart and table show the saved values unchanged. At any other
team count or roster the browser derives the chart from the saved 12-team
natives with `ValueModel.derivePublishedSetup` (value-model.js,
`league-settings-001/6`, JEG-482): the natives times one factor that matches the
live anchor's total over the chart's players at that setting (the saved factor
when the anchor prices fewer than 40 of them), so the chart keeps its own order.
/1-/5 priced Indexed as value above waivers translated onto our positional
maxes, which reordered players across positions; that translation now feeds
only the VORP vs waivers and Adjusted views. The caption labels these values
derived. The
adjusted series refit live against the ESPN two-tier leg at the chosen setting,
as they already did at 12 teams. A scoring with no saved 12-team setup is still
unavailable and borrows nothing.

**Short charts: waiver line extrapolated from the other charts
(V2-WAIVER-COVERAGE, Jeremy 2026-10-07).** Jeremy: "If needed for
computations, cover them by extrapolating from the average of other charts.
Denote them. Where it's not needed, hide those values." This supersedes the
earlier rule that a chart's waiver line falls back to its last listed value when
it lists no more players at a position than the league rosters
(`insufficient_coverage`), which priced the bottom of a short chart at 0 only
because the list ended (e.g. CBS lists 12 QBs, about 43 RBs, 44 WRs and 17 TEs).
The rule, the same on the server (`unified.impute_extension` /
`translate_ranked(peers=...)`) and in the browser
(`ValueModel.imputeExtension` / `translatePublishedVorp({peers})`), held equal
by `tests/test_vorp_translation_js_parity.py`:

- *Peers.* The other published charts' saved 12-team natives at the same
  scoring (CBS, FantasyCalc, FantasyPros, USA Today minus the chart itself).
- *Mapping into the chart's units.* Per position and peer, one ratio: the sum of
  the chart's natives over the sum of the peer's natives, on the players both
  list among the bottom half of the chart's list (value at or below its median
  listed value; at least 3 such players, else that peer is not used). The
  ratio is fitted on the tail because that is where the line is extrapolated.
- *Imputed native* for a player the chart does not list = the mean, over the
  usable peers that list him, of ratio x peer native, capped at the chart's
  last listed value (a chart that leaves a player out values him at most at
  its last listed value). The extension is ordered by that value and appended
  after the chart's own list.
- *Waiver line.* Only a position where the chart lists no more players than the
  league rosters is extended (re-checked after the flex allocation moves). The
  roster allocation and the waiver line then use the extended list; the line
  is the value at the rostered count (`waiver_method:
  imputed_from_other_charts`, `n_imputed` = how far past the list it reads).
  If no peer covers enough players, the old fallback stays and is labelled
  (`insufficient_coverage`). A chart that is never short translates exactly as
  before.
- *Hidden.* Imputed players exist only for this computation. They never get a
  value in any view: the chart still shows "—" for players it does not list
  (CTL-006 still holds: no unpublished player is displayed).
- *Denoted.* The saved combo's `translation.waiver` /
  `translation.waiver_imputation` record each position's method and the
  peers; the engine exposes it (`getSourceInfo()[].waiverNote` / `.waiver`,
  `TradeValueCurveDiagnostics.publishedDerivation[src].waiver`); the main
  chart's caption line names the charts ("waiver line extrapolated from other
  charts: CBS (QB, RB, WR, TE)") and the v2 Sources and Freshness lists add the
  note to the chart's line.
- *Coupling.* The waiver line (VORP vs waivers and Adjusted) depends on the
  other charts' natives. The saved Indexed values do not (JEG-482); the
  comparison chain re-indexes every published chart in the promoted fixture
  against the promoted ESPN leg and runs the rank guard before the fit
  (`rebuild_comparison_chain.run_reindex_fixture`).

**Other chart views (JEG332-VORP-VIEWS, `published-views-001/1`, 2026-10-07).**
The "VORP vs waivers" and "Adjusted values" views show the saved `vorp_views`
only at the setup they were built for (full PPR, 12 teams, standard roster;
FantasyCalc, FantasyPros, USA Today). At every other scoring, team count and
roster -- and for CBS everywhere -- `ValueModel.derivePublishedViews` derives
them from the saved 12-team natives on the same translation and waiver line, so
a player at or below the waiver line is 0 in both views (Indexed, one factor
on the natives, does not zero anyone; JEG-482):

- *VORP vs waivers*: each player's value above the setting's waiver line in the
  publisher's units, times one factor per chart so the chart's total equals the
  ESPN anchor's total over the players that chart ranks (no re-tiering: the
  publisher's own cross-position valuation is kept).
- *Adjusted values*: players grouped position × starter/bench (starter = the
  setting's dedicated + flex count at the position); each group shares the
  anchor's total for that group in proportion to value above waivers; one
  factor across all published charts at the setting puts the top player at 70.
  The saved run's blend-reference group budgets are not carried to other
  settings.

Jeremy accepted any working setup ("I'm ok with however you set up values to
get the tool working"); the recipe awaits his review (`docs/math-review-agenda.md` MR-04,
MR-05).

The installed USA Today, FantasyPros, and CBS trade charts have only 12-team
native inputs. Their ingestion adapters currently assign `league_teams=12`
(`save_usatoday_references.py`, `save_fantasypros_references.py`, and
`save_espn_cbs_references.py`); no independently acquired 8/10/14-team variants
exist in these fixtures. This is an ingestion/coverage limit, not proof that
the publishers can never offer other formats. We do not duplicate those
native charts into new league identities. Roster-translated estimates (the
engine above) are labeled derived and retain the original native
configuration/vintage.

FantasyCalc saves only its 12-team 1-QB setup since #361 (league-settings-001);
its own 8/10/14-team and 2-QB pages are no longer saved, so derived 8-team
values will not match FantasyCalc's 8-team page (accepted trade-off). Custom roster shape changes reprice derived
values; they do not silently switch the publisher's native QB basis.

Configuration selection never changes source vintage or acquisition/processing
timestamps. Coverage is independent of freshness and validation status.

## Publisher Flex Allocation

The translation module shares one roster allocator (JEG-61). Dedicated
starters are excluded from flex candidates. At each eligible position, the
next `teams * flex_count` ranked players define the potential flex range;
missing candidates contribute zero observed surplus. The weight is dedicated
slots per team times average publisher-native surplus above a preliminary
waiver line. That preliminary line comes from slot-proportional flex plus
the configured bench mix, not a scoring-specific constant.

Flex and bench capacities use deterministic highest-averages (D'Hondt)
apportionment. This guarantees exact integer totals and monotone allocations
for fixed weights as capacity grows, but favors larger weights over smaller
ones. A zero-surplus chart falls back to dedicated-slot proportions. Final
waiver lines and implied weights are recomputed from the resulting roster.
This is a one-pass estimate, not a self-consistent optimization of waiver
lines or proof of actual manager lineup preferences. Different formats can
legitimately round to identical allocations; they are never forced apart.
Custom bench/flex settings are calculation-only until storage grain includes
those settings; database writes with nondefault settings fail closed.

## Week-Over-Week Snapshots (2026-10-08)

Weeks are content weeks (Tuesday flip, `pipelines/nfl_week.py`); game weeks (Thursday flip) are
used only where games matter. For week-over-week comparisons each source has exactly one
snapshot per content week: trade-chart articles use the latest revision of that week's article
saved before the week closes; FantasyCalc uses the first pull at or after Tuesday 12:00 UTC of
the week; projection sources use the newest snapshot dated in the week. A closed week's snapshot
never changes; other versions are kept, not used. Full rule and contract: docs/v2-design-notes.md
"Back-end contract: history".

## DDF Composite Value (JEG-455 / JEG-471 / JEG-479, Jeremy 2026-10-08/09)

The **DDF Composite Value** ("DDF Value" in compact spots) is computed per
league setting (scoring, teams, roster, bench share, position shares), per
view and per week, by these steps. The engine and the Python reference
implement exactly this text.

1. **Inputs.** Seven: `espn`, `cbsros`, `razzball` (our projections) and
   `fantasycalc_adjusted`, `usatoday_adjusted`, `fantasypros_adjusted`,
   `cbs_adjusted` (the four trade charts).
2. **Series per view.** Each input contributes one series in each of the
   Three Views:

   | Input | Indexed | VORP vs waivers | Adjusted values |
   |---|---|---|---|
   | `espn` / `cbsros` / `razzball` | the input itself | `espn_vorp` / `cbsros_vorp` / `razzball_vorp` | the input itself |
   | `<chart>_adjusted` | `<chart>_adjusted` (bias-adjusted) | `<chart>` translated to value above waivers | `<chart>` Adjusted values |

3. **Never an input this week** (even when a reader selects it):
   - *Held*: the source's section, or the derived series' own section, carries
     `validationHold: {reason, week, root, kept_week}` (the pipeline sets it
     on every held section, raw and `*_adjusted`; `root` is the source whose
     engine-vs-reference disagreement caused it) or `promotionHold`. Any
     section carrying one is held. A hold on a source holds every
     series derived from it (`fantasycalc` holds `fantasycalc_adjusted`;
     `espn` holds `espn_vorp`; and so on). Reason: `held: <reason>`.
   - *Not yet published*: a weekly chart whose content week is older than the
     current content week (Tuesday flip, `pipelines/nfl_week.py`). Its prior
     section is the only valid one, and it is not used. Reason: `not yet
     published for week N`. Projections are rest-of-season and always current.
4. **Selected and available.** By default every input left by step 3; a reader
   may choose a subset (at least one). An input whose series has no values at
   this setting (missing section, paused, no saved setup) is left out.
5. **Same inputs in both weeks.** For each remaining input, its series is
   recomputed for the prior week at the same setting and view (the week
   before the week it serves; history rule in "Week-Over-Week Snapshots"). The
   pair is the newest served week among them (`currentWeek`) and the week
   before (`priorWeek`). An input without that prior week, or serving another
   week, is left out of **both** weeks. Today the as-published charts are
   recomputed for earlier weeks in the Indexed view only, so in VORP vs
   waivers and Adjusted values the four charts are left out and those two
   DDF Values average our three projections (MR-17). If no input has a prior
   week (a first week, or no history), the current week uses the inputs from
   step 4 and there is no prior week.
6. **Per player, per week.** The equal-weight mean of the finite values of
   the included series, as the rows carry them ("Published Charts On The
   Rows" below). A series with no value for the player is left out, never
   counted as 0. A 0 a series does carry counts: ESPN's 0 for a player it
   lists at 0 (GAP-025), a leg's 0 at or below its floor, and a fully loaded
   chart's 0 for a player below its floor. When exactly **one** series prices
   the player, the DDF Value is that series' value, flagged low confidence
   ("Only one source prices this player"; Jeremy 2026-10-09, replacing the
   two-value minimum). When none does, it is null with the reason "No source
   prices this player". The prior week uses the same series and the same rule.
   A one-source value counts in tiers like any other.
7. **Δ** = this week's value − the prior week's value, when both exist.
8. **Tier.** Rank by the view's current DDF Value and cut at the league's slot
   counts (the engine's value-based slot fill). No value, no tier.

One DDF Value per view for every comparison column (no leave-one-out).

### Published Charts On The Rows (Jeremy 2026-10-08/09)

What a row carries for a published chart (`<chart>`, its VORP vs waivers and
Adjusted values, and `<chart>_adjusted`), in every view and both weeks:

- **Missing = 0 for a fully loaded chart.** A chart is fully loaded at a
  position when its waiver line there is set by its own list: the waiver
  method of the value-above-waivers translation (`unified.waiver_summary`,
  `ValueModel.publishedWaiverInfo`) is `roster_determined`, i.e. the chart
  lists more players at that position than the league rosters. A player the
  chart does not list there is below its floor: 0 for the chart and 0 for its
  `*_adjusted` series. A listed player a view prices only above waivers (VORP
  vs waivers, Adjusted values) is 0 there too.
- **Too shallow at a position.** When the waiver method is
  `imputed_from_other_charts` (the line is extrapolated from the other
  charts) or `insufficient_coverage` (it sits at the end of the chart's own
  list), an unlisted player has no value: "Chart doesn't list players this
  deep at <pos>".
- **Identity-fallback adjustment cells are blank.** A `*_adjusted` value for a
  player in a cell the fit fell back to identity on (`adjustment-inputs.json`
  `fallback: "identity"`, the starter/bench partition the cells are applied
  on) is null: "Not enough players to fit an adjustment" (fewer than 5 pairs),
  or "Adjustment fit refused (order would invert)" (`non_positive_slope`). It
  is never the unadjusted chart value, and it is not a DDF input for that
  player.
- Every null on a row carries its reason (`missingReasons`).

These are row rules: the pie, scale and view-invariant guards measure the
series as before (`TradeValueCurveDiagnostics` unchanged across the 12-combo
sweep); the rows, and everything read from them (tables, DDF Value, Δ),
carry them.

The engine computes it in the browser (`curve-widget.js`,
`ValueModel.compositeValue`); the API is in `docs/v2-design-notes.md`
"Back-end contract: DDF Value". Open points are `docs/math-review-agenda.md`
MR-17.

## Superflex (JEG332-SUPERFLEX-FLEX, Jeremy 2026-10-08, option A)

A superflex league has a **dedicated superflex slot**: roster key `SUPERFLEX`
(slots per team; the page offers 0 or 1, default 0). It is filled after the
dedicated QB/RB/WR/TE slots and before FLEX, by the best remaining player with
QBs eligible. FLEX stays RB/WR/TE. There is no per-position slot weighting in
the superflex fill -- the `slots[pos] x surplus` flex weight is what kept QBs
out of a QB-eligible flex before (risk register JEG332-SUPERFLEX-FLEX). "Best"
means, per context:

- *Projection series and roles* (ESPN, CBS ROS, Razzball; `projectionRoles`,
  `allocationCounts`): projected points per game, like ordinary FLEX. A lineup
  starts whoever scores more, so on ESPN's 2026 projections every superflex
  slot goes to a quarterback (24 QB starters at 12 teams, 20 at 10).
- *Value-ordered roles* (`roleMap`, the anchor's starter/bench groups): the
  values being split.
- *Published-chart translation* (`vorp_via_roster.allocate_superflex`,
  mirrored by `ValueModel.translatePublishedVorp({superflexCount})`): the
  teams x slots best players left after the dedicated starters by the
  chart's own values (ties: QB, RB, WR, TE, then rank); flex candidates start
  after them. The league-following positional maxes
  (`positionalMaxForSetup`) run the same allocation on our ESPN projections,
  which is where the quarterback scarcity of a superflex league enters every
  derived chart.

**Whose values.** The Three Views say the ranker's assumed setting is the
standard default unless the publisher states otherwise. Where a publisher
publishes superflex / 2-QB values -- FantasyCalc (`numQbs=2`), CBS (2QB QB
column), USA Today (Superflex QB column), FantasyPros (2QB Value for QBs) --
those are the publisher's own superflex numbers and the engine uses them: the
saved 12-team combo's `native_superflex` (same units as `native`, only the
players the publisher prices differently) replaces the 1-QB native for those
players when the roster has a superflex slot (`savedPublishedNative`). Where a
publisher's superflex values are not saved, its 1-QB values go through the
league math above unchanged ("derived from 1-QB values" in
`publishedDerivation[src].superflex`).

**How the publisher superflex values are saved** (GAP-SUPERFLEX-PUBLISHER-VALUES,
2026-10-08). Each producer saves them as `qb_slots = 2` rows beside the 1-QB
rows, in the same bake, `native_value` = the published number:

| Publisher | Column | Positions | Scorings |
| --- | --- | --- | --- |
| FantasyCalc | `numQbs=2`, 12 teams (`pull_fantasycalc_12team.py`) | every position (the whole list is repriced) | its own standard / half / full lists |
| CBS | QB table "2QB" | QB only | one column, reused for the three scorings (IMPLIED, like 1QB-4) |
| USA Today | QB table "SFLEX" | QB only | one column, reused for the three scorings (IMPLIED, like 1QB) |
| FantasyPros | QB table "2QB Value" | QB only | one column, reused for the three scorings (like its base value) |

QB only means the publisher prices no RB/WR/TE differently in superflex: those
players keep their 1-QB numbers from the same chart. A QB the chart prices in
its 2-QB column only (CBS shows "--" in the 1QB columns) has a superflex value
and no 1-QB value. The superflex rows are never reindexed (`value` is NULL
for the reindexed savers; the chart-scale reindex is defined against the 1-QB
ESPN anchor), never counted or dated with the 1-QB rows (the import health and
source-vintage reads take `qb_slots = 1`), and never picked as a week's bake:
the importer carries the superflex rows of the 1-QB snapshot's own week and
bake as `superflex_rows`, the chain carries them (match -> reference ->
section -> reindex -> promote) to the 12-team combo's `native_superflex`, and
a promotion whose publication has none removes the previous one, so an older
superflex column never sits beside a newer week's 1-QB values. With no
superflex slot nothing changes (12-combo sweep, 0 values moved with
`native_superflex` present). Open questions on how the views use them:
`docs/math-review-agenda.md` MR-15.

Saved setup: a roster with a superflex slot is never the saved setup; the
saved 12-team values apply only at SUPERFLEX 0, which reproduces the
pre-superflex engine exactly (`tests/test_superflex.py`, and a 12-combo x
three-view sweep with zero moved values). Versions: `unified-py-jeg62/3`,
`league-settings-001/5`, `published-views-001/3`.

**Not repriced by superflex (open, same as the QB stepper).** The ESPN anchor
is the pipeline's built leg at the reference roster; a roster change reaches
it only through `applyRosterShape`'s top-N average factor, and the raw
value-above-waivers series keep each position's pie at the reference roster.
So with a superflex slot the anchor's QB values barely move (12 teams, full
PPR: QB1 29.5 -> 30.9) while the derived published charts' QB1 reaches 70.
Re-pricing the anchor for roster shape is the open decision in
JEG332-SUPERFLEX-FLEX.

## Two Implementations (JEG-479, Jeremy 2026-10-08)

The math lives in two places on purpose, so one can validate the other: the
browser engine (`curve-widget.js`, `value-model.js`) and the Python reference
(`pipelines/value_reference.py`). Every chain run builds the page, runs the
engine headless and the reference on the same snapshot, and diffs every
value the page shows (`pipelines/value_check.py`): all 14 series and the DDF
Value, in the three views, at 3 scorings x 8/10/12/14 teams on the default
roster and with one superflex slot, plus the DDF Value's prior-week pair.

- *Tolerance* 0.05 on the 0-70 scale: half of the last digit the page shows.
  A value on one side and none on the other always disagrees.
- *Hold.* A disagreeing series holds its source and every series derived from
  it (`value_check.SOURCE_DERIVED`: a published chart with its `*_adjusted`
  series and its VORP vs waivers / Adjusted values views; ESPN, CBS ROS and
  Razzball with their raw VORP vs waivers series). Their fixture sections go
  back to the last published ones, labelled with their own week, and carry
  `validationHold: {reason, week}`; a held series is never a DDF Value input.
  The other sources publish. The hold is released on the first run where the
  two agree.
- *Report.* `output/value-check.json` (schema `value-check/1`, published as
  `modules/value-check.json`) lists every source's verdict, the held series
  and examples of each disagreement.
- *Independence.* The reference composes the series from this document, not
  from the JS. Its arithmetic kernels are separate Python code: the server's
  own published-chart translation (`vorp_translation/unified.py`, which the
  browser ports) and two Python ports of the browser's two-tier and
  value-model helpers (`twotier_reference.py`, `parity/value_model_parity.py`,
  each held to the JS by its own vector check). A JS bug a port copied
  verbatim would not be caught; anything in how the series are assembled
  would.
- *Spec reference (non-blocking).* `pipelines/spec_reference/` is a third,
  clean-room implementation of the two-tier pricing and the value model,
  written from this document and the data files only. `value_check.py` adds
  its comparison as the `spec_reference` section of `value-check.json`. It
  never holds a source. Where this text is silent, its readings are listed in
  `docs/math-review-agenda.md` MR-18.

## Player Universe (JEG-502, Jeremy 2026-10-09)

"All players in the active NFL universe should be available in the search;
even if they are not rostered, on practice squads, etc. The user knowing they
are a 0 is better than the user questioning why they aren't in the tool."

- `players.json` has a row for ESPN's list, every player a current-week chart
  or projection prices, and every active NFL QB/RB/WR/TE.
- Active NFL player, from the Sleeper identity base (refreshed Tue + Thu):
  on an NFL team (active roster, practice squad, injured reserve, PUP or
  another reserve list), or a free agent Sleeper flags active with a news item
  in the 365 days before the pull. Rules and statuses:
  `pipelines/lib/nfl_universe.py`; counts by status in
  `meta.universe.nfl_active` and in the fidelity pulse.
- Practice squad is Sleeper's own status, or inferred for a player on a team
  with status Active and no depth-chart slot (`roster_status_inferred`).
- A universe player nothing prices has ESPN "absent" and no projection; the
  row rules give him 0 where a chart is fully loaded and a reason elsewhere.
  `unpriced_reason` names his status. A player not yet on the players table
  is keyed 1,000,000 + his Sleeper id (`identity: "sleeper"`).

## Detailed Rule Owners

- `docs/pipeline-rules.md` owns fail-closed identity, null/zero handling,
  freshness, public copy, adjusted-curve rules, and promotion gates.
- `docs/modular-pipeline.md` owns the source-data -> reference-compute ->
  dashboard-build -> frontend/site workflow.
- `docs/risk-register.md` owns known methodology gaps and decisions still
  needing evidence.
- `docs/math-review-agenda.md` collects every open math and logic question
  (MR-01...) for the full math review, with dependencies, measured options
  and the order to decide them. Add new questions there rather than settling
  them one at a time.

## Validation Principle

Pie totals alone are insufficient. Curve shape must be checked against what a
reader actually sees: positional peaks (where each position's curve starts),
shared-player totals, and table/curve consistency. Publisher shape
disagreement with the ESPN anchor is the product, not a defect: the
peak-vs-anchor "source-scale agreement" check on the published charts was
retired 2026-10-08 (GAP-026).

Two two-tier rules the engine and every leg builder share (server/browser
parity, 2026-10-08):

- The ESPN tier (Starter / Bench / Waiver) shown in every table is the ESPN
  line's own roster: the two-tier pool for the active scoring and team count.
  A player tiered Waiver has no ESPN value.
- When the requested bench share sits below a position's feasible window, the
  share used is one percentage point inside the window's lower edge (halving
  if the window is narrower), never the edge itself, where the bench rate is
  0 and the top starter takes an outsized share of the position pie.

## Refresh Cadence (2026-10-08)

Sources are re-read as often as they change, not on a blind timer. A cheap
probe (`pipelines/source_probe.py`, `source-probe.yml`) fingerprints each source
and the full scrape plus numbers check runs only when the fingerprint moved,
when the last successful scrape is older than the source's max age (20 h;
FantasyCalc 24 h), or when the probe could not read the source. The probe never
changes a number itself: every value still comes from the full, fail-closed
ingest and the rebuild chain's review and `make validate`.

| Source | Change signal | Probe cadence (UTC) | Full ingest when |
| --- | --- | --- | --- |
| FantasyCalc | hash of the three 12-team 1-QB lists (API has no ETag) | hourly | changed and ≥ 6 h since the last save, or 24 h; plus fixed Tue + Fri 13:07 saves |
| USA Today | the week's article, found by the ingest's own discovery, and its `<lastmod>` in USA Today's monthly sitemap | every 3 h Mon–Thu, 00:35 + 12:35 Fri–Sun | changed, or 20 h |
| FantasyPros | the week's article, found by the ingest's own discovery: JSON-LD `dateModified` + tables hash | as USA Today | changed, or 20 h |
| CBS | the week's article, found by the ingest's own discovery, on www.cbssports.com: `dateModified` + tables hash | as USA Today | changed, or 20 h |
| ESPN | hash of the weekly projection blocks the puller sums | every 4 h, 03:25–23:25 | changed, or 20 h |
| CBS rest of season | tables hash of the four stats pages | every 4 h | changed, or 20 h |
| Razzball | the four pages' own "Updated:" stamps + tables hash | every 4 h | changed, or 20 h |

An ingest the probe dispatched acknowledges its fingerprint on success; one
that fails is retried at the next probe slot (after 50 min), at most four times
per fingerprint, then once per max age. When an acknowledged fingerprint is new,
the ingest dispatches the rebuild chain; the chain also runs when the hourly
vintage check sees a new content date and once a day (11:45, with the ESPN
anchor bake). Which saved version is a source's week-N snapshot for Δ is the
week-over-week rule
("Week-Over-Week Snapshots").
