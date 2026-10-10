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
JEG-499) and **revised the same day for Jeremy's binding answers to the open
choices OC-1 to OC-8** (quoted on JEG-508; listed as decided at the end of
this section). Those decisions are binding. This section governs every value
the site shows. It supersedes the paragraphs below that are marked
**Superseded (JEG-508)**. Until the implementation PRs merge, those
paragraphs still describe what the engine does; they are kept, not deleted, so
the before/after is reviewable. Three implementations are written from this
text independently: the engine (`curve-widget.js`, `value-model.js`), the
Python reference (`pipelines/value_reference.py`) and the clean-room spec
reference (`pipelines/spec_reference/`). They must agree to 0.05 on every
value (`value_check`) before anything merges. Where Jeremy's words left a
detail open, the text says **Lead's reading** and gives the rule used; an
implementation follows the rule as written.

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
- Bench share: "15% is right. There is no way 35% is rational math." (OC-2)
- Flex: best remaining by assumed (projected) points, not VORP. (OC-4)
- "We need to fill in more players to get to vorp for all rosterable players.
  We need to pull vorp by using other sources." The fill-in rule (OC-5) was
  approved as proposed.

### VP-0 Definitions and conventions

- **Positions** are QB, RB, WR, TE. Where a tie is broken by "position
  order", it is this order.
- **League setting L.** scoring; teams `T`; dedicated slots per team `D_p`;
  flex slots per team `F` (RB/WR/TE eligible); superflex slots per team `SF`
  (QB/RB/WR/TE eligible); bench slots per team `B` (default 6); bench share
  `bs` (default **0.15**, OC-2; the reader's bench-share slider replaces it,
  VP-3.4); reader position shares (default: none).
- **Sources and natives.**
  - *Projections* (`espn`, `cbsros`, `razzball`). Native = the source's own
    projected points per game at the scoring.
  - *Trade charts* (`cbs`, `fantasycalc`, `fantasypros`, `usatoday`). Native
    = the publisher's trade value from the saved 12-team list at the scoring.
    With `SF >= 1`, the saved `native_superflex` replaces the 1-QB native for
    the players it covers ("Superflex", below).
  - A source *lists* player `i` when it has a finite native for him. His
    position comes from the naming table (`player_key`).
  - A chart's *estimated* players are the players VP-2.4 fills in for it.
    "Listed" never includes them.
