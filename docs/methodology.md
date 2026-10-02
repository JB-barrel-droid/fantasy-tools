# Methodology

This file is the required methodology entrypoint. It summarizes the stable
contract and points to the detailed rules that own each section.

## Trade-Value Contract

The dashboard compares source values on a common, ESPN-anchored fixed-pie scale.
The public chart should answer: how do current source trade values differ after
identity matching, per-position reindexing, and shared-scale normalization?

The stable rules are:

- Identity resolves to canonical numeric `player_key`; names are display only.
- Source values stay native until the reference-compute step reindexes them.
- Missing source values stay absent/null and display as unavailable.
- Genuine source zeros stay zero.
- Published/direct charts are compared against the built ESPN indexed leg.
- Raw ESPN value above waivers is a separate comparison mode, not the indexed
  trade-value anchor.
- Adjusted source projects are derived estimates from raw source values plus
  versioned adjustment cells.

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
The new translation module is not proof that the live chart has switched.
Until its inputs, configuration behavior, validation, and frontend integration
are complete, the existing fitted path remains the current implementation.
Once integrated, translation should replace that derived path for all four
published-chart sources rather than stack another adjustment on top of it.

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

The installed USA Today, FantasyPros, and CBS trade charts have only 12-team
native inputs. Their ingestion adapters currently assign `league_teams=12`
(`save_usatoday_references.py`, `save_fantasypros_references.py`, and
`save_espn_cbs_references.py`); no independently acquired 8/10/14-team variants
exist in these fixtures. This is an ingestion/coverage limit, not proof that
the publishers can never offer other formats. We do not duplicate those
native charts into new league identities. A future roster-translated estimate
must be labeled derived and retain the original native configuration/vintage.

FantasyCalc currently has 8/10/12/14-team native charts for all three scoring
formats and separate `qb1`/`qb2` grains (32, not 24, fixture combos). These
views explicitly display the 1-QB publisher basis and select only `qb1` for
both raw and adjusted charts. `qb2` remains a distinct acquired input, not a
fallback for a missing `qb1`. Custom roster shape changes reprice derived
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
