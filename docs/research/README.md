# Research

Durable evidence behind the tool's opinionated choices (JEG-604, 2026-10-12). Research posts on the site (JEG-543, JEG-544, JEG-557) link here; every claim in a post should link to a page below and to the script that produced it.

| Page | What it holds |
|---|---|
| [bench-rule-research.md](bench-rule-research.md) | Market bench versus fundamental bench: draft ratios, the five-rule scorecard, bench-spot value, field scan. |
| [roster-convention-audit.md](roster-convention-audit.md) | The JEG-556 audit of inconsistent roster rules, and the convention that replaces them. |
| [qb-bench-share.md](qb-bench-share.md) | The 22.6% QB bench share, why it was an artifact, and what superseded it. |
| [research-post-1-facts.md](research-post-1-facts.md) | JEG-544 decisions and the fact tickets, with status. |
| [post-1-review-2026-10-23.md](post-1-review-2026-10-23.md) | Post 1 review: each of Jeremy's comments mapped to the change made (JEG-544, #846). |
| [ddf-predictive-plan.md](ddf-predictive-plan.md) | JEG-943 internal plan behind post 10: data inventory, evaluation protocol, what is missing. |
| [source-discovery-2026-10-15.md](source-discovery-2026-10-15.md) | JEG-622/JEG-623 source shortlist and FantasyFootballAnalytics access check. |
| [jeg613-q4-context.md](jeg613-q4-context.md) | JEG-613 open question 4: whether bias-adjusted charts belong in DDF Value, written for Jeremy's decision (2026-10-22). |
| [jeg613-scoring.md](jeg613-scoring.md) | JEG-613 read-only audit of value goals, scoring and the engine at the 12 standard setups, with Jeremy's answers (2026-10-22). |
| [qb-values-review-2026-10-16.md](qb-values-review-2026-10-16.md) | JEG-702 investigation of QB values on a 2-QB board and the part-timer per-game question; no value math changed. |
| [posts04-06-refresh-2026-10-29.md](posts04-06-refresh-2026-10-29.md) | JEG-545 refresh of posts 4 to 6: each stale claim, the current rule and its code, how the new figures were checked, and what waits before publication. |
| [jeg-1195-weekly-inputs-readiness.md](jeg-1195-weekly-inputs-readiness.md) | JEG-1195 evidence inventory for the retired Versus Vegas and waiver products, today's weekly inputs, a shared input contract and ready/blocked slices (2026-10-29), and the weekly FantasyPros tables (applied 2026-10-29; JEG-1268 null-safe follow-up proposed, not applied). |
| [jeg1047-waiver-line.md](jeg1047-waiver-line.md) | JEG-1047: the projection waiver line rests on one player; sensitivity on the 12-combo grid and the line-rule options for Jeremy (2026-10-29). Script `tools/research/jeg1047_waiver_anchor.py`. |
| [jeg-1198-ros-rank-anchor.md](jeg-1198-ros-rank-anchor.md) | JEG-1198: whether rest-of-season rankings can anchor trade values (rank curves, scarcity, aggregation, worked examples); research only, no-go recommendation (2026-10-29). Current finding first: expert ROS rankings are readable (option C feed) and track DDF Value closely, so a review check, not a value; the first study's modeled-only availability audit is kept as dated history. Joins on canonical player_key; baseline recipe and its reproduction check documented (JEG-1251). Scripts `tools/research/ros_rank_anchor*.py`, `ros_rank_keys.py`, `ros_rank_baseline_check.py`, data `data/jeg1198/`. |
| [jeg1286-flex-flips.md](jeg1286-flex-flips.md) | JEG-1286 flex and bench slot flips: how often one fringe player at the flex or bench cutoff reprices a position (real bakes and a one-player sweep), and options A to D for Jeremy's pick (2026-10-29). Script `tools/research/jeg1286_flex_flips.py`, figures in [data/jeg1286_flex_flips.md](data/jeg1286_flex_flips.md). |

## Post drafts

