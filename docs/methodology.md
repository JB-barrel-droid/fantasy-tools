# Methodology

This file is the required methodology entrypoint. It summarizes the stable
contract and points to the detailed rules that own each section.

## Why

`docs/manifesto.md` states the project's reasoning: player value splits into
market, fundamental (value above waivers, usable production) and portfolio
value, and decisions come from the gaps between them. Judge features against it.

## Value Pipeline (source-neutral, 2026-10-09)

**Status.** Spec for JEG-508, written from Jeremy's decisions of 2026-10-09
(JEG-508, JEG-479 comment "value pipeline order (confirmed)", JEG-497,
JEG-499). Those decisions are binding. This section governs every value the
site shows. It supersedes the paragraphs below that are marked
**Superseded (JEG-508)**. Until the implementation PRs merge, those
paragraphs still describe what the engine does; they are kept, not deleted, so
the before/after is reviewable. Three implementations are written from this
text independently: the engine (`curve-widget.js`, `value-model.js`), the
Python reference (`pipelines/value_reference.py`) and the clean-room spec
reference (`pipelines/spec_reference/`). They must agree to 0.05 on every
value (`value_check`) before anything merges. Where Jeremy has not decided
something, the step uses the recommended option of an open choice (OC-1 to
OC-8, listed at the end). Changing an answer changes only the step that names
it.

**Jeremy's rules this implements.**

- Pipeline order. Each source goes from its native values to implied value
  above waivers (VORP). Every source then uses the same logic (flex, bench
  share, league settings) to get from VORP to Adjusted values. DDF Value is
  the equal-weight mean of Adjusted values only. Indexed exists only for
  display and never feeds DDF.
- "Build the weights at the source level based on VORP and league settings
  and size logic. Then use the average weights at the DDF level; generally
  speaking do as much work as possible at the source level before
  aggregation/averages."
- A fixed league pie for each league setting. It is split by the DDF weights,
  and every source's Adjusted values sum to it. "You will need to fill in for
  trade value charts where they have not scored enough players to fill out
  the pie."
- "ESPN has no favored position in any part of the logic or dashboard."

### VP-0 Definitions and conventions

- **Positions** are QB, RB, WR, TE. Where a tie is broken by "position
  order", it is this order.
- **League setting L.** scoring; teams `T`; dedicated slots per team `D_p`;
  flex slots per team `F` (RB/WR/TE eligible); superflex slots per team `SF`
  (QB/RB/WR/TE eligible); bench slots per team `B` (default 6); bench share
  `bs` (default: none, which means source-implied; OC-2); reader position
  shares (default: none).
- **Sources and natives.**
  - *Projections* (`espn`, `cbsros`, `razzball`). Native = the source's own
    projected points per game at the scoring.
  - *Trade charts* (`cbs`, `fantasycalc`, `fantasypros`, `usatoday`). Native
    = the publisher's trade value from the saved 12-team list at the scoring.
    With `SF >= 1`, the saved `native_superflex` replaces the 1-QB native for
    the players it covers ("Superflex", below).
  - A source *lists* player `i` when it has a finite native for him. His
    position comes from the naming table (`player_key`).
- **Sort order.** Within a position: native descending, then `player_key`
  ascending (numeric). "Rank" is the 1-based position in that order.
- **Arithmetic.** IEEE doubles. No intermediate rounding anywhere. Display
  rounds to one decimal. Ties mean exact equality of doubles. Sums run in sort
  order.
- **Constants.** `BENCH_MIX_12 = {QB 10, RB 27, WR 33, TE 10}`.
  `IMPUTE_MIN_FIT = 3`. `PIE_PER_STARTING_SLOT = 28` (OC-1).
- **Week.** Everything below runs once per content week. The prior week runs
  the same steps on the prior inputs (VP-8).

### VP-1 The included set

1. A source is **eligible** this week when all three hold:
   - it is not held (`validationHold` or `promotionHold` on its section);
   - it is not unpublished (a weekly chart whose content week is older than
     the current content week);
   - it has values at `L` (the section exists and the scoring is saved).
2. **Included set `I`** = the eligible sources that also have a prior-week
   snapshot. If no eligible source has one (a first week, or no history), `I`
   = the eligible sources and there is no prior week.
3. `I` alone drives the DDF weights (VP-4), the imputation peers (VP-2.4), the
   DDF versions (VP-6.3) and the mean points per game (VP-7). The same `I` is
   used for both weeks.
4. A source outside `I` (held, unpublished, no prior week) is still shown from
   its kept section. It goes through VP-2, VP-3, VP-5 and VP-6.4 against the
   same pie and DDF weights, so its numbers stay on the page's scale. It
   contributes nothing to weights, peers or DDF.
5. The reader's input selection (`setCompositeInputs`) filters only the DDF
   averaging (VP-6.3). It never changes `I`, the weights, or any source's
   values.
6. ESPN has no special role anywhere. A missing ESPN is dropped like any other
   source, and the page renders with any non-empty `I`.

### VP-2 Native to value above waivers (per source, per position)

Every source runs this step in its own units: points per game for
projections, trade value for charts. Charts and projections use the same
rules.

1. **Lists.** Build each position's listed players in sort order.
2. **Roster allocation `alloc(lists)`** (the "size logic"):
   - a. Dedicated: `d_p = T x D_p`.
   - b. Superflex: candidates are every player ranked below `d_p` at any
     position. Take the `T x SF` best, by native descending, then position
     order, then rank. `sf_p` = the number taken at `p`.
   - c. Flex: candidates are the players ranked below `d_p + sf_p` at
     RB/WR/TE. Take the `T x F` best, in the same order. `fx_p` = the number
     taken at `p` (OC-4).
   - d. Bench: `b_p` = D'Hondt apportionment of `round_half_up(T x B)` seats
     over `BENCH_MIX_12`. Each seat goes to the position with the largest
     `weight / (seats + 1)`, with ties going to position order. The bench
     does not depend on the source.
   - e. Starters `S_p = d_p + sf_p + fx_p`. Rostered `N_p = S_p + b_p`. If the
     candidates run out, the untaken slots stay empty.
3. **Waiver line `w_p`**, read from the work list (the listed players, plus
   the imputed ones when 4 extends the position):
   - If the work list is longer than `N_p`: `w_p` = the value at 0-based index
     `N_p`. The method is `roster_determined` when `N_p` < the number listed.
     Otherwise it is `imputed_from_other_charts`, with
     `n_imputed = N_p - listed + 1`.
   - Else, if anyone is listed: `w_p` = the last *listed* value. The method is
     `insufficient_coverage`.
   - Else: `no_players`. The source does not price `p`.
4. **Short positions: filling the pie.** A position is short when
   `listed_p <= N_p`. Its list is extended with imputed players:
   - *Peers*: the sources in `I` of the same family, other than the source
     itself. They are the charts for a chart and the projections for a
     projection. Peers use their listed natives (with the superflex overlay at
     `SF >= 1`), never their own extensions.
   - *Fit set*: take the source's listed values in sort order. `last` = the
     final value. `median` = the value at 0-based index `floor(n / 2)`. The
     tail is the listed players with value `<= median`.
   - *Ratio*: for each peer, in source-key order, `shared` = the tail players
     the peer lists. If `|shared| < IMPUTE_MIN_FIT`, or the peer's sum over
     `shared` is `<= 0`, skip that peer. Otherwise
     `ratio = sum(own natives over shared) / sum(peer natives over shared)`.
   - *Imputed native* for each player some usable peer lists and the source
     does not = `min(last, mean over those peers of ratio x peer native)`.
     The imputed players are sorted by value descending, then key ascending,
     and appended after the listed players.
   - *Loop*: run `alloc` on the work lists. Extend every position that is
     short, not yet extended and has imputed players. Repeat until nothing
     new is extended, which takes at most 4 passes. Imputed players are
     superflex and flex candidates like listed ones.
   - Imputed players exist only to fill the pie. They are never displayed and
     never get a row (CTL-006). The method and peers are reported (VP-11).
