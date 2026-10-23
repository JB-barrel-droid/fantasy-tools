# Research

Durable evidence behind the tool's opinionated choices (JEG-604, 2026-10-12). Research posts on the site (JEG-543, JEG-544, JEG-557) link here; every claim in a post should link to a page below and to the script that produced it.

| Page | What it holds |
|---|---|
| [bench-rule-research.md](bench-rule-research.md) | Market bench versus fundamental bench: draft ratios, the five-rule scorecard, bench-spot value, field scan. |
| [roster-convention-audit.md](roster-convention-audit.md) | The JEG-556 audit of inconsistent roster rules, and the convention that replaces them. |
| [qb-bench-share.md](qb-bench-share.md) | The 22.6% QB bench share, why it was an artifact, and what superseded it. |
| [research-post-1-facts.md](research-post-1-facts.md) | JEG-544 decisions and the fact tickets, with status. |

## Post drafts

| Post | File | Ticket | Status |
|---|---|---|---|
| 1. How much is a bench player worth? | [posts/01-bench-player-value.md](posts/01-bench-player-value.md) | JEG-544 | Revised for public audience 2026-10-23; blocked on starter-downside breakout (JEG-550) and mid-season improvement model |
| 2. How many backups should a fantasy roster hold? | [posts/02-how-many-backups.md](posts/02-how-many-backups.md) | JEG-557 | Draft; scripts pending JEG-566 |
| 3. Why DDF Value is the core | [posts/03-why-ddf-value.md](posts/03-why-ddf-value.md) | JEG-545 | Draft |
| 4. How we rescale trade charts | [posts/04-how-we-rescale-trade-charts.md](posts/04-how-we-rescale-trade-charts.md) | JEG-545 | Draft |
| 5. Missing = 0 and the one-source rule | [posts/05-missing-zero-one-source.md](posts/05-missing-zero-one-source.md) | JEG-545 | Draft |
| 6. Trade confidence | [posts/06-trade-confidence.md](posts/06-trade-confidence.md) | JEG-545 | Draft; partially gated on JEG-505 |
| 7. Does the market gap predict anything? | [posts/07-does-the-gap-predict.md](posts/07-does-the-gap-predict.md) | JEG-882 | Draft; weeks 2-7 only, re-run at season end. Script `tools/research/gap_backtest.py`, figures in [data/gap_backtest.md](data/gap_backtest.md) (2026-10-22, reference engine, DDF Value blend and projections-only) |
| 8. When do the trade charts agree? | [posts/08-when-charts-agree.md](posts/08-when-charts-agree.md) | JEG-883 | Draft; script `tools/research/chart_agreement.py`, outputs `data/post8/` (2026-10-22, engine cc576e71, DDF Value blended: PR #814 open) |

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
