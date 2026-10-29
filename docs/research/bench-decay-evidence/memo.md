# Bench decay: the evidence we have, and the one decision left (JEG-1276)

Parent: JEG-948 (policy choice held for Jeremy). As of 2026-10-29.
Baseline: `main` at `430791c41ca9578d878c14c3a37d37a0f3fe0670` (2026-10-29).

This memo replays the bench-decay research already committed in post 1
(PR #846), JEG-943 (PR #847) and JEG-528 (PR #604). It adds no new
measurement, changes no value, default or ranking, and picks no method. The
numbers come from `output/evidence_matrix.md`, which a script rebuilds offline
from a fixed manifest.

## How to rerun

```
python3 tools/research/bench-decay-evidence/bench_decay_evidence.py          # rebuild output/
python3 tools/research/bench-decay-evidence/bench_decay_evidence.py --check  # fail if output/ is stale
python3 -m unittest tests.test_bench_decay_evidence
```

`manifest.json` pins every input by sha256 with its source date (PR merge),
capture date (the commit that wrote the data) and content window. The rerun
stops if a hash differs, a date is after the as-of date, content runs past its
capture date, an expected week is absent, or a missing value would print as 0.
A missing sample count prints as "missing"; a model output with no sample
prints as "n/a".

## Two kinds of bench value

Jeremy (2026-10-23): decay includes both option value and fill-in insurance.
The evidence for each is different in kind, so the matrix keeps them apart.

- **Fill-in insurance**: a bench player's points in the weeks a starter is on
  bye or misses a game. The engine prices this today.
- **Option value**: the chance a bench player becomes a starter for good. The
  engine leaves it out of DDF Value on purpose; #604 computes it as a separate
  series that no page reads.

## What is measured, what is historical, what is hypothetical

**Measured on the engine at capture (2026-10-23, 12-team PPR).**

- The per-week bench share already falls with the calendar: 8.7% of the pie at
  content week 1, 8.4% at week 8, 7.6% at week 13, 7.2% at week 17 (F1). It
  falls because future byes run out (bye share 7.8% at week 5, 0 from week 14)
  and projection uncertainty narrows. RB falls from 8.35% to 7.5%; WR from 9.95%
  to 7.6%; TE rises slightly, 1.9% to 2.0%.
- At capture, bench upside from projection uncertainty was 17.7% of the pie and
  starter downside 21.6%; RB is the only position where bench upside is larger
  (11.4% vs 9.7%) (O4). This is one snapshot, not a series by week.
- Rest-of-season projections over 2026 content weeks 2 to 6: all sources sit
  within each other's 95% intervals (MAE 4.36 to 5.05, n 703 to 1,600) (A1).
  The backtest has no split by lead time, so it says nothing about how
  accuracy decays with weeks ahead.

**Historical (2015-2025 game logs).**

- Per-game missed-game rate m: RB 15.3%, TE 14.4%, QB 11.0%, WR 10.5%; in the
  playoff weeks for players healthy at Week 5 (m_late): RB 19.7%, TE 18.6%,
  QB 15.6%, WR 14.0% (F2). The engine already uses m_late when the objective is
  playoffs only.
- Breakout rate measured from week 9: QB 4.2% (30 of 715), RB 3.5% (49 of
  1,403), WR 3.3% (70 of 2,128), TE 2.6% (33 of 1,264); season-to-season ranges
  are wide (RB 1.6% to 6.4%) (O2). First backups break out far more often
  (RB 30 of 132, WR 36 of 132) than third backups (RB 5, WR 8) (O3).
- Breakout rate by the week it is measured from falls through the season: RB
  5.3% from week 4, 3.5% from week 9, 2.1% from week 13, 1.1% from week 16
  (O1). This is the evidence post 1 cites for option-value decay. It has no
  sample counts (G1), and part of the fall comes from how a breakout is defined
  (G3), so it is an upper bound on runway loss, not a measurement of it.

**Hypothetical (arithmetic on the numbers above, not model output).**

- If weeks are independent, an RB starter misses at least one game with
  86% chance over 12 weeks and 39% over 3 (F3). These are JEG-528's figures,
  reproduced.
- Read as a rest-of-season total rather than a per-week share, bench value is
  the share times the weeks left: 1.39 pie-weeks at week 1, 0.76 at week 8,
  0.30 at week 13 (F4). The artifact states this implication; the engine does
  not compute it.
- The #604 timing series scales the bench slice by weeks left over 17. At
  content week 8 (today) that is 9/17 = 0.53, which would take the bench slice
  from 8.4% to about 4.4% of the pie (F4). This is the size of a later value
  change of that shape, shown to make the choice concrete, not proposed.

## Gaps and limitations

The full table is in `output/evidence_matrix.md`. The ones that matter for
the decision:

- **Option value has no measured decay curve.** The by-week breakout series
  has no counts (G1), scores half PPR under a PPR label (G2), defines a
  breakout on full-season points per game (G3), uses 17 weeks for 18-week
  seasons (G4) and counts every non-starter, not rostered bench (G5). The engine's own
  option-value series exists only as one snapshot (G7).
- **No basis yet for a per-week discount.** No week-ahead projections are
  stored by lead time (G6), so JEG-528's "per-week weight with a stated basis"
  cannot be measured yet.
- **The #604 timing series jumps back at the last week.** At content week 17
  the window is empty and the rule leaves the factor at 1, so the series goes
  from 1/17 at week 16 to full at week 17 (G10). It is a separate series, not
  DDF Value; reported to its owner, not changed here.
- **Two published bench shares disagree.** Post 1's sensitivity table gives
  10.0% at PPR/12, the by-week artifact 8.7% (G8). Which matches today's
  engine was not checked; this ticket does not run the engine.
- **Dates.** The engine fixture date behind the model series is not recorded,
  so its content date is bounded by the 2026-10-23 capture (G9). All measured
  engine numbers are from that capture, not today's engine.
- A passing local rerun proves the manifest and arithmetic, not live behaviour.

## The three choices

None is selected here.

| | A. No change | B. Readout only | C. Later value change |
|---|---|---|---|
| What changes | Nothing | A week-aware bench readout (weeks left, byes left, fill-in share, historical breakout odds), each labelled measured or historical | Bench value in DDF Value scales with weeks left (fill-in, option value, or both) |
| DDF Value | Unchanged | Unchanged | Changes; at week 8 a #604-shaped change would cut the bench slice by about half |
| Rests on | F1 (engine already week-aware for fill-in) | F1, F2, O2, O3 as they stand | F1 to F4 plus evidence not yet stored |
| Missing before it is honest | Nothing new; post 1's decay claims stay as published | G1 counts before showing breakout odds by week | G1 to G7 closed, then a before/after on live data, Python reference, value_check 0 and rank guard 0 (AGENTS.md) |
| Fit with the two-level bench model (#1105) | DDF level stays pure VORP | DDF level stays pure VORP; timing sits beside it as information | DDF-level VORP would carry the horizon; how that meets #1105's market level is open (#1105 is blocked by JEG-1249) |
| Work | None | Front-end readout ticket and copy; no engine change | Engine, spec and reference change on hot files, paired JS and Python, 12-combo sweep |

## Question for Jeremy

For JEG-948, which should happen next with bench decay: (A) no change, keep
today's week-aware fill-in share and leave option value out; (B) add a
week-aware bench readout, with DDF Value unchanged; or (C) plan a later DDF
Value change that scales bench value with weeks left, built only after the
evidence gaps above are closed and you approve its before/after?