5. **Starter line `l_p`** = the work-list value at 0-based index `S_p` (the
   first non-starter) if it exists, else `w_p`. Then `l_p = max(l_p, w_p)`.
6. **Per player** on the work list, listed or imputed:
   - value above waivers `v_i = max(0, x_i - w_p)`;
   - bench slice `bsl_i = max(0, min(x_i, l_p) - w_p)`, the part of his
     surplus that any rostered player at `p` provides;
   - starter slice `ssl_i = max(0, x_i - l_p)`, the premium over the first
     non-starter;
   - `v_i = bsl_i + ssl_i` exactly.
   - Display role: starter if rank `<= S_p`, bench if `<= N_p`, else waiver.
     The role is shown but does not price (OC-3).

### VP-3 Per-source implied weights (8 groups)

1. **Group totals** over the work list, imputed players included:
   `G_s[p, starter] = sum(ssl_i)` and `G_s[p, bench] = sum(bsl_i)`. That makes
   8 groups, position x starter/bench. Flex and superflex are accounted for
   because their winners count in `S_p` at their own positions, which moves
   `l_p`.
2. `G_s` = the sum of the 8. If `G_s = 0`, the source has no implied weights.
   It is left out of VP-4, and its VORP vs waivers and Adjusted values are 0
   for every listed player.
3. **Weights**: `w_s[g] = G_s[g] / G_s`. They are unit-free, so a chart and a
   projection are comparable.
4. **Bench share override** (OC-2), only when the reader has set `bs`:
   `Bsum_s = sum over p of w_s[p, bench]`. If `0 < Bsum_s < 1`, the bench
   groups become `w x bs / Bsum_s` and the starter groups
   `w x (1 - bs) / (1 - Bsum_s)`. Otherwise the weights are unchanged. With no
   override, the slider shows the source-implied share (VP-4 sum of bench
   groups).

### VP-4 DDF weights

1. `Wraw[g]` = the mean of `w_s[g]` over the sources in `I` that have weights
   and do not have `no_players` at `g`'s position.
2. `W[g] = Wraw[g] / sum(Wraw)`.
3. **Reader position shares** (BE-2 / MR-16), when set:
   `W[p, r] = W[p, r] x share_p / (W[p, starter] + W[p, bench])`, skipped
   where that sum is 0. Applied after VP-3.4.
4. Every source in `I` counts once (four charts and three projections, so 7
   at full strength). There is one weight set per league setting and week
   (OC-6).

### VP-5 Fixed league pie and Adjusted values

1. **Pie** (OC-1): `Pie(L) = 28 x T x (sum of D_p + F + SF)`, which is 28 per
   starting slot. It depends on neither scoring nor bench. At the default
   roster (8 starters) it is 1,792 / 2,240 / 2,688 / 3,136 at 8 / 10 / 12 /
   14 teams, and 3,024 at 12 teams with one superflex slot. Today's 12-team
   anchor total is about 2,636, so the top player lands near 70 at the
   default, but nothing pins him there.
2. **Budgets**: `b[g] = Pie x W[g]`.
3. **Unfunded groups** (OC-5): when a source has `G_s[g] = 0` while
   `b[g] > 0`, and the other group at the same position has `G_s > 0`, the
   budget moves to that other group. If both are 0 (the source has no surplus
   at `p`), the budget stays unpaid and is reported in `unfundedGroups`.
4. **Rates**: `r_s[g] = b'_s[g] / G_s[g]`, or 0 where `G_s[g] = 0`.
5. **Adjusted value**:
   `A_i = r_s[p, bench] x bsl_i + r_s[p, starter] x ssl_i`.
   - Each source's group totals equal the budgets, and its total equals the
     pie, both counted over the work list.
   - `A` is continuous and non-decreasing in the native, so a source's own
     order within a position never inverts.
   - Multiplying a source's natives by a constant changes nothing.
   - Imputed players' Adjusted values fill the pie and stay hidden. So a short
     chart's displayed total is the pie minus its imputed players' share.
6. **VORP vs waivers (display)**: `V_i = v_i x Pie / G_s`. That is one factor
   per source, so every source's total over its work list equals the pie: the
   same exact scale, with each source keeping its own weighting.

### VP-6 Rows, DDF Value and Indexed

1. **Rows.** Every player any source lists, held sources included, gets a
   row. This includes every player on ESPN's list (JEG-496).
2. **Row value of source `s` for player `i`**, in any view:
   - `s` lists `i`: the view's value (`A_i`, `V_i`, or Indexed from 4).
   - A chart that does not list `i`, where its method at `p` is
     `roster_determined`: **0** in every view. He is below a fully loaded
     chart's floor.
   - A chart that does not list `i`, where the method is anything else:
     null, "Chart doesn't list players this deep at <pos>".
   - A projection that does not list `i`: null, "<label> doesn't project this
     player".
   - `no_players` at `p`: null, "<label> doesn't price <pos>".
3. **DDF Value, three versions** (JEG-497). Each is one number across every
   view and tab.
   - `ddf_value` (blended): the sources in `I`.
   - `ddf_value_charts`: the charts in `I`.
   - `ddf_value_projections`: the projections in `I`.

   Each is further narrowed by the reader's selection. Value = the
   equal-weight mean of the numeric Adjusted row values of those sources.
   Zeros count; nulls are left out. Exactly one value gives that value with
   `lowConfidence` ("Only one source prices this player"). None gives null
   ("No source prices this player"). A held or unpublished source is never an
   input.
4. **Indexed** (JEG-499, display only). For each chart `c`, `shared` = the
   players `c` lists who have a numeric blended DDF Value, zeros included
   (OC-8). Then
   `f_c = sum(ddf_value over shared) / sum(native_c over shared)` and
   `Indexed_i = native_i x f_c`.
   - It is one positive factor, so the chart's own order survives exactly
     (rank guard).
   - If the native sum is `<= 0`, or `shared` is empty, Indexed is null:
     "Not enough shared players to index".
   - Unlisted players follow rule 2.
   - Projections have no published scale. In the Indexed tab they show their
     Adjusted values (OC-7).

### VP-7 Slot filling, zones, tiers, ranking

1. **Mean points per game** `m_i` = the mean of the natives of the
   projections in `I` that list `i`. Missing values are left out, never
   counted as 0.
2. **Slot fill** = `alloc` (VP-2.2) on the `m` lists. That gives `S*_p` and
   `N*_p`. The zones on the curve sit at these counts. If `I` has no
   projection, slot fill runs on the blended DDF Value instead.
3. **Tier** (`ddfTier`). Within a position, rank by blended DDF Value
   descending, then `m` descending (missing last), then key ascending.
   - DDF Value 0: waiver.
   - Rank `<= S*_p`: starter.
   - Rank `<= N*_p`: bench.
   - Otherwise waiver.
   - No DDF Value: no tier.
