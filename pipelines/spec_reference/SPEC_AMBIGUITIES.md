# Spec ambiguities found by the clean-room reference (JEG-508)

Written while implementing `value_pipeline.py` from docs/methodology.md
"Value Pipeline (source-neutral, 2026-10-09)" only. For each item: what the
text says, the reading this implementation takes (the most literal one), and
whether the worked example pins it. None of these changes a value in the
worked example (all 4,455 pinned leaves match to 1e-6); they matter on live
data or in edge cases. Ids are cited in the code as `SA-n`.

Status as of 2026-10-09: open for the lead; nothing here was guessed silently.

## Inputs and data (the spec names concepts, not files)

- **SA-1 Current-week natives.** VP-0 says "the saved 12-team list at the
  scoring" but not which file. Taken from the section's
  `combos["<scoring>_12"]` (`fantasycalc`: `_12_qb1`) `.native` in
  `data/fixtures/current/comparison-sources-data.json`. Projections use
  `combos["<scoring>_<T>"].native` (identical across `T` in the snapshot).
  The committed `dist/assets/comparison-sources-data.json` is an older build
  (built_at 2026-10-03, vs 2026-10-09 for the snapshot), so the snapshot is
  the default; `--fixture` points at another build.
- **SA-2 Superflex overlay adds players?** VP-0: `native_superflex`
  "replaces the 1-QB native for the players it covers". Read literally: it
  replaces a value that exists and never adds a player listed only in the
  overlay (FantasyCalc's overlay has 197 names vs 196 in its 1-QB list).
- **SA-3 Prior week at SF >= 1.** VP-8 runs the prior week on "the same L",
  but `data/history/week-N.json` keeps only the 1-QB `natives` for charts (no
  `native_superflex`). Taken: the prior week at a superflex setting uses the
  charts' 1-QB natives. The spec should say whether a missing prior overlay
  means "no prior week" for that chart at SF >= 1 instead.
- **SA-4 Which prior snapshot.** VP-1.2 / VP-8 say "prior-week snapshot" with
  no location. Taken: `data/history/week-<content_week - 1>.json`, an entry
  with `complete: true` that has data at the scoring; `content_week` from
  `data/history/index.json`. Projection prior `ppg` there is rounded (2 or 6
  dp) while the current natives are not; the spec does not say whether that
  matters.
- **SA-5 Holds and "unpublished".** VP-1.1 names `validationHold` /
  `promotionHold` on the section; neither key exists in the live snapshot, so
  no source is held. "Unpublished" (a weekly chart whose content week is
  older than the current one) is read from `data/history/index.json`
  `served[s].week < content_week`, charts only. The spec does not say where a
  section's content week lives.
- **SA-6 Default roster and the superflex combo.** The VP section never states
  the default slot counts. Taken: QB1 RB2 WR3 TE1 FLEX1 BENCH6 ("standard
  roster", elsewhere in methodology.md), which gives the 8 starters and the
  1,792 / 2,240 / 2,688 / 3,136 pies VP-5.1 quotes. The superflex combo is
  12 teams, that roster plus SF1 (pie 3,024); VP-5.1 does not give its
  scoring, PPR was used.

## Ordering and arithmetic

- **SA-7 Cross-position sum order.** VP-0 "sums run in sort order" defines
  order within a position only. For sums across positions (G_s, Indexed's
  `sum(ddf_value)` / `sum(native)`, the DDF mean across sources) this uses
  position order QB, RB, WR, TE then the source's sort order, and the source
  order espn, cbsros, razzball, cbs, fantasycalc, fantasypros, usatoday.
  Effect is at the 1e-12 level.
- **SA-8 `v_i = bsl_i + ssl_i` "exactly".** In doubles `max(0, x - w)` and
  `bsl + ssl` can differ by one ulp. `v_i` is computed by its own formula and
  `V_i = v_i x Pie / G_s` uses it, so a source's V total equals the pie to
  ~1e-12, not bit-exactly.

## Steps where the literal text leaves a choice

- **SA-9 Indexed when the factor is null.** VP-6.4: if the native sum is
  `<= 0` or `shared` is empty, "Indexed is null", and then "Players below
  rosterable depth follow rule 2 (0)". Read literally: listed and estimated
  players are null, below-depth players at priced positions are still 0.
  Probably the intent is null for the whole chart; the text should say.
- **SA-10 Tier ranks and null DDF.** VP-7.3 ranks "within a position by
  blended DDF Value". Players with no DDF Value have no tier; taken: they do
  not occupy a rank either (ranks count only numeric DDF values, zeros
  included).
- **SA-11 VP-4.1 exclusion is per position.** "do not have `no_players` at
  `p`" is applied only to the mean at `p`: a source that does not price TE
  still contributes its QB/RB/WR starter mix (whose TE share is 0 by
  construction, computed over its own positions). The resulting `Sraw` is
  then renormalized by VP-4.3. The spec could instead mean "drop the source
  from every mean"; the two differ whenever a source misses a position.
- **SA-12 Rows of sources outside `I` for other reasons.** VP-6.1 "every
  player any source lists, held sources included". Taken: every source with
  values at `L` (held, unpublished or without a prior week) adds rows, since
  VP-1.4 shows all of them.
- **SA-13 Degenerate week below-depth zeros.** VP-2.2 f (no projection in
  `I`): no rosterable set and nothing estimated. VP-6.2 still says a chart
  that neither lists nor estimates a player "at a position it prices" is 0.
  Taken literally: 0, so in a degenerate week every player a chart does not
  list is 0 on it, at any depth.
- **SA-14 Unusable-peer record.** VP-11's `estimates.peers` lists
  `fitPlayers, ratio, estimate`; the text does not say whether unusable peers
  appear. Taken: they appear with `usable: false`, `ratio`/`estimate` null
  and a reason. Not pinned by the fixture.
- **SA-15 Unfunded-group move shape.** VP-5.3 / VP-11 name `unfundedGroups`
  but not the record of a moved budget. Here: `unfunded_moved: [{from, to,
  budget}]` and `unfunded_groups: [{group, budget}]` (unpaid). The fixture
  pins only the empty list.
- **SA-16 The prior week's sources.** VP-8.1 runs the prior week for "each
  source in `I`". Sources outside `I` get no prior values. With
  `included_set`, every source in `I` has a prior snapshot by construction,
  except in a first week, where there is no prior week at all.

## Observations on live data (not ambiguities, for the lead)

- PPR 12 (live snapshot, 2026-10-09): every included source totals the pie
  (2,688) with no unfunded group; the fill-in estimates 84 chart values
  (CBS 58 of them); 520 of 737 rows have blended DDF 0. The QB starter
  weight is 0.054 (1-QB league: the 12th QB's projection is high, so QB
  starter surplus is small), and the top QB's blended DDF is 38.9 against
  the top RB's 89.9.
