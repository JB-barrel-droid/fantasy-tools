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

Value above waivers and DDF values follow the user's league-settings inputs
(teams, scoring, roster). There is no cap at the anchor's top value: a
publisher whose implied weighting puts its top player above ours shows that.
CBS ROS and Razzball are matched to the ESPN anchor by total only (Jeremy,
2026-10-08): one factor makes their total over the players they share with ESPN
equal ESPN's, so each keeps its own weighting across positions and its own top
values. Aligning each position's top to ESPN's applies only to the fitted
`*_adjusted` series.

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
The saved 12-team published values are this translation for players above the
waiver line (JEG-64, `translate_via_vorp.py`) and 0 for players the translation
prices at or below it; only a player the translation cannot identify keeps the
flex-aware pie value as a fail-safe. The comparison chain computes the
translation from the natives it is promoting (`--translation natives`), so the
saved values are always the translation of the saved natives
(`tests/test_vorp_translation_js_parity.py` `stored_drift_problems`, risk
register JEG332-STORED-DRIFT). The browser runs the same translation at every
other league setting (see "League-settings engine" below).

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
inputs with `ValueModel.derivePublishedSetup` (value-model.js): the
value-above-waivers translation (`translatePublishedVorp`, an exact port of
`unified.translate_ranked`, held to it by `tests/test_vorp_translation_js_parity.py`)
runs at the chosen setting for every player above that setting's waiver line;
every other player is worth 0 (value above waivers is zero by definition;
`league-settings-001/3`, 2026-10-07 -- it replaced the server's fail-safe value,
which the saved 12-team values still carry, risk register
JEG332-BELOW-WAIVER-SAVED). The caption labels these values derived. The
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
- *Coupling.* A chart's saved values now depend on the other charts' natives,
  so the comparison chain re-translates every published chart in the promoted
  fixture after the per-source stages (`rebuild_comparison_chain.run_retranslate`)
  before the fit.

Because a chart's translated value is value above waivers scaled so its top
player sits at our positional max, a lower waiver line raises the chart's
lower and middle values a little as well as pricing the bottom; its top value
does not move.

**Other chart views (JEG332-VORP-VIEWS, `published-views-001/1`, 2026-10-07).**
The "VORP vs waivers" and "Adjusted values" views show the saved `vorp_views`
only at the setup they were built for (full PPR, 12 teams, standard roster;
FantasyCalc, FantasyPros, USA Today). At every other scoring, team count and
roster -- and for CBS everywhere -- `ValueModel.derivePublishedViews` derives
them from the saved 12-team natives on the same translation and waiver line as
Indexed, so a player at or below the waiver line is 0 in all three views:

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
get the tool working"); the recipe awaits his review.

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

## Detailed Rule Owners

- `docs/pipeline-rules.md` owns fail-closed identity, null/zero handling,
  freshness, public copy, adjusted-curve rules, and promotion gates.
- `docs/modular-pipeline.md` owns the source-data -> reference-compute ->
  dashboard-build -> frontend/site workflow.
- `docs/risk-register.md` owns known methodology gaps and decisions still
  needing evidence.

## Validation Principle

Pie totals alone are insufficient. Curve shape must be checked against what a
reader actually sees: positional peaks, source-scale agreement, shared-player
totals, and table/curve consistency.

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
| USA Today | the week's article and its `<lastmod>` in USA Today's monthly sitemap | every 3 h Mon–Thu, 00:35 + 12:35 Fri–Sun | changed, or 20 h |
| FantasyPros | the week's article: JSON-LD `dateModified` + tables hash | as USA Today | changed, or 20 h |
| CBS | the week's article on www.cbssports.com: `dateModified` + tables hash | as USA Today | changed, or 20 h |
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