- **Sort order** (a source's own order within a position): native
  descending, then listed before estimated, then `player_key` ascending
  (numeric). "Rank" is the 1-based position in that order.
- **Mean points per game** `m_i` = the arithmetic mean of the natives of the
  projections in `I` (VP-1) that list `i`. A projection that does not list
  `i` is left out, never counted as 0. A player no projection in `I` lists
  has no `m`. **Projected-points order** within a position: `m` descending,
  then `player_key` ascending; players without `m` are not in it.
- **Arithmetic.** IEEE doubles. No intermediate rounding anywhere, including
  the bench share, ratios, fits and estimates. Display rounds to one decimal.
  Ties mean exact equality of doubles. Sums run in sort order. A median of
  an even count is the mean of the two middle values.
- **Constants.** `BENCH_MIX_12 = {QB 10, RB 27, WR 33, TE 10}`.
  `IMPUTE_MIN_FIT = 3`. `ESTIMATE_FIT_N = 10`. `DEFAULT_BENCH_SHARE = 0.15`
  (OC-2). `PIE_PER_STARTING_SLOT = 28` (OC-1).
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
3. `I` alone drives the mean points per game and with them the league
   allocation and the rosterable set (VP-2.2, VP-2.4), the DDF weights
   (VP-4), the fill-in peers (VP-2.4) and the DDF versions (VP-6.3). The
   same `I` is used for both weeks.
4. A source outside `I` (held, unpublished, no prior week) is still shown from
   its kept section. It goes through VP-2, VP-3, VP-5 and VP-6.4 against the
   same allocation, rosterable set, pie and DDF weights, with the charts in
   `I` as its fill-in peers, so its numbers stay on the page's scale. It
   contributes nothing to weights, peers, `m` or DDF.
5. The reader's input selection (`setCompositeInputs`) filters only the DDF
   averaging (VP-6.3). It never changes `I`, `m`, the weights, or any
   source's values.
6. ESPN has no special role anywhere. A missing ESPN is dropped like any other
   source, and the page renders with any non-empty `I`.

### VP-2 Native to value above waivers (per source, per position)

Every source runs this step in its own units: points per game for
projections, trade value for charts. Charts and projections use the same
rules, except that only charts are filled in (VP-2.4).

1. **Lists.** Build each position's listed players in sort order.
2. **League allocation `alloc`** (the "size logic", OC-4). It runs **once per
   setting and week, on the projected-points order**, and every source uses
   the same counts. A source's own values never move a slot.
   - a. Dedicated: `d_p = T x D_p`.
   - b. Superflex: candidates are the players at 0-based index `>= d_p` of
     their position's projected-points order, at any position. Take the
     `T x SF` best by `m` descending, then position order, then `player_key`
     ascending. `sf_p` = the number taken at `p`. **Lead's reading:** Jeremy's
     "by assumed points, not VORP" covers the superflex slot as well, since it
     is a flex slot that also admits QBs.
   - c. Flex: candidates are the players at index `>= d_p + sf_p` of the
     projected-points order at RB/WR/TE. Take the `T x F` best, in the same
     order (`m` descending, position order, `player_key` ascending). `fx_p` =
     the number taken at `p`.
   - d. Bench: `b_p` = D'Hondt apportionment of `round_half_up(T x B)` seats
     over `BENCH_MIX_12`. Each seat goes to the position with the largest
     `weight / (seats + 1)`, with ties going to position order.
   - e. Starters `S_p = d_p + sf_p + fx_p`. Rostered `N_p = S_p + b_p`. If the
     candidates run out, the untaken slots stay empty.
   - f. **No projection in `I`** (degenerate week). **Lead's reading:** there
     is no projected-points order, so each source runs a–e on its own sort
     order (superflex and flex by its own natives, the superseded OC-4 rule),
     there is no rosterable set and nothing is estimated (VP-2.4 is skipped),
     and VP-7.2 runs a–e on blended DDF Value.
3. **Waiver line `w_p`**, read from the work list (the listed players plus,
   for a chart, its estimated players at `p`, in sort order):
   - If the work list is longer than `N_p`: `w_p` = the value at 0-based index
     `N_p`. The method is `roster_determined` when that player is listed and
     `estimated` when he is an estimated player.
   - Else, if the work list is non-empty: `w_p` = its last value. The method
     is `insufficient_coverage`.
   - Else: `no_players`. The source does not price `p`.
4. **Fill-in of rosterable players a chart does not list (OC-5, approved
   2026-10-09).** Projections are not filled in (**Lead's reading:** Jeremy's
   rule is written for charts, and a projection that does not project a
   player is already covered by the other projections in `m`).
   - a. **Rosterable set.** `R_p` = the first `N_p` players of position `p`'s
     projected-points order (the league's starters plus bench spots, ranked
     by projected points). **Fill set** `Fill_p` = the first `N_p + 1` (fewer
     if the order is shorter). **Lead's reading:** the one extra player is the
     first player past rosterable depth; he sets the waiver line, so a chart
     that lists exactly the rosterable players still has a waiver line. He is
     estimated and shown like the others.
   - b. A chart `c` gets an estimate for every player in `Fill_p` it does not
     list, **only at positions where it lists at least one player**. A chart
     that lists nobody at `p` does not price `p` (`no_players`).
   - c. **Peers** = the charts in `I` other than `c`, in source-key order,
     using their listed natives (with the superflex overlay at `SF >= 1`),
     never their own estimates.
   - d. **Ratio path** (from the other charts that list him). For each peer
     `k` that lists `i`:
     - `shared` = the players at `p` that both `c` and `k` list, in `c`'s sort
       order. The **fit set** is the last `min(ESTIMATE_FIT_N, |shared|)` of
       them (the 10 lowest on `c`; all of them when fewer than 10 are shared).
     - If the fit set has fewer than `IMPUTE_MIN_FIT` (3) players, or `k`'s sum
       over it is `<= 0`, the peer is not usable.
     - Otherwise `ratio_k = sum(c's natives over the fit set) / sum(k's natives
       over the fit set)` (a ratio of sums, not a median of per-player
       ratios), and `est_k = ratio_k x native_k(i)`.
     - If at least one peer is usable, `raw` = the median of the `est_k`.
   - e. **Curve path** (no chart lists him, or none of those that do is
     usable; **Lead's reading** for the second case). Points = `c`'s listed
     players at `p` that have `m`, in `c`'s sort order; take the last
     `min(ESTIMATE_FIT_N, count)`. If there are at least `IMPUTE_MIN_FIT` of
     them and their `m` values are not all equal, fit an ordinary
     least-squares line `native = a + b x m` (unweighted, `b = sum((m - mean
     m)(x - mean x)) / sum((m - mean m)^2)`, `a = mean x - b x mean m`) and
     `raw = a + b x m_i`. Otherwise (**Lead's reading**), if `c` lists a
     player at `p` with `m > 0`, take the lowest such player in `c`'s order,
     `low`, and `raw = native_c(low) x m_i / m_low`; else `raw = 0`.
   - f. **Order stays the chart's own.** The estimate is
     `min(max(raw, 0), lowest listed native of c at p)`. An estimated player
     never goes above the chart's lowest listed player at that position; at a
     tie the listed player sorts first (VP-0). `capped` = `raw` was above the
     cap.
   - g. Estimates use only listed natives and `m`, never other estimates, so
     there is no loop and the result does not depend on processing order.
   - h. **Display and counting.** An estimated player is a full member of the
     chart's work list: he counts in its waiver and starter lines, its groups
     (VP-3), its VORP vs waivers and Adjusted values (VP-5), its Indexed
     values (VP-6.4) and the DDF Value (VP-6.3). His row value on `c` is
     shown marked **estimated**, with a reason: "Estimated: <label> doesn't
     list him; scaled from <peer labels>" (ratio path) or "Estimated: no
     chart lists him; from <label>'s values against projected points" (curve
     path). This replaces CTL-006's "never displayed" for these players.
   - i. **Below rosterable depth.** A player a chart does not list and does not
     estimate, at a position the chart prices, is 0 on that chart in every
     view (VP-6.2). Players below rosterable depth therefore stay at or near 0
     for every source.
5. **Starter line `l_p`** = the work-list value at 0-based index `S_p` (the
   first non-starter) if it exists, else `w_p`. Then `l_p = max(l_p, w_p)`.
6. **Per player** on the work list, listed or estimated:
   - value above waivers `v_i = max(0, x_i - w_p)`;
   - bench slice `bsl_i = max(0, min(x_i, l_p) - w_p)`, the part of his
     surplus that any rostered player at `p` provides;
   - starter slice `ssl_i = max(0, x_i - l_p)`, the premium over the first
     non-starter;
   - `v_i = bsl_i + ssl_i` exactly.
   - Display role: starter if rank `<= S_p`, bench if `<= N_p`, else waiver.
     The role is shown but does not price (OC-3: the slice only decides which
     group a player's value counts in).

### VP-3 Per-source implied weights (8 groups)

1. **Group totals** over the work list, estimated players included:
   `G_s[p, starter] = sum(ssl_i)` and `G_s[p, bench] = sum(bsl_i)`. That makes
   8 groups, position x starter/bench.
2. `G_s` = the sum of the 8. If `G_s = 0`, the source has no implied weights.
   It is left out of VP-4, and its VORP vs waivers and Adjusted values are 0
   for every player on its work list.
3. **Mixes** (unit-free, so a chart and a projection are comparable):
   - starter mix `sig_s[p] = G_s[p, starter] / sum over q of G_s[q, starter]`,
     defined when that sum is `> 0`;
   - bench mix `beta_s[p] = G_s[p, bench] / sum over q of G_s[q, bench]`,
     defined when that sum is `> 0`.
4. **Bench share (OC-2).** `bs` = 0.15 unless the reader has set the
   bench-share slider, which replaces it (**Lead's reading:** the slider stays
   as a reader override; 15% is its default, and source-implied shares are
   never used). Each source is normalized to it at the source level: its
   weights are `w_s[p, starter] = (1 - bs) x sig_s[p]` and
   `w_s[p, bench] = bs x beta_s[p]`. A source whose bench mix is undefined
   (no bench surplus) shows `w_s[p, starter] = sig_s[p]` and bench 0; one whose
   starter mix is undefined shows `w_s[p, bench] = beta_s[p]` and starter 0.
   These per-source weights are reported; VP-4 averages the mixes, which
   equals averaging the normalized weights and renormalizing each half.

### VP-4 DDF weights

1. `Sraw[p]` = the mean of `sig_s[p]`, and `Braw[p]` = the mean of
   `beta_s[p]`, each over the sources in `I` that have weights (VP-3.2), have
   that mix defined and do not have `no_players` at `p`. Empty means 0.
2. `bs* = bs` when `sum(Sraw) > 0` and `sum(Braw) > 0`; `bs* = 0` when
   `sum(Braw) = 0` (no bench surplus anywhere, e.g. `B = 0`); `bs* = 1` when
   only `sum(Sraw) = 0`.
3. `W[p, starter] = (1 - bs*) x Sraw[p] / sum(Sraw)` and
   `W[p, bench] = bs* x Braw[p] / sum(Braw)` (0 where the denominator is 0).
   The bench groups of `W` therefore sum to exactly `bs` (15% by default) and
   the starter groups to `1 - bs`.
4. **Reader position shares** (BE-2 / MR-16), when set:
   `W[p, r] = W[p, r] x share_p / (W[p, starter] + W[p, bench])`, skipped
   where that sum is 0. Applied after 3, so with position shares set the
   bench total follows the shares.
5. Every source in `I` counts once (four charts and three projections, so 7
   at full strength). There is one weight set per league setting and week,
   shared by all three DDF versions (OC-6).

### VP-5 Fixed league pie and Adjusted values

1. **Pie** (OC-1): `Pie(L) = 28 x T x (sum of D_p + F + SF)`, which is 28 per
   starting slot. It depends on neither scoring nor bench. At the default
   roster (8 starters) it is 1,792 / 2,240 / 2,688 / 3,136 at 8 / 10 / 12 /
   14 teams, and 3,024 at 12 teams with one superflex slot.
2. **Budgets**: `b[g] = Pie x W[g]`. The bench budgets total
   `Pie x bs` (15% of the pie by default) for every source.
3. **Unfunded groups.** When a source has `G_s[g] = 0` while `b[g] > 0`, and
   the other group at the same position has `G_s > 0`, the budget moves to
   that other group. If both are 0 (the source has no surplus at `p`), the
   budget stays unpaid and is reported in `unfundedGroups`. **Lead's
   reading:** Jeremy's OC-5 answer replaced the question with the fill-in
   (VP-2.4), which removes nearly every unfunded group; this move is kept
   only as the residual rule (the earlier recommendation A).
4. **Rates**: `r_s[g] = b'_s[g] / G_s[g]`, or 0 where `G_s[g] = 0`.
5. **Adjusted value**:
   `A_i = r_s[p, bench] x bsl_i + r_s[p, starter] x ssl_i`.
   - Each source's group totals equal the budgets, and its total equals the
     pie, both counted over the work list (estimated players included, and
     shown).
   - `A` is continuous and non-decreasing in the native, so a source's own
     order within a position never inverts.
   - Multiplying a source's natives by a constant changes nothing.
6. **VORP vs waivers (display)**: `V_i = v_i x Pie / G_s`. That is one factor
   per source, so every source's total over its work list equals the pie: the
   same exact scale, with each source keeping its own weighting.

### VP-6 Rows, DDF Value and Indexed

1. **Rows.** Every player any source lists, held sources included, gets a
   row. This includes every player on ESPN's list (JEG-496).
2. **Row value of source `s` for player `i`**, in any view:
   - `s` lists `i`: the view's value (`A_i`, `V_i`, or Indexed from 4).
   - A chart that estimated `i` (VP-2.4): the view's value from his estimate,
     marked estimated with its reason.
   - A chart that neither lists nor estimated `i`, at a position it prices:
     **0** in every view ("Below rosterable depth; <label> doesn't list
     him").
   - A projection that does not list `i`: null, "<label> doesn't project this
     player".
   - `no_players` at `p`: null, "<label> doesn't price <pos>".
3. **DDF Value, three versions** (JEG-497). Each is one number across every
   view and tab.
   - `ddf_value` (blended): the sources in `I`.
   - `ddf_value_charts`: the charts in `I`.
   - `ddf_value_projections`: the projections in `I`.

   Each is further narrowed by the reader's selection. Value = the
   equal-weight mean of the numeric Adjusted row values of those sources,
   estimated values included. Zeros count; nulls are left out. Exactly one
   value gives that value with `lowConfidence` ("Only one source prices this
   player"). None gives null ("No source prices this player"). A held or
   unpublished source is never an input.
4. **Indexed** (JEG-499, display only). For each chart `c`, `shared` = the
   players `c` **lists** (estimated players excluded) who have a numeric
   blended DDF Value, genuine zeros included (OC-8). Then
   `f_c = sum(ddf_value over shared) / sum(native_c over shared)` and
   `Indexed_i = native_i x f_c` for listed and estimated players (estimated
   ones marked).
   - It is one positive factor, so the chart's own order survives exactly
     (rank guard; estimated players sit at or below the lowest listed one).
   - If the native sum is `<= 0`, or `shared` is empty, Indexed is null:
     "Not enough shared players to index".
   - Players below rosterable depth follow rule 2 (0).
   - Projections have no published scale. In the Indexed tab ("Trade charts
     (as published)") they are available as their Adjusted values but
     **off by default** (OC-7): not drawn until the reader turns them on.

### VP-7 Slot filling, zones, tiers, ranking

1. **Mean points per game** `m_i` as in VP-0.
2. **Slot fill** = the league allocation of VP-2.2 (`S*_p = S_p`,
   `N*_p = N_p`). The zones on the curve sit at these counts. With no
   projection in `I`, slot fill runs VP-2.2 a–e on blended DDF Value.
3. **Tier** (`ddfTier`). Within a position, rank by blended DDF Value
   descending, then `m` descending (missing last), then key ascending.
   - DDF Value 0: waiver.
   - Rank `<= S*_p`: starter.
   - Rank `<= N*_p`: bench.
   - Otherwise waiver.
   - No DDF Value: no tier.
4. **Default ranking, lock and curve**: blended `ddf_value`, descending, then
   key ascending; nulls last. The other two versions can be chosen like any
   series.
5. No source is required to render. With an empty `I`, every DDF Value is null
   ("No source available this week") and Indexed is null. The page still
   renders.

### VP-8 Weeks and the change since last week

1. The prior week runs VP-2 to VP-7 on the prior inputs:
   - each source in `I` uses its prior-week snapshot ("Week-Over-Week
     Snapshots");
   - the same `L`, the same `I` and the same pie;
   - prior-week `m` (so a prior allocation and rosterable set) and
     prior-week peers.

   That gives prior weights, prior Adjusted values, prior DDF versions and a
   prior Indexed factor. Nothing from the current week enters the prior week.
2. The change is the current value minus the prior value, for each DDF
   version, when both exist. It moves when either the source or the average
   weights moved. That settles MR-07 as option (b).

### VP-9 How each league setting enters

| Setting | Where it enters |
| --- | --- |
| Scoring | Which natives: each chart's list at that scoring; points per game at that scoring, and so `m`. |
| Teams `T` | The league allocation (VP-2.2), and with it the rosterable set, the waiver and starter lines; the pie. |
| Dedicated slots, flex | The league allocation (flex by projected points); the pie. |
| Superflex `SF` | The league allocation (by projected points); the chart natives' superflex overlay; the pie. |
| Bench per team `B` | Bench seats, so `N_p`, the rosterable set and the waiver line. Not the pie (OC-1). |
| Bench share `bs` | 15% by default (OC-2); the reader's slider replaces it (VP-3.4). |
| Reader position shares | Only when the reader sets them (VP-4.4). |

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
| ESPN group totals as DDF weights ("the anchor's total for that group") | The average of the source mixes with bench fixed at 15% (VP-3, VP-4) |
| ESPN-measured positional pies (`espn_pies.json`) and the two-tier glide as the projections' value | VP-2.6 slices and VP-5 rates. The bench share keeps its meaning as the share of the pie paid on bench slices (15% by default), without the softplus glide |
| Source-implied bench share (the first draft's OC-2 A) | 15% fixed default, every source normalized to it (VP-3.4) |
| Indexed factor against the ESPN leg (`order_preserving_rescale`, `derivePublishedSetup`'s live-anchor factor, the 40-player fallback) | VP-6.4 against blended DDF Value |
| Default lock and curve on ESPN; ESPN tier (V2-TIER-VS-ESPN-LEG) | VP-7.3 / VP-7.4 on DDF Value |
| Slot filling and zones by ESPN points per game | VP-7.1 / VP-7.2, the mean of the included projections |
| ESPN as the only source whose absence refuses to render | VP-1.6 / VP-7.5 |
| Saved `vorp_views` (`build_imputed_vorps.py`) at the 12-team setup | VP-2 to VP-5 at every setting |
| One DDF Value per view (`ddfByView`), and the charts dropping out of two views' DDF (MR-17) | VP-6.3, one number per version in every tab |
| D'Hondt surplus-weighted flex with a preliminary waiver line ("Publisher Flex Allocation"), and the first draft's per-source greedy flex by own values | VP-2.2: one league allocation, flex and superflex by projected points (OC-4). The bench D'Hondt stays |
| Hidden imputed extension of short charts (tail-median ratio, mean over peers, `imputed_from_other_charts`, never displayed) | VP-2.4 fill-in of the rosterable set: last-10 ratio of sums, median over peers, curve fallback, shown as estimated |
| A chart that does not list a player gives 0 when "fully loaded", null otherwise | VP-6.2: estimated if rosterable, 0 below rosterable depth |
| Copy that calls ESPN the anchor or the core weight | DDF Value is the core value (JEG-499) |

### VP-11 Front-end contract (keeps existing names where the meaning is unchanged)

- **Series in `row.values`**, in the active tab:

  | Key | Indexed tab ("Trade charts (as published)") | VORP vs waivers tab | Adjusted values tab |
  | --- | --- | --- | --- |
  | `cbs`, `fantasycalc`, `fantasypros`, `usatoday` | Indexed (VP-6.4) | `V` (VP-5.6) | `A` (VP-5.5) |
  | `espn`, `cbsros`, `razzball` | `A`, available, off by default (OC-7) | not drawn | `A` |
  | `espn_vorp`, `cbsros_vorp`, `razzball_vorp` | not drawn | `V` | not drawn |
  | `ddf_value`, `ddf_value_charts`, `ddf_value_projections` | the same in every tab | | |

  `fantasycalc_adjusted`, `usatoday_adjusted`, `fantasypros_adjusted` and
  `cbs_adjusted` are retired. The front-end change that stops reading them
  ships in the same release.
- **Estimated values.** New row field `estimated: {sourceKey: reason}` for
  every chart value that comes from VP-2.4. The value cell, tooltip and
  inspector mark it "estimated" and show the reason. Estimated values are
  drawn like listed ones.
- **DDF row fields.** These keep their names and now describe blended
  `ddf_value`: `ddfReason`, `ddfCount`, `ddfSources` (source keys, such as
  `fantasycalc`), `ddfLowConfidence`, `ddfConfidenceNote`, `ddfPrior`,
  `ddfPriorCount`, `ddfPriorLowConfidence` and `ddfTier`.
  - New: `ddfByVersion: {blended, charts, projections}`. Each entry is
    `{value, count, sources, reason, lowConfidence, prior, priorCount,
    priorLowConfidence}`.
  - `ddfByView` is retired.
  - `missingReasons` keeps its texts, minus the two identity-fallback
    reasons, "Adjustment data failed to load" and "Chart doesn't list players
    this deep at <pos>". It gains "<label> doesn't price <pos>", "Not enough
    shared players to index", "No source available this week" and "Below
    rosterable depth; <label> doesn't list him".
- **Composite API.** `getCompositeInputs([version])` and
  `getCompositeValues([version])`, where `version` is `"blended"` (default),
  `"charts"` or `"projections"`.
  - The former `view` argument is accepted and ignored.
  - `inputs` and `series` are source keys.
  - `getSourceInfo({includeComposite: true})` lists all three DDF keys.
  - `setLockOrder` accepts each of them.
  - `getPriorWeek` / `getWeekValues` accept each of them.
- **Diagnostics.** New `TradeValueCurveDiagnostics.valuePipeline` =
  `{version: "value-pipeline/2", setting, pie, benchShare, included,
  excluded: [{key, reason}], ddfWeights: {"POS|starter"...}, allocation:
  {pos: {dedicated, superflex, flex, bench, starters, rostered}}, fillSets:
  {pos: [player keys]}, sources: {key: {family, totalVorp, groups, weights,
  starterMix, benchMix, rates, unfundedGroups, vorpFactor, indexedFactor,
  positions: {pos: {method, waiver, starterLine, starters, rostered, listed,
  nEstimated, estimates: {playerKey: {path, peers: {key: {fitPlayers, ratio,
  estimate}}, curve, raw, cap, capped, value}}}}}}}`. The math inspector
  reads it.
- **Copy.** "DDF Value", "DDF Value · trade charts", "DDF Value ·
  projections", "estimated". No copy calls ESPN the anchor.

### VP-12 Validation

- `value_check` compares, per setting:
  - the 7 sources in each view they appear in (VP-11), estimated values
    included;
  - the three DDF versions, current and prior;
  - `ddfWeights`, the allocation and the pie.

  Tolerance is 0.05 on values and 1e-4 on weights.
- **Worked example.** `tests/fixtures/value_pipeline_worked_example.json`
  holds the inputs, every intermediate value and the expected outputs for a
  2-team league (hand-checkable; summary below). Each implementation must
  reproduce it to 1e-6 before it runs on live data.
- **Before publishing**, run the 12-combo sweep (CLAUDE.md), check where each
  position's curve starts, and show Jeremy the before/after on live data
  (JEG-508 plan step 3), including the share of players at DDF 0 at Full PPR
  12 (it was about 383 of 648 before the fill-in).

### Worked example (tests/fixtures/value_pipeline_worked_example.json)

**Setting.** 2 teams, QB1 RB1 WR1 TE1 FLEX1, no superflex, bench 2 per team,
bench share 0.15. Pie = 28 x 2 x 5 = **280**.

**Sources.** Projections `p1` and `p2` and charts `c1`, `c2`, `c4`, `c5` are
included. `c3` is held; its natives are exactly 10 x `c1`. RB Juliet (a
rookie) is projected only by `p1` (8.5) and listed by no chart.

**League allocation (by projected points).**

- Bench seats: `round(2 x 2) = 4`, D'Hondt over `BENCH_MIX_12` in the order
  WR, RB, WR, RB: RB 2, WR 2.
- Flex candidates by `m`: WR November 11.0, TE Uniform 10.2, RB Foxtrot 9.8.
  The two flex slots go to **WR and TE**. By `c1`'s own values (the
  superseded rule) they would go to WR November (40) and **RB Foxtrot (35)**,
  not TE Uniform (6) (`expected.flex_contrast`).
- Every source: QB 2/2, RB 2 starters/4 rostered, WR 3/5, TE 3/3.
- Fill sets (first `N_p + 1` by `m`): QB Alpha, Bravo, Charlie; RB Delta,
  Echo, Foxtrot, Juliet, Golf; WR Lima to Quebec; TE Sierra to Victor.

**Fill-in estimates.**

| Chart | Player | Path | Detail | Raw | Shown |
| --- | --- | --- | --- | --- | --- |
| c2 | WR Quebec | peers c1, c4 (median of 2) | ratios 0.956311, 0.947115 on 5 shared | 9.038975 | 9.038975 (its WR waiver line) |
| c5 | WR Papa | peers c1, c2, c4 (median of 3) | estimates 14.072917, 12.518919, 15.0 | 14.072917 | 14.072917 |
| c5 | WR Quebec | peers c1, c4 | estimates 9.046875, 10.0 | 9.523438 | 9.523438 (waiver line) |
| c5 | TE Victor | peers c1, c2, c4 | estimates 4.463768, 2.961538, 5.202703 | 4.463768 | 4.463768 (waiver line) |
| c5 | RB Golf | peers c1, c2 | ratio 186/185 on 3 shared, both | 17.594595 | 17.594595 (waiver line) |
| c4 | RB Golf | peers c1 (fit on the last 10 of 11 shared: `145.5 / 130.5`), c2 | 22.298851, 15.692308 | 18.995579 | **2** (capped at c4's lowest listed RB) |
| c5 | RB Juliet | curve on Delta, Echo, Foxtrot: `native = -46.824297 + 7.810356 x m` | m = 8.5 | 19.563731 | 19.563731 |
| c1, c2, c3, c4 | RB Juliet | curve | | 26.26 / 32.30 / 262.61 / 34.42 | capped: 1 / 3 / 10 / 2 |

Below rosterable depth: `c2` does not list RB Hotel and `c5` does not list QB
Delta; both are 0 on that chart in every view.

**DDF weights (bench 15%).** Starter mix mean QB 0.146323, RB 0.263452, WR
0.313098, TE 0.277128; bench mix mean RB 0.509118, WR 0.490882. So
`W` = QB starter 0.124374, RB starter 0.223934, RB bench 0.076368, WR starter
0.266133, WR bench 0.073632, TE starter 0.235558 (bench 0.15 exactly). QB and
TE have no bench seats, so their bench groups are 0.

**Hand-check one value.** `p1`, RB Delta: native 18; starter line 10 (RB
Foxtrot, index 2), waiver line 7 (RB Golf, index 4). Bench slice 3, starter
slice 8. `p1`'s RB groups are 10.5 bench and 12 starter, so the rates are
`280 x 0.076368 / 10.5 = 2.036472` and `280 x 0.223934 / 12 = 5.225123`, and
`A = 3 x 2.036472 + 8 x 5.225123 =` **47.910397**. Across the six included
sources RB Delta's blended DDF Value is **48.511113** (charts 50.223260,
projections 45.086821).

**What else it pins.**

| Case | Player | Result |
| --- | --- | --- |
| Estimated value counts in DDF | RB Juliet | blended 0.785708 over 5 sources (c5's estimate gives 0.873833 Adjusted); projections 3.054707, low confidence (`p2` is null) |
| Capped ratio estimate | RB Golf on c4 | estimated 2, Adjusted 0; blended 1.297383 |
| Indexed basis excludes estimates | c5 | `f = 276.236057 / 532 = 0.519241` over its 13 listed players; RB Juliet's estimate shows 10.158285 Indexed |
| Held source shown, never counts | c3 | Adjusted and Indexed identical to c1's (the curve estimate scales by 10, and so does the cap) |
| Tiers | slot fill = the allocation | TE Uniform (DDF 9.048407) is a starter by the flex; RB Juliet (rank 5 of RB) is waiver |
| Bench share slider 0.10 | `variant_bench_share_0_10` | weights and blended DDF |

### Expected-starts value (JEG-521, 2026-10-09): the proposed answer to OC-2 and OC-3

**Status.** Approved by Jeremy 2026-10-09 20:51 (JEG-533, `es-value-001`,
option A with the bench share as a computed readout, ES-14). Not live yet:
it lands after JEG-508. JEG-508 ships first with the bench share fixed at 15% and slices
(OC-2, OC-3 decided 2026-10-09); this section is the follow-up question of
whether the 15% becomes an output of the data. When approved it replaces VP-2.6 and lands through JEG-508's pipeline with the
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
   "Enters a lineup" is decided on projections before the week, so the share
   is about where his projection will sit, not how his games turn out.
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
- The 95% intervals in the table are binomial over team games and are too
  narrow, because missed games come in runs (one season-ending injury is many
  missed games). A player-cluster bootstrap gives QB 8.3% to 13.9%, RB 13.5%
  to 17.1%, WR 10.3% to 13.0%, TE 11.8% to 17.1% (`tools/rb_hazard_trend.py`,
  JEG-525 item d). Whether `m_RB` should weight recent seasons more is MR-25;
  the bench tier moves by at most 0.15 points across the candidates.

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
   `X` is where his projection will sit when a manager sets a lineup, not
   his realized points: lineups are set on projections before the games, so
   `sigma` is the spread of projections (source disagreement and weekly
   drift, ES-1), and Sunday's outcome noise is excluded on purpose (ES-8.2;
   Jeremy, JEG-525 artifact comment, 2026-10-09).
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
- Moot since OC-2 was decided at a fixed 15% (2026-10-09); kept for the
  record. The VP slices with a source-implied share (OC-2 A) would imply a bench share of
  42% at 12-team full PPR, 49% at 8-team standard and 39% at 14-team half
  PPR on live data (QB 47%, RB 42%, WR 43%, TE 37% at 12-team full PPR),
  because every starter's surplus up to the starter line is a bench slice.
  That would have been a large silent move toward the bench (MR-19).
- Expected lineup share of the surplus, ESPN, 12-team full PPR:

| Position | Rank | Player | Points per game | Share of surplus | Start-worthy part |
| --- | --- | --- | --- | --- | --- |
| QB | 1 | Josh Allen | 23.84 | 72.8% | 71.8% |
| QB | 7 | Tyler Shough | 20.45 | 56.6% | 54.2% |
| QB | 12 | Dak Prescott | 19.49 | 49.1% | 46.2% |
| QB | 13 | Jared Goff | 18.95 | 44.3% | 41.3% |
| QB | 18 | Jordan Love | 18.11 | 36.3% | 33.0% |
| RB | 1 | Jahmyr Gibbs | 25.71 | 77.4% | 76.8% |
| RB | 16 | Chuba Hubbard | 14.5 | 70.1% | 65.2% |
| RB | 31 | Josh Jacobs | 10.43 | 53.6% | 40.1% |
| RB | 32 | Jordan Mason | 10.35 | 53.0% | 39.3% |
| RB | 37 | Alvin Kamara | 8.5 | 36.9% | 18.4% |
| RB | 44 | Keaton Mitchell | 7.69 | 28.6% | 9.8% |

- Top movers of the blended DDF Value at 12-team full PPR (before scaled to the pie; eleven-season `m`, from `docs/claude-log/2026-10-09-jeg521-expected-starts-before-after.md`):

| Player | Position | Tier | Before | After A | Change |
| --- | --- | --- | --- | --- | --- |
| Jaxon Smith-Njigba | WR | starter | 51.37 | 66.99 | +15.6 |
| Ja'Marr Chase | WR | starter | 46.24 | 59.98 | +13.7 |
| Amon-Ra St. Brown | WR | starter | 44.48 | 57.42 | +12.9 |
| CeeDee Lamb | WR | starter | 45.56 | 58.22 | +12.7 |
| Puka Nacua | WR | starter | 47.17 | 59.79 | +12.6 |
| Chris Olave | WR | starter | 37.34 | 47.52 | +10.2 |
| Justin Jefferson | WR | starter | 35.09 | 44.12 | +9.0 |
| Jahmyr Gibbs | RB | starter | 71.88 | 80.28 | +8.4 |
| Zay Flowers | WR | starter | 32.3 | 40.64 | +8.3 |
| Nico Collins | WR | starter | 33.63 | 41.88 | +8.2 |
| Bijan Robinson | RB | starter | 65.39 | 73.52 | +8.1 |
| Romeo Doubs | WR | bench | 13.4 | 5.44 | -8.0 |

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
- *C, keep the fixed 15% (OC-2 as decided).* For: no change after JEG-508.
  Against: the bench tier stays near 15% against the 8.0% to 9.9% measured,
  a starter-level point is often worth less than a bench-level point (0.7x
  to 1.9x), and one number is wrong for most settings (about 9.6% at 8
  teams, 8.0% to 8.6% at 12 and 14, falling through the season).
- **Recommendation: A**, with the bench share shown as a computed readout and
  the slider kept only as an override (JEG-533). B is a budget patch on a structure the manifesto
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

**ES-12 League week inputs (proposed, JEG-525 item c; not in the spec until
approved).** Today the window is fixed: from the content week + 1 to NFL
week 18. Proposed reader inputs, with defaults that match a standard league:

| Input | Default | What it changes |
| --- | --- | --- |
| Content week `W` | the build's week | already used; becomes visible and settable on the dashboard |
| Last regular-season week `R` | 14 | the "regular" window below |
| Playoff weeks `P` | 15 to 17 | the "season" and "playoffs" windows; week 18 drops out of every window |
| Objective | season | "season" = weeks `W+1` to the last playoff week; "regular" = `W+1` to `R`; "playoffs" = `P` only |

Effect on ES-1 and ES-4, by input:
- `b` (ES-1, ES-4.1-2) is the bye share of the objective window's team-weeks,
  not of weeks `W+1` to 18. "Playoffs" has `b = 0` (no byes after week 14).
- `sigma` drift (ES-1) scales with the square root of the distance from `W`
  to the window's midpoint, so a playoff objective sees a wider bell curve
  (the level at week 16 is further away than the average remaining week).
- `m` (ES-1) is unchanged for "season" and "regular" (a per-game hazard).
  For "playoffs" it is measured in the playoff weeks themselves for players
  healthy at the end of weeks 1-5 / 1-9, which carries the season-ending
  absences that pile up before then: QB 15.6%, RB 19.7%, WR 14.7%, TE 18.6%
  (2015-2025) against 11.0 / 15.3 / 11.7 / 14.4% per game.
- ES-2 to ES-5 are unchanged.

Measured at Week 5, 12-team full PPR (`tools/season_window_effect.py`):
bench tier 8.65% today (weeks 6-18), 8.65% "season" (weeks 6-17), 8.71%
"regular" (weeks 6-14), 8.71% "playoffs" (8.47% if the per-game hazard were
kept). The pie on fill-in parts: 5.31%, 5.43%, 5.89%, 4.71%. So the inputs
matter for the dashboard and for what the numbers mean, but they move the
bench share by less than a point: a playoff window removes the byes but adds
uncertainty and accumulated injuries, and they nearly cancel. The objective
switch does not price eliminated teams, standings or a horizon (manifesto
sections 9 and 10, MR-22): those need the roster import (JEG-481).

**ES-13 What the share does and does not capture (JEG-525 items a and b).**
The share is for an average team in the league setting. It captures, for
every rostered player, the chance his projection sits above the starter line
and the chance a starter ahead of him on an average team is out (bye or
injury). It does not capture:
1. *The handcuff contingency (fundamental, not only portfolio).* A backup
   running back is held for the jump he makes when his own NFL team's lead
   back misses. Measured over 2015-2025 (`tools/handcuff_jump.py`): backups
   score 7.2 points per game with the lead back playing and 12.8 with him
   out; behind a top-12 lead back, 6.9 to 13.4, above the 12-team starter
   line about 55% of the time. The share puts a symmetric bell curve on the
   backup's own projection, which cannot produce that jump, so a pure
   handcuff below the waiver line is valued at 0 (Week 5, ESPN: Sione Vaki
   behind Gibbs 4.16 points per game, value 0; Justice Hill behind Henry
   4.74, value 0) and his Stash signal `P(X > l)` is also 0. Rough size of
   what is missing, Vaki: 0.928 (not a bye week) x 0.153 (lead back out) x
   0.847 (Vaki himself available) x (13.4 - 4.90 surplus at the promoted
   level) x 0.78 (projected to start at that level) = 0.79 points of surplus
   per week reaching a lineup, the same as Keaton Mitchell's whole 0.80
   (RB44, 7.69 points per game, share 28.6%). MR-26.
2. *The own-handcuff hedge (portfolio).* Holding your own starter's backup
   pays exactly in the weeks your starter is out, so its value to you is
   higher than to the average team. That needs the roster (manifesto
   section 6, JEG-481) and is not a property of the player.
3. The weekly matchup swap (MR-23), discounting and the playoff objective
   (ES-8.3, ES-12), known absences (MR-20).

**ES-14 Reader settings and the bench-share readout (es-value-001, approved
2026-10-09).** The bench share is not an input. The reader sets its causes;
the page shows the result.

| Setting | Where | Default | Enters |
| --- | --- | --- | --- |
| League size, starters, bench size | existing league options | 12 teams, QB 1 / RB 2 / WR 3 / TE 1 / FLEX 1, bench 6 | ES-2, ES-3 |
| Last regular-season week, playoff weeks | league options (JEG-527) | 14; 15-17 | the window (ES-12) |
| Optimize for | league options (JEG-527) | whole season | the window, and `m` in the playoff weeks for "playoffs" |
| Injury history | Advanced | recent seasons (half-life 5 seasons, MR-25); or all seasons equal | `m` |
| Projection confidence | Advanced | 1 (as measured); 0.5 = trust projections twice as much | multiplies `sigma`, its floor and the chart `sigma` |
| Bench-share override | Advanced, off | off | when on, replaces the computed share as the bench group's weight (VP-3.4); the readout says "override" |

- **Building blocks.** `config/lineup_parameters.json` (schema
  `lineup-parameters-config/2`) holds per position `m` (recent, all),
  `m_late` (the same in the season's fantasy-playoff weeks), `sigma_now`,
  `sigma_weekly`, `sigma_floor`, the bye table, the defaults, and the
  resolved default. `derive_lineup_parameters.resolve(cfg, objective,
  injury_history, league_weeks, content_week, projection_confidence)` is the
  Python reference the engine mirrors: window (ES-12), `b` over the window,
  drift horizon = the gap before the window plus half its length, `sigma =
  sqrt(now^2 + weekly^2 x horizon) x confidence`.
- **Readout.** "Bench share this week: QB x%, RB y%, WR z%, TE w%, from your
  league settings" = the bench tier's share of each position's value and of
  the pie under A (`expected_starts_model.bench_share_readout`, the Python
  reference). Week 5, 12-team full PPR, defaults: QB 22.7%, RB 9.1%, WR 6.4%,
  TE 12.6%, overall 9.1%. QB is high because the quarterback curve is flat
  near the line: QB13-21 sit close to the starters.
- **Measured at the defaults** (Week 5, `docs/claude-log/2026-10-09-jeg533-*`):
  bench tier 8.5% to 9.7% across the 12 settings, zero inversions. The
  settings move it little (12-team full PPR): injury history all 9.08%,
  regular season 9.12%, playoffs 9.07%, content week 12 8.58%, projection
  confidence 0.5 8.64%. The parameter tables in ES-1 and ES-7 above are the
  decision build (two weeks' data before the merge of main, weeks 6-18,
  equal weighting); the approved defaults are in the claude-log files named
  here.
- **Portfolio.** Where bench value differs most between readers is their own
  roster; that input is the roster import (JEG-481), not a percentage.

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

### Open choices: decided (Jeremy, 2026-10-09, quoted on JEG-508)

All eight are decided. The "Recommended" column is the first draft's
recommendation, kept for the record; "Decided" governs.

| # | Choice | Options | Recommended (first draft) | Decided 2026-10-09 |
| --- | --- | --- | --- | --- |
| OC-1 | Pie total per league setting | (A) 28 per starting slot: `28 x T x starters per team` (2,688 at the 12-team default). (B) 16 per rostered slot: `16 x T x (starters + bench)` (also 2,688 at the default; grows with bench size) | A | **A**, 28 per starting slot (VP-5.1) |
| OC-2 | Bench share default | (A) Source-implied; the slider overrides at the source level before averaging. (B) 15% applied to every source, like today. (C) 15% per position, like today's two-tier | A | **15%**: "15% is right. There is no way 35% is rational math." The DDF weights give bench 15% of the pie and every source is normalized to that; source-implied share is not used (VP-3.4, VP-4) |
| OC-3 | How a player's value splits between starter and bench | (A) Slices. (B) Whole player in his role's group | A | **A**, slices; the slice only splits a player's value into the starter and bench groups, whose totals the DDF weights set with bench at 15% (VP-2.6) |
| OC-4 | Flex fill per source | (A) Greedy best remaining by the source's own values. (B) Today's D'Hondt surplus-weighted flex | A | **Best remaining by assumed (projected) points, not VORP**: the mean points per game of the included projections, the same order as slot filling (VP-2.2) |
| OC-5 | A group a source can't fund | (A) Its budget moves to the same position's other group. (B) Left unpaid and reported. (C) That source's group shown unavailable | A | **Fill-in, approved as proposed**: "We need to fill in more players to get to vorp for all rosterable players." Rosterable = starters + bench by projected points; ratio to other charts on the last ~10 shared players, median; else the chart's own curve against projected points; never above the chart's lowest listed player; marked estimated and counted (VP-2.4). The budget move stays as the residual rule (VP-5.3) |
| OC-6 | Weights for the charts-only and projections-only versions | (A) One DDF weight set. (B) Each family's own average | A | **A**, one shared weight set (VP-4.5) |
| OC-7 | Projections in the Indexed tab | (A) Show their Adjusted values. (B) Hide them | A | Available in "Trade charts (as published)" as their Adjusted values, **off by default** (VP-6.4, VP-11) |
| OC-8 | Which players set a chart's Indexed factor | (A) Listed players with a blended DDF Value, zeros included. (B) DDF Value above 0 only | A | **A** (the lead's call after Jeremy found the question unclear; revisit if he wants) (VP-6.4) |

**Follow-up open choice (not part of JEG-508's eight).**

| # | Choice | Options | Recommended | Decision |
| --- | --- | --- | --- | --- |
| OC-9 | After JEG-508 ships, replace the fixed 15% with expected starts (ES-9; decided A, 2026-10-09) | (A) Replace the VP-2.6 slices with the expected-starts parts (ES-5). (B) Keep the slices; set each position's bench budget from expected starts. (C) Keep the fixed 15% as decided (OC-2) | A: bench tier 8.0% to 9.9% across the 12 settings and a starter-level point worth 1.1x to 3.5x a bench-level point, against about 15% and 0.7x to 1.9x under C | **A** (Jeremy, 20:51, JEG-533): the bench share becomes a readout of the reader's settings (ES-14); one override, off by default |

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
  **Superseded again (JEG-508 OC-5, Jeremy 2026-10-09)**: the ratio, cap,
  loop and hiding rules below are replaced by the VP-2.4 fill-in. Only charts
  are filled; the players filled are the rosterable set by projected points;
  the ratio is fitted on the last 10 shared players and the median over peers
  is taken; a curve against projected points covers players no chart lists;
  and estimated players are shown, marked "estimated".
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
>
> **Superseded again (JEG-508 OC-4, Jeremy 2026-10-09)**: flex is filled by
> best remaining by projected points (the mean points per game of the
> included projections), not by any source's own values. One league
> allocation serves every source (VP-2.2).

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
>
> **Updated (JEG-508 answers, 2026-10-09)**: the superflex slot is now filled
> by projected points in the one league allocation (VP-2.2b, Lead's reading
> of OC-4), not on each source's own values.

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