4. **Default ranking, lock and curve**: blended `ddf_value`, descending, then
   key ascending. The other two versions can be chosen like any series.
5. No source is required to render. With an empty `I`, every DDF Value is null
   ("No source available this week") and Indexed is null. The page still
   renders.

### VP-8 Weeks and the change since last week

1. The prior week runs VP-2 to VP-7 on the prior inputs:
   - each source in `I` uses its prior-week snapshot ("Week-Over-Week
     Snapshots");
   - the same `L`, the same `I` and the same pie;
   - prior-week peers.

   That gives prior weights, prior Adjusted values, prior DDF versions and a
   prior Indexed factor. Nothing from the current week enters the prior week.
2. The change is the current value minus the prior value, for each DDF
   version, when both exist. It moves when either the source or the average
   weights moved. That settles MR-07 as option (b).

### VP-9 How each league setting enters

| Setting | Where it enters |
| --- | --- |
| Scoring | Which natives: each chart's list at that scoring; points per game at that scoring. |
| Teams `T` | Allocation counts (VP-2.2), and with them the waiver and starter lines; the pie. |
| Dedicated slots, flex | Allocation; the pie. |
| Superflex `SF` | Allocation, where QBs compete for the slot on each source's own values; the chart natives' superflex overlay; the pie. |
| Bench per team `B` | Bench seats, so `N_p` and the waiver line. Not the pie (OC-1). |
| Bench share `bs` | Only when the reader sets it (VP-3.4). |
| Reader position shares | Only when the reader sets them (VP-4.3). |

The charts' saved lists are 12-team lists. At every `T` and roster the same
natives are deconstructed at the reader's setting. That is the publisher's
valuation applied to the reader's league, and it is labelled derived, as
today.

### VP-10 Retired, and what replaces each

| Retired | Replaced by |
| --- | --- |
| Per-player `*_adjusted` fit: `build_adjustment_inputs.py` position/tier affine cells | Each chart's own Adjusted values (VP-2 to VP-5) |
| `adjustment-inputs.json` and its identity-fallback cells ("Not enough players to fit an adjustment", "Adjustment fit refused") | Nothing. There is no fit, so there are no fallback cells and no blank-cell rule |
| `refitLiveCells` / `buildLiveAdjustedMap` (live refit against the ESPN two-tier leg; GAP-ADJ-CLIP-ZERO's clip) | VP-5. No clip: values are non-negative by construction |
| `shapeToAnchorPeaksThenSharedTotal` (per-position peak pin, then shared total) | VP-5. Group totals equal pie x DDF weights by construction |
| CBS ROS / Razzball level-matched to ESPN (option C, total only) | Each projection's own VP-2 to VP-5 |
| The ESPN top = 70 unit: two-tier `70 / max`, `OUR_MAX`, `positionalMaxForSetup`, the Adjusted view's 70 factor | The fixed league pie (VP-5.1) |
| ESPN group totals as DDF weights ("the anchor's total for that group") | The average of the source weights (VP-4) |
| ESPN-measured positional pies (`espn_pies.json`) and the two-tier glide as the projections' value | VP-2.6 slices and VP-5 rates. The bench share keeps its meaning as the share of the pie paid on bench slices, without the softplus glide |
| Indexed factor against the ESPN leg (`order_preserving_rescale`, `derivePublishedSetup`'s live-anchor factor, the 40-player fallback) | VP-6.4 against blended DDF Value |
| Default lock and curve on ESPN; ESPN tier (V2-TIER-VS-ESPN-LEG) | VP-7.3 / VP-7.4 on DDF Value |
| Slot filling and zones by ESPN points per game | VP-7.1 / VP-7.2, the mean of the included projections |
| ESPN as the only source whose absence refuses to render | VP-1.6 / VP-7.5 |
| Saved `vorp_views` (`build_imputed_vorps.py`) at the 12-team setup | VP-2 to VP-5 at every setting |
| One DDF Value per view (`ddfByView`), and the charts dropping out of two views' DDF (MR-17) | VP-6.3, one number per version in every tab |
| D'Hondt surplus-weighted flex with a preliminary waiver line ("Publisher Flex Allocation") | VP-2.2c greedy best-remaining (OC-4). The bench D'Hondt stays |
| Copy that calls ESPN the anchor or the core weight | DDF Value is the core value (JEG-499) |

### VP-11 Front-end contract (keeps existing names where the meaning is unchanged)

- **Series in `row.values`**, in the active tab:

  | Key | Indexed tab | VORP vs waivers tab | Adjusted values tab |
  | --- | --- | --- | --- |
  | `cbs`, `fantasycalc`, `fantasypros`, `usatoday` | Indexed (VP-6.4) | `V` (VP-5.6) | `A` (VP-5.5) |
  | `espn`, `cbsros`, `razzball` | `A` (OC-7) | not drawn | `A` |
  | `espn_vorp`, `cbsros_vorp`, `razzball_vorp` | not drawn | `V` | not drawn |
  | `ddf_value`, `ddf_value_charts`, `ddf_value_projections` | the same in every tab | | |

  `fantasycalc_adjusted`, `usatoday_adjusted`, `fantasypros_adjusted` and
  `cbs_adjusted` are retired. The front-end change that stops reading them
  ships in the same release.
- **DDF row fields.** These keep their names and now describe blended
  `ddf_value`: `ddfReason`, `ddfCount`, `ddfSources` (source keys, such as
  `fantasycalc`), `ddfLowConfidence`, `ddfConfidenceNote`, `ddfPrior`,
  `ddfPriorCount`, `ddfPriorLowConfidence` and `ddfTier`.
  - New: `ddfByVersion: {blended, charts, projections}`. Each entry is
    `{value, count, sources, reason, lowConfidence, prior, priorCount,
    priorLowConfidence}`.
  - `ddfByView` is retired.
  - `missingReasons` keeps its texts, minus the two identity-fallback
    reasons and "Adjustment data failed to load". It gains "<label> doesn't
    price <pos>", "Not enough shared players to index" and "No source
    available this week".
- **Composite API.** `getCompositeInputs([version])` and
  `getCompositeValues([version])`, where `version` is `"blended"` (default),
  `"charts"` or `"projections"`.
  - The former `view` argument is accepted and ignored.
  - `inputs` and `series` are source keys.
  - `getSourceInfo({includeComposite: true})` lists all three DDF keys.
  - `setLockOrder` accepts each of them.
  - `getPriorWeek` / `getWeekValues` accept each of them.
- **Diagnostics.** New `TradeValueCurveDiagnostics.valuePipeline` =
  `{version: "value-pipeline/1", setting, pie, included, excluded:
  [{key, reason}], ddfWeights: {"POS|starter"...}, slotFill: {pos: {starters,
  rostered}}, sources: {key: {family, totalVorp, groups, weights, rates,
  unfundedGroups, vorpFactor, indexedFactor, positions: {pos: {method,
  waiver, starterLine, starters, rostered, listed, nImputed, peers}}}}}`.
  The math inspector reads it.
- **Copy.** "DDF Value", "DDF Value · trade charts", "DDF Value ·
  projections". No copy calls ESPN the anchor.

### VP-12 Validation

- `value_check` compares, per setting:
  - the 7 sources in each view they appear in (VP-11);
  - the three DDF versions, current and prior;
  - `ddfWeights` and the pie.

  Tolerance is 0.05 on values and 1e-4 on weights.
- **Worked example.** `tests/fixtures/value_pipeline_worked_example.json`
  holds the inputs, every intermediate value and the expected outputs for a
  2-team league (hand-checkable; summary below). Each implementation must
  reproduce it to 1e-6 before it runs on live data.
- **Before publishing**, run the 12-combo sweep (CLAUDE.md), check where each
  position's curve starts, and show Jeremy the before/after on live data
  (JEG-508 plan step 3).

### Worked example (tests/fixtures/value_pipeline_worked_example.json)

**Setting.** 2 teams, QB1 RB1 WR1 TE1 FLEX1, no superflex, bench 2 per team,
bench share source-implied.

- Bench seats: `round(2 x 2) = 4`, apportioned by D'Hondt over
  `BENCH_MIX_12` in the order WR, RB, WR, RB. That gives RB 2 and WR 2.
- Pie = 28 x 2 x 5 = **280**.

**Sources.**

- Projections `p1` and `p2`, and charts `c1` and `c2`, are included.
- `c3` is held. Its natives are exactly 10 x `c1`.
- `p2`'s flex has a tie at 10.0 between RB Foxtrot and WR Oscar. Position
  order gives the RB the slot.

**Allocation and waiver lines.** Every source gets RB 3 starters / 5 rostered
and WR 3 / 5.

- `c2` lists only 5 WRs, so it is short at WR.
- Its tail (values at or below the median, 35) is WR November, Oscar and
  Papa. `c1` lists all three, so `ratio = (35 + 20 + 12) / (40 + 22 + 14) =
  67/76`.
- That imputes WR Quebec at `9 x 67/76 = 7.934211` and WR Romeo at 4.407895.
- `c2`'s WR waiver line is Quebec's 7.934211 (`imputed_from_other_charts`,
  `n_imputed = 1`). Quebec and Romeo get no value on `c2`'s rows.

**Group totals (`G`) and weights.**

| Source | QB starter | RB starter | RB bench | WR starter | WR bench | TE starter | `G_s` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| p1 | 12 | 15 | 18 | 16 | 13 | 10 | 84 |
| p2 | 11 | 18 | 28 | 10 | 27 | 12 | 106 |
| c1 | 35 | 125 | 62 | 104 | 57 | 51 | 434 |
| c2 | 32 | 140 | 52 | 105 | 52.328947 | 54 | 435.328947 |
| **DDF weight `W`** | 0.100196 | 0.239499 | 0.185186 | 0.191411 | 0.165255 | 0.118453 | 1 |

QB bench and TE bench are 0 for everyone: no bench seats, so the starter line
is the waiver line.

**Hand-check one value.** `p1`, RB Delta: native 18, waiver 5 (RB Hotel,
index 5), starter line 9 (RB Juliet, index 3).

- Bench slice = 4 and starter slice = 9.
- Rates: `280 x 0.185186 / 18 = 2.880670` and
  `280 x 0.239499 / 15 = 4.470653`.
- `A = 4 x 2.880670 + 9 x 4.470653 =` **51.759**.
- Across the four included sources RB Delta is 51.759 / 44.641 / 49.262 /
  52.681, so blended DDF = **49.586**, charts 50.971 and projections 48.200.

**What else it pins.**

| Case | Player | Result |
| --- | --- | --- |
| Missing from a fully loaded chart = 0 | RB Hotel on `c2` | 0, and it counts: blended 3.106 over 4 sources |
| One-source low confidence in one version only | RB Juliet (only `p1` projects him) | Projections version 11.523, low confidence. Blended 3.841 over 3 (the full charts give 0). `p2` is null |
| Short chart, unlisted | WR Quebec on `c2` | null; charts version 0.0 from `c1` alone, low confidence |
| A held source is shown but never counts | `c3` | Adjusted and Indexed identical to `c1`'s; not in any weight or DDF |
| Indexed | `c1` | `f = 277.119339 / 592 = 0.468107`, so RB Delta's 90 shows 42.130 |
| Indexed | `c2` | `f = 0.500938`. RB Kilo (`c2` only, below its waiver line) shows 1.503 Indexed and 0 Adjusted |
| Tiers | slot fill on mean points per game | QB 2 / RB 3 + 2 / WR 3 + 2 / TE 2. RB Hotel (DDF 3.106, RB rank 6) is waiver |
| Bench share override 0.10 | `variant_bench_share_0_10` | weights and blended DDF |

### Expected-starts value (JEG-521, 2026-10-09): the proposed answer to OC-2 and OC-3

**Status.** Proposed by the JEG-521 math work, waiting on Jeremy (decision
`es-value-001` in `docs/decisions.md`, OC-9 below). Nothing here is live. When
approved it replaces VP-2.6 and lands through JEG-508's pipeline with the
Python reference and the spec reference on the same branch (`value_check` at
0 disagreements), never as a parallel edit. The measured before/after is
`output/expected-starts-before-after.md`, produced by
`pipelines/expected_starts_model.py` on the Week 5 build; the parameters are
`output/lineup-parameters.json` and `config/lineup_parameters.json`, produced
by `pipelines/derive_lineup_parameters.py`. The Week 5 reports are kept in
`docs/claude-log/2026-10-09-jeg521-*.md` (`output/` is not committed).

**ES-0 The lens, and what it is not.**

1. Manifesto section 4: bench points do not count. Section 7: a roster spot is
   compared with the best freely available alternative. Section 8: the unit is
   the weeks a player materially improves the lineup. Put together, a rostered
   player's fundamental value is his value above waivers times the share of
   the remaining weeks in which that surplus enters a starting lineup. This
   section defines that share.
2. It is an additive approximation of "contribution to expected lineup
   points over an all-waiver roster". The exact quantity depends on the
   other players on the roster (section 6, portfolio value). That needs a
   roster import (JEG-481) and is out of scope; the share here is for an
   average team in the league setting.
3. Two things the manifesto names are deliberately left out of the pie and
   recorded in ES-8: the convex option value of a level change (section 5)
   and the discounting of later weeks (section 9).

**ES-1 Parameters.** All measured, none assumed. The script re-derives them
each week from the repo's data; the engine reads them from
`config/lineup_parameters.json` (generated, committed, pinned by tests). A
change to them is a value change and is reviewed as one.

| Position | m, missed-game hazard | 95% interval | team games | m, 2024-2025 only | sigma now (source spread) | sigma drift (to mid-window) | sigma used | sigma floor (points per game) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| QB | 11.0% | 9.8% to 12.3% | 2,319 | 9.9% | 14.0% | 11.6% | 18.2% | 0.69 |
| RB | 15.3% | 14.4% to 16.2% | 5,816 | 10.0% | 11.1% | 27.9% | 30.0% | 0.89 |
| WR | 11.7% | 11.0% to 12.4% | 8,128 | 13.0% | 12.3% | 28.2% | 30.8% | 1.01 |
| TE | 14.4% | 13.0% to 15.8% | 2,331 | 15.9% | 8.1% | 35.3% | 36.2% | 0.64 |

- `m_p`: the share of team games a healthy starter at `p` misses. From
  `data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz` (ES-A; MR-24):
  players in the 12-team starter pool by points per game over weeks 1-5 or
  1-9 who played their team's last game of that window; measured on weeks
  k+1 to the season's last week minus one, pooled over 2015 to 2025 (2,319
  to 8,128 team games per position). The 2024-2025 Supabase export gives the
  "2024-2025 only" column as a cross-check; it agrees within 2 points
  except RB, where those two seasons were unusually healthy (10.0% against
  15.3% over eleven).
- `b`: the bye share of the remaining team-weeks, from
  `data/inputs/nfl_byes_2026.json` and the content week: 30 of 32 teams have a
  bye in weeks 6-18, so `b = 30 / (32 x 13) = 7.2%` at Week 5. It falls as
  byes pass and is 0 from Week 15.
- `sigma_p` (relative) and `sigma_floor,p` (points per game): the uncertainty
  of a player's rest-of-season per-game level. Now = the sample standard
  deviation over the mean of the ESPN, CBS rest of season and Razzball
  per-game projections, median over healthy players ranked between half the
  starters and the roster line. Drift = the demeaned robust weekly movement of
  the same projections in `data/history`, scaled by the square root of half
  the remaining weeks. Used = the root sum of squares. The floor is the median
  absolute spread below the starter count. Stand-in until G4 can measure
  realized projection error (then `sigma` becomes the measured error).
- Chart family: the same construction on the four charts after putting each
  on a common scale (one factor per chart over the players all four list):
  QB 58%, RB 50%, WR 52%, TE 84% this week; no floor (ES-6).
- The result is insensitive to all of these (ES-7 sensitivity): the decision
  is about the form, not the numbers.

**ES-2 Roster.** VP-2.2 unchanged: dedicated, greedy flex (OC-4 A), D'Hondt
bench, `S_p` and `N_p` per source. `n_p = max(1, round(S_p / T))` is the
starters per team at `p`, flex winners included.

- **Roster decision (JEG-521 constraint).** The default roster is QB 1 / RB 2 /
  WR 3 / TE 1 / FLEX 1 / BENCH 6, as in `DEFAULT_ROSTER`, `REF_SLOTS`, the
  spec reference, the worked example and the v2 steppers. `config/roster.json`
  says WR 2 / FLEX 2 and is wrong; both shapes have 8 starters and the same
  pie, but the engine has never priced the WR 2 / FLEX 2 shape by default.
  The file is corrected when VP-10 retires `build_adjustment_inputs.py`,
  which is its only consumer that moves a live number (today it sets the
  starter and bench roles of the `*_adjusted` fit cells, so correcting it
  before the fit retires would move live values outside this decision).
  `reindex_comparison_section.py` loads the shape and never uses it.

**ES-3 Lines and depth edges** (per source and position, own units, on the
work list of VP-2.4).

1. `w_p` and `l_p` as VP-2.3 and VP-2.5: the waiver line is the value at
   0-based index `N_p`, the starter line the value at index `S_p` (the first
   non-starter), floored at `w_p`.
2. Depth edges: `e_0 = l_p`; for `k >= 1`, `e_k` = the value at index
   `S_p + k x T` (the first player at depth `k + 1`) while that index exists and
   its value is above `w_p`. The last band runs down to `w_p`. Depth `k` is the
   band `(e_k, e_(k-1)]`: open below, closed above, so the first non-starter
   (whose value is `l_p`) is at depth 1, not start-worthy.

**ES-4 Lineup share of a level** at position `p`, league setting `L`.

1. Availability `avail_p = (1 - b)(1 - m_p)`: the share of remaining weeks a
   healthy player at `p` plays.
2. A starter at `p` is unavailable in a week with probability
   `q_p = b + (1 - b) m_p`. The depth-`k` bench player on an average team
   plays when at least `k` of his team's `n_p` starters are out:
   `fill_k = P(Binomial(n_p, q_p) >= k)`. At 12 teams this week:
   RB depth 1 about 0.34, depth 2 about 0.04; WR depth 1 about 0.48.
3. The level of a player projected at `x` is `X ~ Normal(x, s(x))` with
   `s(x) = max(sigma_p x, sigma_floor,p)` (for a chart, `sigma_chart,p x`).
4. `share_p(x) = avail_p x [ P(X > l_p) + sum over k of fill_k x
   P(e_k < X <= e_(k-1)) ]`. Mass below `w_p` counts nothing. `share` is
   between 0 and `avail_p`, and non-decreasing in `x`.

**ES-5 The two parts replace the slices of VP-2.6.** For every player on the
work list, with `v_i = max(0, x_i - w_p)` unchanged:

- start-worthy part `sw_i = avail_p x v_i x P(X_i > l_p)`;
- fill-in part `fi_i = avail_p x v_i x sum_k fill_k P(e_k < X_i <= e_(k-1))`;
- `sw_i + fi_i = v_i x share_p(x_i) <= v_i`.

VP-3 to VP-7 then run unchanged with `ssl := sw` and `bsl := fi`: group
totals, per-source weights, the DDF average of weights, the pie, the rates,
`A_i = r[p, bench] x fi_i + r[p, starter] x sw_i`, VORP vs waivers display,
rows, DDF Value, Indexed, tiers. The bench share becomes an output: the sum
of the bench-group weights (the pie paid on fill-in parts, 5.0% to 6.1% this
week) and, in diagnostics, the pie held by bench-tier players (8.0% to 9.9%).
The slider (VP-3.4) stays as the reader's override on these groups. OC-2 is
therefore answered "source-implied, from expected starts", and OC-3 "parts by
expected starts, continuous in the native, never reordering a source's
players" (zero inversions at all 12 settings, `tests/test_expected_starts_model.py`).

**ES-6 Charts** use the same formula in their own units with the chart
family's `sigma` and no floor; imputed players (VP-2.4) are in the work list
like listed ones. A chart's `l_p` and `w_p` are its own, so its start-worthy
probability is its own view of who starts.

**ES-7 Measured effect** (`output/expected-starts-before-after.md`; before =
today's live values scaled to the fixed pie; bench-tier share = the pie held
by players ranked past the starters on the mean projection; price = median
value per point above waivers, starters over bench tier, QB / RB / WR / TE).

| Setting | Bench tier, before | after A | after B | after A, option form | Price before | Price after A |
| --- | --- | --- | --- | --- | --- | --- |
| standard/8 | 13.8% | 9.6% | 9.2% | 13.7% | 1.0 / 1.6 / 0.7 / 1.0 | 1.2 / 2.8 / 1.7 / 1.2 |
| standard/10 | 14.5% | 9.5% | 9.1% | 13.0% | 1.0 / 1.0 / 0.9 / 1.1 | 1.2 / 2.0 / 2.3 / 1.4 |
| standard/12 | 14.0% | 8.0% | 7.5% | 11.1% | 1.4 / 1.1 / 1.1 / 0.8 | 2.3 / 2.2 / 2.7 / 1.5 |
| standard/14 | 14.7% | 8.3% | 7.4% | 10.8% | 1.1 / 0.9 / 0.8 / 0.7 | 2.1 / 1.9 / 1.9 / 1.6 |
| half_ppr/8 | 14.0% | 9.6% | 9.2% | 13.8% | 1.0 / 1.7 / 0.8 / 1.0 | 1.2 / 3.5 / 1.7 / 1.2 |
| half_ppr/10 | 14.2% | 9.4% | 9.0% | 12.9% | 1.0 / 1.2 / 0.8 / 1.1 | 1.2 / 2.1 / 1.9 / 1.3 |
| half_ppr/12 | 14.1% | 8.2% | 8.3% | 11.5% | 1.5 / 1.3 / 1.0 / 0.8 | 2.2 / 2.5 / 2.4 / 1.1 |
| half_ppr/14 | 14.5% | 8.3% | 7.4% | 10.9% | 1.1 / 1.2 / 0.8 / 0.7 | 2.1 / 1.9 / 2.1 / 1.3 |
| ppr/8 | 14.5% | 9.9% | 9.5% | 14.1% | 1.0 / 1.6 / 0.9 / 1.0 | 1.2 / 2.8 / 1.6 / 1.1 |
| ppr/10 | 14.0% | 8.7% | 8.5% | 12.4% | 1.0 / 1.5 / 0.8 / 1.9 | 1.2 / 2.5 / 2.4 / 2.2 |
| ppr/12 | 14.8% | 8.6% | 8.6% | 12.0% | 1.5 / 1.0 / 1.0 / 0.8 | 2.2 / 1.6 / 2.9 / 1.4 |
| ppr/14 | 14.1% | 8.2% | 7.4% | 10.8% | 1.2 / 1.2 / 0.8 / 0.6 | 2.1 / 2.0 / 2.0 / 1.1 |

- Sensitivity at 12-team full PPR (option A): `m` at 0.5x to 1.5x gives
  8.2% to 9.0%; `sigma` at 0x to 1.5x gives 8.1% to 9.1%; the first-pass
  assumptions give 8.7%; the fill-in-only bound is 8.1% and plain value above
  waivers (bench starts every week) 13.1%. Top-12 share of the RB pie: 56.1%
  (before 52.0%); WR 48.5% (39.2%).
- The VP slices as written (OC-2 A, source-implied) imply a bench share of
  42% at 12-team full PPR, 49% at 8-team standard and 39% at 14-team half
  PPR on live data (QB 47%, RB 42%, WR 43%, TE 37% at 12-team full PPR),
  because every starter's surplus up to the starter line is a bench slice.
  That is a large silent move toward the bench and the reason OC-2 cannot
  stay "source-implied slices" (MR-19).
- Expected lineup share of the surplus, ESPN, 12-team full PPR:

| Position | Rank | Player | Points per game | Share of surplus | Start-worthy part |
| --- | --- | --- | --- | --- | --- |
| QB | 1 | Josh Allen | 23.84 | 73.7% | 72.7% |
| QB | 7 | Tyler Shough | 20.45 | 57.1% | 54.9% |
| QB | 12 | Dak Prescott | 19.49 | 49.5% | 46.8% |
| QB | 13 | Jared Goff | 18.95 | 44.7% | 41.8% |
| QB | 18 | Jordan Love | 18.11 | 36.6% | 33.4% |
| RB | 1 | Jahmyr Gibbs | 25.71 | 82.1% | 81.6% |
| RB | 16 | Chuba Hubbard | 14.5 | 73.4% | 69.3% |
| RB | 31 | Josh Jacobs | 10.43 | 54.0% | 42.6% |
| RB | 32 | Jordan Mason | 10.35 | 53.3% | 41.8% |
| RB | 37 | Alvin Kamara | 8.5 | 34.9% | 19.5% |
| RB | 44 | Keaton Mitchell | 7.69 | 25.9% | 10.4% |

- Top movers of the blended DDF Value at 12-team full PPR (before scaled to the pie):

| Player | Position | Tier | Before | After A | Change |
| --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 51.37 | 65.02 | +13.7 |
| Ja'Marr Chase | WR | starter | 46.24 | 58.22 | +12.0 |
| Jahmyr Gibbs | RB | starter | 71.88 | 83.85 | +12.0 |
| Bijan Robinson | RB | starter | 65.39 | 76.76 | +11.4 |
| Amon-Ra St. Brown | WR | starter | 44.48 | 55.74 | +11.3 |
| CeeDee Lamb | WR | starter | 45.56 | 56.52 | +11.0 |
| Puka Nacua | WR | starter | 47.17 | 58.04 | +10.9 |
| Kenneth Walker III | RB | starter | 59.98 | 70.53 | +10.6 |
| Chris Olave | WR | starter | 37.34 | 46.15 | +8.8 |
| Jonathan Taylor | RB | starter | 52.65 | 61.42 | +8.8 |
| Christian McCaffrey | RB | starter | 49.82 | 58.29 | +8.5 |
| Romeo Doubs | WR | bench | 13.4 | 5.35 | -8.0 |

**ES-8 Left out of the pie, by decision.**

1. *Convex option value* (manifesto section 5). The form
   `avail x E[(X - w)^+ lineup(X)]` pays for the upside of a level change as
   well as its probability. Measured: bench tier 10.8% to 14.1% across the
   12 settings and a starter/bench price of 0.6x to 1.9x, so it gives back
   most of the starter premium the lineup share creates, it is driven by
   `sigma` (the least-measured input), and near the line it values a player
   above his whole surplus. Recommendation: keep the pie on expected starts
   and show option value as its own signal, `P(X > l_p)` for bench players,
   which is the G5 Stash tag (MR-21).
2. *Weekly noise* (the manager's Sunday problem): starters' weekly points vary
   by 38% (QB) to 59% (WR, TE) of their mean (2015-2025, `output/lineup-parameters.md`).
   `sigma` here is level uncertainty, not that. Matchup-driven starts of bench
   players need weekly projections (G4 b) and are a follow-up.
3. *Discounting* (section 9) and the *playoff objective* (section 10): out of
   scope per JEG-521.
4. *Known absences.* `m_p` is the forward hazard of a healthy player. A player
   already out is priced by the projections: ESPN's per-game number is per
   team game (rest-of-season total over the team's remaining games), so it
   already carries his known absence, while CBS rest of season and Razzball
   are per game played and do not. That is a source-neutrality gap in VP-0
   (MR-20), not something this section fixes.

**ES-9 Options for the glide (JEG-521 G1), argued.**

- *A, replace the slices with the two parts (ES-5).* For: one rule for every
  rostered player, continuous in the native, no calibration solve, so no
  infeasible-window clamp (MR-11: five of the 24 live legs are clamped below
  15% today, for example ESPN half PPR 12 RB at 14.2% and CBS rest of season
  standard 12 RB at 12.8%); the bench share is an output with a meaning
  (expected fill-in starts); the starter premium follows from `m`, `b` and
  the depth, not from a slider; the stash signal (G5) and the drawer's
  "expected lineup share" read straight off it. Against: a new shape within
  the starters (top-12 share up 4 to 9 points) and the chart-unit `sigma` is
  rougher than the projections'.
- *B, keep the slices and set the per-position bench budget from A.* For: the
  smallest change to the VP spec; the same bench-tier share by construction
  (7.4% to 9.5%). Against: it keeps the kink at the starter line, pays every
  starter's bench-level part at the bench rate (so the starter premium is a
  by-product of a budget transfer rather than of lineup share), gives no
  per-player share for the drawer or the stash tag, and needs a second rule
  to carry the shares from A into the weights.
- **Recommendation: A.** B is a budget patch on a structure the manifesto
  argues against; A is the manifesto's rule.

**ES-10 Front-end and diagnostics.** `valuePipeline.sources[key].positions
[pos]` gains `waiver`, `starterLine`, `avail`, `bands: [{depth, lo, hi,
fill}]`; each row gains `lineupShare` (the blended mean of the sources'
`share_p(x_i)`) and `startWorthy` (`P(X > l_p)`). The drawer's fixed
"Starter / bench utilization weighting" text (G5) becomes the player's
expected lineup share. Copy: "expected lineup share", "value above waivers";
never VORP, never an abbreviation in a title.

**ES-11 Validation.** The engine, the Python reference and the spec reference
reproduce `tests/fixtures/value_pipeline_worked_example.json` with an
expected-starts variant to 1e-6, then agree with each other to 0.05
(`value_check`). Acceptance on live data: per setting, the engine's bench-tier
share per position and each source's total match
`pipelines/expected_starts_model.py` within 0.05; the 12-combo sweep and
`check_rank_guard.py` at zero inversions; the before/after shown to Jeremy
before publishing (JEG-450).

**ES-A Data appendix.** `data/inputs/weekly_actuals_2024_2026.csv` and
`data/inputs/nfl_schedule_2024_2026.json` were exported on 2026-10-09 from
Supabase (MCP `execute_sql`, read only) with

```sql
select p.player_key, p.position, g.season, g.week, t.abbreviation,
       round(a.actual_std, 2), round(a.actual_half, 2), round(a.actual_ppr, 2)
from v_player_game_actuals a
join games g on g.id = a.game_id
join players p on p.id = a.player_id
join teams t on t.id = a.team_id
where p.position in ('QB', 'RB', 'WR', 'TE');
-- schedule: select g.season, t.abbreviation, g.week from games g
-- join teams t on t.id in (g.home_team_id, g.away_team_id);
```

A row exists where the player recorded a stat line. The 2026 schedule agrees
with `nfl_byes_2026.json` for all 32 teams (test). G4 (a) should extend this
view week by week rather than start a new table.

`data/inputs/weekly_actuals_nflverse_2015_2025.csv.gz` and
`data/inputs/nfl_schedule_2015_2025.json` (MR-24) come from nflverse's public
releases, `stats_player/stats_player_week_<year>.csv` and `schedules/games.csv`
(2026-10-09): regular season, QB/RB/WR/TE, keyed by nflverse player id, team
codes as `games_remaining.TEAM_ALIASES`. A player who dressed and recorded no
stat has a 0-point row there, so he counts as played. On 2024-2025 it carries
about 1.5% fewer player-games and 0.75% fewer points than the Supabase export
(a few extra rostered players per week there, and a minor scoring-rule
difference); the healthy-starter hazard agrees within 2 points (test). The
cancelled 2022 Week 17 game leaves BUF and CIN with 16 games that season.

### Open choices for Jeremy (the spec uses the recommended option)

| # | Choice | Options | Recommended |
| --- | --- | --- | --- |
| OC-1 | Pie total per league setting | (A) 28 per starting slot: `28 x T x starters per team` (2,688 at the 12-team default). (B) 16 per rostered slot: `16 x T x (starters + bench)` (also 2,688 at the default; grows with bench size) | A. Bench depth already moves values through the waiver line and the weights; the top player stays near 70 at every bench size |
| OC-2 | Bench share default | (A) Source-implied from the VP-2.6 slices; the slider overrides at the source level before averaging (VP-3.4). (B) 15% applied to every source, like today. (C) 15% per position, like today's two-tier. (D) Source-implied from expected starts (ES-5): the pie paid on fill-in parts, with the slider as the override | D (JEG-521, 2026-10-09). On live data A implies 39% to 49% of the pie on bench slices (ES-7), because slices count the bench-level part of every starter's surplus; D gives 4.7% to 5.5% on fill-in parts and 7.8% to 9.8% to bench-tier players, from measured missed-game and bye rates |
| OC-3 | How a player's value splits between starter and bench | (A) Slices: bench = value above waivers up to the first non-starter, starter = the rest (continuous, never reorders a source's own players). (B) Whole player in his role's group. (C) Expected-starts parts (ES-5): start-worthy part = surplus x P(level above the starter line), fill-in part = surplus x expected fill-in share; continuous, at most the surplus, never reorders | C (JEG-521, 2026-10-09). Under B, in the example, `c2`'s rates are 0.58 starter and 1.09 bench, and its RB4 comes within 2.6 of its RB3; on live data that becomes reorderings and a tier cliff (MR-06). A keeps the order but prices every starter's bench-level part at the bench rate (OC-2) |
| OC-4 | Flex fill per source | (A) Greedy best remaining by the source's own values, the same as superflex and real lineups. (B) Keep today's D'Hondt surplus-weighted flex with a preliminary waiver line | A. One rule, nothing to estimate, and it closes MR-18 SG-9 |
| OC-5 | A group a source can't fund | (A) Its budget moves to the same position's other group. (B) Left unpaid and reported. (C) That source's group shown unavailable | A. Every source still sums to the pie |
| OC-6 | Weights for the charts-only and projections-only versions | (A) One DDF weight set from all included sources; the versions differ only in which Adjusted values they average. (B) Each version re-weights to its own family's average weights | A. Each source has one Adjusted value per player, the same in every version |
| OC-7 | Projections in the Indexed tab | (A) Show their Adjusted values. (B) Hide them; the tab shows the charts and DDF Value | A. Both sit on the pie scale, so the comparison is fair |
| OC-9 | Expected-starts value (JEG-521, ES-9) | (A) Replace the VP-2.6 slices with the expected-starts parts (ES-5). (B) Keep the slices; set each position's bench budget so bench-tier players hold the share A gives them. (C) Keep the slices as written (OC-2 A) | A. B is a budget patch on a structure the manifesto argues against; C moves 39% to 49% of the pie to bench slices. Decision `es-value-001` |
| OC-8 | Which players set a chart's Indexed factor | (A) Players the chart lists with a numeric blended DDF Value, zeros included. (B) DDF Value above 0 only | A. A genuine 0 is a value (contract), and B moves the basis with the waiver line (MR-01 / SG-11) |

## Trade-Value Contract

> **Superseded (JEG-508)** in this section: the ESPN-anchored scale, the
> comparison of the charts against the built ESPN leg, and the adjustment
> cells. The scale is now the fixed league pie (VP-5), Indexed is set against
> DDF Value (VP-6.4), and there are no adjustment cells (VP-10). The identity,
> null and zero bullets still hold. Until the implementation merges, this
> describes the engine.

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

> **Superseded (JEG-508)**: the factor's target. It is still one
> order-preserving factor per chart, but it now matches the blended DDF
> Value's total over the shared players, not the ESPN anchor's (VP-6.4,
> JEG-499). The roster in item 1 is the reader's league setting (VP-2.2,
> VP-9). The DDF weights in item 2 are the average of the source weights
> (VP-4).

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

> **Superseded (JEG-508)**: the CBS ROS and Razzball matching to the ESPN
> anchor, and the `*_adjusted` peak pin. Every projection now goes through
> its own VP-2 to VP-5 onto the fixed pie. The rest of this paragraph and the
> "What the views guarantee today" measurements describe the engine before
> VP. Under VP, each source's VORP vs waivers and Adjusted totals equal the
> pie by construction (VP-5).

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

> **Superseded (JEG-508)**: the `*_adjusted` series and their fit
> (`build_adjustment_inputs.py`, adjustment cells) are retired. Every source,
> projection or chart, gets Adjusted values through the same VP-2 to VP-5
> (VP-10). The two paragraphs below describe the engine until the
> implementation merges. The rule that each projection keeps its own inputs
> still holds.

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

> **Superseded (JEG-508)**: the factor against the live ESPN anchor, the
> 40-player fallback to the saved factor, and the live refit of the adjusted
> series. Indexed is set against DDF Value (VP-6.4), and VORP vs waivers and
> Adjusted values come from VP-2 to VP-5 at every setting (VP-9). The saved
> 12-team natives and the "derived" label stay.

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
  **Superseded (JEG-508)**: the peers are the *included* sources of the same
  family (VP-1, VP-2.4). A held or unpublished chart is not a peer, and a
  short projection is filled from the other projections the same way. The
  imputed players now also fill the source's pie (VP-3, VP-5), not only its
  waiver line. The ratio, cap, loop and hiding rules below are unchanged.
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

> **Superseded (JEG-508)**: VORP vs waivers is now one factor per source to
> the fixed pie (VP-5.6). Adjusted values are now the slices re-weighted to pie
> x DDF weights, with no 70 factor and no ESPN group totals (VP-5.5). The
> saved `vorp_views` are retired (VP-10).

**Other chart views (JEG332-VORP-VIEWS, `published-views-001/1`, 2026-10-07).**
VA-3 decided (Jeremy, 2026-10-09: "Compute live everywhere."): the saved `vorp_views`
(2026-10-03) are retired. At every scoring, team count and roster -- Full PPR /
12 / standard roster included -- `ValueModel.derivePublishedViews` derives
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

> **Superseded (JEG-508, OC-4)**: flex is now filled greedily, best remaining
> by the source's own values, with no preliminary waiver line (VP-2.2c). The
> same allocator serves every source, projections included. Bench seats keep
> the D'Hondt apportionment over `BENCH_MIX_12` (VP-2.2d).

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

## DDF Composite Value (JEG-455 / JEG-471 / JEG-479 / JEG-497, Jeremy 2026-10-08/09)

> **Superseded (JEG-508)**: steps 1, 2, 5, 6 and 8 and "one DDF Value per
> view".
> - The inputs are now each included source's Adjusted values (VP-6.3), with
>   no `*_adjusted` series.
> - There are three versions (blended, charts, projections), each one number
>   in every view.
> - The charts no longer drop out of any view.
> - Tiers come from VP-7.3.
>
> Steps 3, 4 and 7, the zero and one-source rules, and "same inputs in both
> weeks" carry into VP-1 and VP-6. The identity-fallback bullet under
> "Published Charts On The Rows" is retired with the fit.

The **DDF Composite Value** ("DDF Value" in compact spots) is computed per
league setting (scoring, teams, roster, bench share, position shares) and per
week, by these steps. It is **one number per player in each of three
versions, the same in every view and tab**: the view tabs change what the
chart plots, never the DDF Value. The engine and the Python reference
implement exactly this text.

1. **Inputs and their values.** Seven inputs, each contributing its
   **Adjusted values** value only (Jeremy 2026-10-09: the Indexed and VORP vs
   waivers values never feed it):

   | Input | Value used | DDF series name |
   |---|---|---|
   | `espn`, `cbsros`, `razzball` | the projection's value as the rows carry it (identical in every tab) | `espn`, `cbsros`, `razzball` |
   | `fantasycalc_adjusted`, `usatoday_adjusted`, `fantasypros_adjusted`, `cbs_adjusted` | the published chart's **Adjusted values** (value above waivers re-weighted to our weights, "The Three Views" 2), with the rows' rules ("Published Charts On The Rows") | `<chart>_adj_values` |

   The input keys keep their historical names; a chart input is the chart, not
   its bias-adjusted `*_adjusted` series.
2. **Three versions (JEG-497).** `ddf_value` averages all seven inputs,
   `ddf_value_charts` the four charts, `ddf_value_projections` the three
   projections. Steps 3-8 apply to each version on its own inputs.
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
   may choose a subset (at least one), and each version uses its share of it.
   An input with no values at this setting (missing section, no saved setup)
   is left out.
5. **Same inputs in both weeks.** For each remaining input, its value is
   recomputed for the prior week at the same setting (the week before the
   week it serves; history rule in "Week-Over-Week Snapshots"). Per version,
   the pair is the newest served week among its inputs (`currentWeek`) and
   the week before (`priorWeek`). An input without that prior week, or
   serving another week, is left out of **both** weeks of that version. A
   chart's Adjusted values for a saved week (JEG-479, Jeremy 2026-10-09
   "Build prior week"): the same `ValueModel.derivePublishedViews` batch as
   the current week, fed every chart's saved natives for that week (its own
   natives and player set, its peers for the waiver-line extension, the batch
   whose top sets the Adjusted 0-70 scale), with the current league, roster
   and the ESPN anchor's eight group totals; no adjustment fit is involved.
   Equal natives keep the order of the chart's served list. Every setting
   derives the charts' views live (VA-3, Jeremy, 2026-10-09: "Compute live everywhere."), so
   every chart has a prior week at every setting. If no input of a
   version has a prior week (a first week, or no history), the current week
   uses the inputs from step 4 and that version has no prior week.
