# How projections reach the chart DDF Value: an offline ledger

JEG-1280, 2026-10-29. Research only, offline, on pinned inputs. This changes no
engine, value, default, tolerance or ranking, and nothing here is published.
It follows up the side finding on JEG-1047 (comment e6055a31): "projection
changes also move DDF Value (chart-based)". JEG-1047's own waiver-line
correction (JEG-1244, #1077) and JEG-1249 (#1105) are separate and untouched.

- Numbers: [ledger-readout.md](ledger-readout.md), generated from
  [ledger.json](ledger.json) (816 pairs, one per line).
- Tool: `tools/research/projection-influence-ledger/ledger.py`.
- Frozen inputs: `tests/fixtures/projection-influence-ledger/frozen_inputs.json`.
- Tests: `tests/test_projection_influence.py`.

## The question

DDF Value averages the trade charts only, and the settled JEG-1073 decision
(Jeremy, 2026-10-25) keeps it that way. Do projection inputs still move it?
If so, through which steps, and by how much per point of projection? This
ledger measures that. It does not reopen whether DDF Value should be the
chart average.

## Definitions

Jeremy's wording (2026-10-29 brief) sits beside what the code computes at the
pinned SHA. The code column is evidence, not a new definition.

| Term | Jeremy | The engine at `430791c4` |
|---|---|---|
| DDF Value | "the average of the weight-adjusted indexed values" | `ddf_value`, the blended version. It is the equal-weight mean of the Adjusted values of the trade charts that are included and visible: `pipelines/value_reference.py:100` (`DDF_FAMILY["blended"] = "chart"`), `:1188-1194`; `value-model.js:1349` (`blendedI = chartsI`). Adjusted is a chart's value above its waiver line, re-weighted to the DDF position and starter/bench weights (`value_reference.py:859-868`). The page's Indexed view is a different series whose basis is DDF Value; the ledger reads DDF Value only. |
| DDF Projections | "the average of the imputed values across projected sources" | `ddf_value_projections`: the equal-weight mean of the included, visible projection sources' Adjusted values (`DDF_FAMILY["projections"]`). The VP-2.4 fill-in estimates run for charts only (`value_reference.py:960`). The ledger reports DDF Projections only for context. |
| Weekly vs ROS | "do not blend weekly data with ROS data, ever." | At this fixture the four charts are weekly ("Week 8") and the three projections are rest of season. No experiment moves a value from one source to another, and the guard refuses any pair that changes a source's horizon label. |

## Engine and inputs

- **Engine SHA:** `430791c41ca9578d878c14c3a37d37a0f3fe0670`, main at
  2026-10-29 17:03 UTC, read only. The last commit there that touched the
  engine or reference is `2e7a2c7c` (JEG-1142).
- **Limitation of this snapshot:** at this SHA each projection source's waiver
  line is one player (`value_reference.py:698`, `w = work[n_rost][1]`). The
  seven-player waiver-line average Jeremy approved (pick A on JEG-1244, built
  on #1077) is not on main here. Nothing below measures it, implements it, or
  speaks for the engine once it lands.
- **Engine file hashes:** recorded in the ledger's `provenance.engine_files`.
  `run` refuses to write a ledger if any of these files changed:
  - `value_reference.py` `sha256:98537b44…`, blob `65f88568`
  - `lib/roster_convention.py` `sha256:92672495…`
  - `config/market_bench.json` `sha256:cb6ce8eb…`
  - `value-model.js` `sha256:ad93b1f6…`, blob `e9d4584a`
- **Inputs:**
  - The committed fixture `data/fixtures/current/comparison-sources-data.json`
    (built 2026-10-29 16:16:53 UTC, `sha256:42fcf8bd…`) and `players.json`
    (`sha256:4a241a62…`), at the pinned SHA.
  - The content-week clock is pinned to 2026-10-29.
  - `freeze` copied the exact per-scoring natives the engine reads (natives
    `sha256:9aab5dc1…`). Running the pipeline on that copy reproduces
    `Setting.result()` exactly (largest difference 0.0) at all 12 settings.

| Source | Family | Horizon | Fetched | Vintage | Hold at this build |
|---|---|---|---|---|---|
| USA Today | chart | Week 8 | 2026-10-27 | 2026-10-27 | none |
| FantasyCalc | chart | Week 8 | 2026-10-29 14:07 UTC | Week 8 | none |
| FantasyPros | chart | Week 8 | 2026-10-29 12:35 UTC | 2026-10-27 | none |
| CBS | chart | Week 8 | 2026-10-28 12:23 UTC | Week 8 | none |
| ESPN | projection | rest of season | 2026-10-29 16:16 UTC | snapshot 2026-10-28 | none |
| CBS ROS | projection | rest of season | not recorded | 2026-10-29 | amber: fidelity, publisher vs stored |
| Razzball | projection | rest of season | not recorded | 2026-10-27 | amber: fidelity, publisher vs stored |

Amber holds keep a source in I and visible (JEG-726), so all seven sources
price at baseline.

## Method

1. **Pairs with fixed chart inputs.** Each experiment is a pair of runs at
   one setting (3 scorings × 4 league sizes, default roster). In each pair:
   - The charts' natives and the included and held sets are identical.
     `check_projection_only` refuses the pair otherwise, and also refuses a
     pair that changes a source's horizon or changes no projection at all.
   - Only projection natives differ. Each pair records a hash of the chart
     inputs and the projection-input hashes for both sides.
2. **Four stages.** The pipeline was read at the pinned SHA, and projection
   numbers reach a chart's Adjusted values at four points. Each is a stage
   output the charts consume (paths below):
   - `lineup`: starters per position;
   - `bench`: bench seats per position;
   - `fill_in`: the estimates for rosterable players a chart does not list;
   - `position_weight`: the projection sources' mixes inside the DDF
     weights.
3. **Attribution.** For each pair, 16 hybrid runs give the charts each
   stage's output from either side. Each player's move is split by the
   Shapley value over the four stages. The **residual** is what still moves
   with all four held at baseline, and it is reported, never folded into a
   stage. A hybrid run swaps stage outputs inside the tool's process only
   (it wraps `_source_lines` for charts and `ddf_weights`). The tool checks
   that an unfrozen run is unchanged.
4. **JS cross-check.** Both sides of every pair at PPR 12 and Standard 8
   (136 pairs) were re-run on the production engine, `value-model.js`, at the
   same SHA. The largest difference from the reference was 4.3e-14 DDF Value
   points, in levels and in moves. The stage split runs on the reference
   only, since the JS engine has no hook.

## Where projections enter the chart DDF Value (file:line at `430791c4`)

| Path | Built from projections at | Consumed by every chart at | JS engine |
|---|---|---|---|
| Direct chart inputs (held fixed) | none | `value_reference.py:691-693` (the chart's own listed natives start its work list) | `value-model.js` work lists |
| Mean projected points | `:892` (projections in I, held ones included), `:921` | lineup, bench, fill-in below | `:913-925` (`projI`) |
| lineup | `allocate` `:312` (flex seats ordered by mean points), call `:925` | `:957` (`s_alloc = alloc`), `:694` (`n_start`): starter line and expected-start bands | `:936`, `:1067` |
| bench | `_vorp_bench_allocate` `:322` (scored by mean points) | `:694` (`n_rost`), `:698` (the chart's waiver line is `work[n_rost]`) | `:936`, `:1067` |
| fill_in | `:927` (fill set = the mean-points order up to the rostered count) | `:966-968` (estimates for unlisted players); curve path reads mean points `:378-395` | `:939-941`, `:1021-1044`, `:1087` |
| position_weight | each projection source's own 8-group weights from its own lines (`:971`) | `ddf_weights` averages every included source, held ones too (`:811-816`; computed share is the default) → budgets `:981` → each chart's rates `:859` → Adjusted `:868` | `:1222-1260` |
| Held source | stays in I (`Setting.state` `:1743-1753`) | only the DDF blends drop it (`_ddf` `:1148`) | `:874`, `:1444` |
| Absent vs zero | `mean_ppg` averages listed values: a 0.0 counts, an absent player does not (`:892-901`) | a chart that does not list a player gives him 0 (`:1089-1090`), so any player a projection lists gets a chart DDF row (`:1169`) | `:1368`, `:1385` |

## What the ledger measures

The full tables are in [ledger-readout.md](ledger-readout.md). Below, a move
means a change in another player's chart DDF Value; the edited player is
excluded.

- **Projection inputs move DDF Value.** Moving one projection source's
  waiver-line player by ±1 PPG moved at least one other player's DDF Value
  in 270 of 288 pairs (215 by 0.05 or more).
  - The median worst move was 0.110 and the largest 1.822 (Standard 10, CBS
    ROS WR −1).
  - DDF Projections, the series those numbers feed directly, moved by a
    similar median of 0.109.
  - A +1 PPG change to the top player moved DDF Value in all 144 pairs, by
    0.214 at most.
- **Most of it goes through the position weights.** For the waiver-line
  moves, the four stages carry this share of the absolute attribution:

  | Stage | Share | Pairs where it moved anyone |
  |---|---|---|
  | position_weight | 86.3% | 270 |
  | fill_in | 5.3% | 36 |
  | bench | 4.9% | 3 |
  | lineup | 3.5% | 1 |

  For top-player moves it is 100% position weight. A projection change
  shifts that source's own mix of value across positions and starter/bench.
  The DDF weights average that mix with the charts', and every chart is then
  repriced on the new weights.
- **It crosses positions.** In the worst waiver-line pair, the move is in
  the CBS ROS WR line, but the largest moves are at RB (+1.82 for Jahmyr
  Gibbs). That pair also moved one flex seat from WR to RB and changed bench
  seats. Across waiver-line pairs the worst move at another position (1.822)
  exceeds the worst at the edited position (1.656).
- **The lineup stage matters when a flex seat flips.** Removing a player ESPN
  lists at 0.0 (JEG-496) moved DDF Value in only 8 of 48 pairs. Those 8 are
  where mean points crossed a flex or roster boundary: up to 2.104 (Half PPR
  14, WR). There, lineup carried 45.7% and position weight 45.0%.
- **Absent and zero are not the same.**
  - A zero listing counts in mean points as 0.0. An absent player is left
    out of the mean.
  - A player who is listed by a projection and by no chart gets a DDF Value
    row of 0, or a fill-in estimate.
  - Removing the best such player from every projection removed his row in
    all 48 pairs. It moved other players in 16 of them, by up to 1.757
    (Standard 14, RB), through the fill set (13.5%) and the weights (81.3%).
- **Excluding a source cuts it off; holding it does not.**
  - With the source excluded from I on both sides, the same +1 waiver-line
    move changed nothing in all 144 pairs. Every stage was exactly 0.
  - With the source held (in I, hidden from the blends), all 144 pairs moved
    every player exactly as with the source visible, by up to 1.380.
  - So a red hold hides a projection from DDF Projections, but its numbers
    still set the mean points, allocation, fill-in and weights that price the
    charts. This matches the JEG-569 design note in the code (a held source
    "stays in the pipeline (weights, pie, allocation)"). The ledger now puts
    a size on it.

## Measured coupling vs earlier hypotheses

| Earlier statement | Where | What this ledger measures at `430791c4` |
|---|---|---|
| Projection changes move the chart DDF Value "by up to ~0.6 through the shared lineup/bench model, under every rule" | JEG-1047 comment e6055a31; `docs/research/jeg1047-waiver-line.md` on #1077 | **The coupling is confirmed. The channel was not.** For waiver-line moves, lineup and bench carry 8.4% between them (moving anyone in 1 and 3 of 288 pairs); position weights carry 86.3%. The magnitudes don't compare. That run used a different fixture build (2026-10-28 23:27 UTC), ±0.5 and ±1 moves, seven candidate line rules, and same-position players only. Here the largest moves are cross-position. The two figures are not reconciled. |
| A held source "contributed to weights and pie so no other source's Adjusted/VORP values change" | JEG-569 part 2 comment, `value-model.js:870-872` | **Consistent.** Holding a source does not change the charts' values. It also means a held projection's changes still reach DDF Value one for one (144 of 144 pairs identical). |
| JEG-1073's open consequence: with charts as DDF, Indexed sits on the chart average | JEG-1073 | **Not measured.** It concerns Indexed, not DDF Value. |

## Unattributed residual

The residual is 0 exactly, in all 816 pairs and for every player. With the
four stage outputs held at baseline, chart DDF Value equals baseline bit for
bit. At this SHA, for these perturbations, the four stages are the whole
route from projection natives to DDF Value. The bench and lineup split
follows `allocate`'s output fields (`starters`, `bench`); interaction between
stages is split equally by the Shapley rule.

The residual does not cover changes in which rows exist. Rows added or
removed are counted separately (48 removed, all in the projection-only-player
experiment).

## Choices for Jeremy

None of these is selected, and none changes a number until Jeremy picks.
Multiple choice, per the working agreement (JEG-850):

- **A. Retain and document.** Write the measured coupling into the
  methodology: DDF Value averages the charts, priced on the shared league
  model. Mean projected points set starters, bench seats and the fill-in;
  the DDF weights average every included source's mix, held ones included.
  No further work.
- **B. Investigate the weights and the weekly vs ROS rule.** Question: does
  "do not blend weekly data with ROS data, ever" cover the pricing stages,
  where the DDF weights average the weekly charts' mixes with the ROS
  projections' mixes, or only averaged values? This path carries 86% of the
  measured coupling. The deliverable would be options with measured effects,
  not a change.
- **C. Investigate held sources.** Question: should "held" mean out of the
  pricing stages (mean points, allocation, fill-in, weights) as well as out
  of the blends? Today a held projection moves DDF Value exactly as a
  visible one.
- **D. Investigate zero listings in mean points.** Question: should a 0.0
  listing (ESPN's JEG-496 zero, or any source) count in mean points the way
  a real projection does? In this snapshot one such listing moved DDF Value
  by up to 2.104 when it decided a flex seat.

Recommendation, not a selection: **A now**, and put B, C and D on
`docs/math-review-agenda.md` for the coordinated math review rather than
answering them one at a time. That file is outside this ticket's paths; the
lead or Codex can add the rows.

## Run it (offline)

```bash
python3 tools/research/projection-influence-ledger/ledger.py run --jobs 6
```

`run` rewrites `ledger.json` and `ledger-readout.md` from the frozen inputs:
about 2 minutes on 6 cores, 9 sequentially.

```bash
python3 tools/research/projection-influence-ledger/ledger.py check --jobs 6
```

`check` reruns everything and compares it with the committed ledger byte for
byte.

```bash
python3 -m unittest tests.test_projection_influence
```

18 tests, about 8 seconds.

`ledger.py freeze` re-copies the inputs from `data/fixtures/current/`. Run it
only to move the ledger to a newer fixture: that changes the pinned inputs,
so rerun `run` after it.

Proposed for the CI owner (this ticket does not edit the Makefile): add
`python3 -m unittest tests.test_projection_influence` to `test-unit-modules`.
The committed-ledger reproduction test skips itself, naming the files, once
any pinned engine file changes.

## Limitations

- **One-player waiver line.** The pinned SHA has it; the approved
  seven-player average (JEG-1244 / #1077) is absent from this snapshot.
  Results speak only for this SHA.
- **One snapshot.** One fixture build (2026-10-29 16:16 UTC) and the default
  league (1 QB, 2 RB, 2 WR, 1 TE, 1 flex, 7 bench, no superflex). Default
  lineup parameters and value basis, no DDF input selection, no overrides.
- **No week view or prior week.** The History path is off; every source is
  priced on its current fixture values.
- **Synthetic perturbations.** ±1 PPG, a zero listing made absent, a
  projection-only player removed. They show where coupling exists and its
  size per edit. They are not a forecast of weekly movement, and they make
  no claim about which values are more accurate.
- **Reporting cut.** "Moved" uses 0.05 DDF Value points, the JEG-1047
  readout's page-rounding cut, for comparability. It is not a tolerance;
  "any move" uses a 1e-9 float-noise floor.
- **JS coverage.** The production JS engine confirms totals at two of the
  twelve settings. The stage split is measured on the Python reference only.