| Post | File | Ticket | Status |
|---|---|---|---|
| 1. How much is a bench player worth? | [posts/01-bench-player-value.md](posts/01-bench-player-value.md) | JEG-544 | Revised for public audience 2026-10-23; blocked on starter-downside breakout (JEG-550) and mid-season improvement model |
| 2. How many backups should a fantasy roster hold? | [posts/02-how-many-backups.md](posts/02-how-many-backups.md) | JEG-557 | Draft; scripts pending JEG-566 |
| 3. Why DDF Value is the core | [posts/03-why-ddf-value.md](posts/03-why-ddf-value.md) | JEG-545 | Draft |
| 4. How we rescale trade charts | [posts/04-how-we-rescale-trade-charts.md](posts/04-how-we-rescale-trade-charts.md) | JEG-545 | Draft. Refreshed 2026-10-29 to the rules on main (week 8 data); script `tools/research/posts04_06_readout.py`, figures in `data/posts04_06/`, stale-claim checklist in [posts04-06-refresh-2026-10-29.md](posts04-06-refresh-2026-10-29.md). Terminology waits on JEG-1212 before publication; fill-in sentence waits on JEG-1201. |
| 5. Missing is not zero, and the one-source rule | [posts/05-missing-zero-one-source.md](posts/05-missing-zero-one-source.md) | JEG-545 | Draft. Refreshed 2026-10-29 to the rules on main (week 8 data); script `tools/research/posts04_06_readout.py`, figures in `data/posts04_06/`, stale-claim checklist in [posts04-06-refresh-2026-10-29.md](posts04-06-refresh-2026-10-29.md). Terminology waits on JEG-1212 before publication; fill-in sentence waits on JEG-1201. |
| 6. Trade confidence | [posts/06-trade-confidence.md](posts/06-trade-confidence.md) | JEG-545 | Draft. Refreshed 2026-10-29 to the rules on main (week 8 data); script `tools/research/posts04_06_readout.py`, figures in `data/posts04_06/`, stale-claim checklist in [posts04-06-refresh-2026-10-29.md](posts04-06-refresh-2026-10-29.md). Terminology waits on JEG-1212 before publication. Describes the Compare deal read; the propose/accept headline was removed from the page 2026-10-26 (#947). |
| 7. Does the market gap predict anything? | [posts/07-does-the-gap-predict.md](posts/07-does-the-gap-predict.md) | JEG-882 | Draft; weeks 2-7 only, re-run at season end. Script `tools/research/gap_backtest.py`, figures in [data/gap_backtest.md](data/gap_backtest.md) (2026-10-22, reference engine, DDF Value blend and projections-only) |
| 8. When do the trade charts agree? | [posts/08-when-charts-agree.md](posts/08-when-charts-agree.md) | JEG-883 | Draft (merged #826); script `tools/research/chart_agreement.py`, outputs `data/post8/` (2026-10-22, engine cc576e71). Computed on the old DDF Value blend that included trade charts; #814 (projections only) has since merged, so figures that use the blend are stale until re-run (the post also shows a projections-only column; not re-checked here). |
| 9. How we split value across positions | [posts/09-how-position-weights-work.md](posts/09-how-position-weights-work.md) | JEG-925 | Draft; numbers recomputed 2026-10-29 on main 7f212319 (week 8 fixture, all seven sources, JEG-1121 bench rule, promotion model off) by `tools/research_post9_numbers.py`, Python reference engine. Replaces PR #837. |
| 10. How DDF Value should be built | [posts/10-how-ddf-value-should-be-built.md](posts/10-how-ddf-value-should-be-built.md) | JEG-943 | Draft (merged #847); script `tools/research/source_accuracy_backtest.py`, figures in [data/source_accuracy_backtest.md](data/source_accuracy_backtest.md) (2026-10-23, Python reference engine). Internal plan: [ddf-predictive-plan.md](ddf-predictive-plan.md). |

In-page links to research use the Writing routes (`#writing/research`, `#writing/manifesto`, `#writing/how-values`); the old `#research` style routes only redirect (JEG-905, #830). The red-test sweep that found a link-route break outside the gate is JEG-916 (`docs/claude-log/red-render-triage/log.md`).

Rules: do not freeze a number that is known to be wrong; mark figures computed on an older engine as stale with the date; name the script or say "none yet". Bench scripts go to `tools/bench_research` (JEG-566); other research scripts to `tools/research/`, each writing its figures to `docs/research/data/` (JEG-882).

## Checklist: public-facing research posts

Before a post goes live, every item must pass. Run through this list on each
revision.

- [ ] **No internal references.** No ticket IDs, script paths, branch names,
  file links, internal dates, or "draft for review" markers. Readers see a
  published article, not a working document.
- [ ] **Define every term.** If a reader would ask "what does that mean?",
  define it inline the first time it appears. Backup, starter, waiver line,
  value above replacement, fill-in value -- all need plain-English definitions.
- [ ] **Explain every constant.** Any number that is not obviously derived from
  the data (a scale factor, a threshold, a default) must say where it comes
  from and whether changing it would affect the results.
- [ ] **State the practical implication of each finding.** After every result,
  say what it means for the reader's roster decisions. "The number is X" is not
  enough; "the number is X, which means Y for your team" is.
- [ ] **Neutral, reader-facing headings.** Section titles should make sense to
  a fantasy manager reading a published article, not to the development team.
- [ ] **Source data described in plain English.** Say "NFL game logs from 2015
  to 2025 (nflverse)" rather than linking to repo files or scripts.
- [ ] **Variance and stability stated for load-bearing assumptions.** If the
  model depends on a number (missed-game rates, bye rates), show how stable it
  is across seasons or settings, and whether recent data differs from the
  historical average.
- [ ] **Limitations are honest and correctly framed.** Each limitation says
  what the model does not do and why it matters. Do not frame a feature as a
  limitation (e.g., "uses projections" when projections are the right input).
- [ ] **No stale numbers.** Every figure in the post traces to a current engine
  run or data source. If a number was computed on an older version, mark it
  stale with the date or recompute it.