6. **Per player, per week.** The equal-weight mean of the finite values of
   the included inputs. A value that is missing is left out, never counted as
   0. A 0 an input does carry counts: ESPN's 0 for a player it lists at 0
   (GAP-025), a leg's 0 at or below its floor, and a fully loaded chart's 0
   for a player below its floor. When exactly **one** input prices the
   player, the value is that input's value, flagged low confidence ("Only one
   source prices this player"; Jeremy 2026-10-09, replacing the two-value
   minimum). When none does, it is null with the reason "No source prices
   this player". The prior week uses the same inputs and the same rule.
7. **Δ** = this week's value − the prior week's value, when both exist.
8. **Tier.** Rank by the current `ddf_value` and cut at the league's slot
   counts (the engine's value-based slot fill). A one-source value counts. No
   value, no tier.

One value per version for every comparison column (no leave-one-out).

### Published Charts On The Rows (Jeremy 2026-10-08/09)

What a row carries for a published chart (`<chart>`, its VORP vs waivers and
Adjusted values, and `<chart>_adjusted`), in every view and both weeks, and
so what the DDF Value reads for a chart (its Adjusted values):

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
  is never the unadjusted chart value. (The DDF Value reads a chart's Adjusted
  values, not its `*_adjusted` series, so these cells do not reach it.)
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

> **Superseded (JEG-508)**: the anchor-based parts of this section. These
> are the value-ordered roles on the anchor, the ESPN projections in
> `positionalMaxForSetup`, and the paragraph below. There is no anchor now.
> Every source fills the superflex slot on its own values (VP-2.2b), the pie
> grows by one starting slot per team (VP-5.1), and the QB weights come from
> the sources' own superflex VORP (VP-3, VP-4). That also removes MR-15's
> "Adjusted values push superflex QBs below their 1-QB values". The publisher
> superflex overlay and how it is saved are unchanged.

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
Value, in the three views (**superseded (JEG-508)**: the series and DDF
versions listed in VP-11 / VP-12, with the weights and the pie), at 3 scorings x 8/10/12/14 teams on the default
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
- A universe player nothing prices has ESPN "absent" and no projection
  (`universe_only`, `unpriced_reason` names his status). He is not one of the
  engine's computed rows (getAllRows, the curves, the pies); search
  materialises him on demand (`TradeValueCurveControls.searchPlayers` /
  `getPlayer`) with the same row rules: 0 where a chart is fully loaded, a
  reason elsewhere.
- Every row ties back to the players table (JEG-438). The Sleeper identity
  refresh inserts universe players the table lacks
  (`pipelines/sync_sleeper_players.py`, additive, `metadata.sleeper_id`);
  until then they are listed in `meta.universe.nfl_active.not_on_players_table`.

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

> **Superseded (JEG-508)**: the ESPN tier is replaced by the DDF tier
> (VP-7.3), and the two-tier legs no longer price any series (VP-10). These
> rules describe the engine until the implementation merges.

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
