# JEG-566: Commit bench research scripts to tools/bench_research

Date: 2026-10-12
Ticket: JEG-566
PR: TBD

## What changed

Committed 8 analysis scripts and a README to `tools/bench_research/`,
adapted from the Linear document "Bench research: analysis scripts
(2026-10-10)". Each script reproduces one or more findings from JEG-557.

Scripts: mix_proto.py (harness), qb_diag.py (QB 22.6% diagnosis),
depth_round_starts.py, insurance_upside.py, waiver_rule.py,
streaming_coverage.py (cautionary circular example),
draft_composition.py, scorecard.py.

## Verified

- scorecard.py runs and produces correct output (ratios match JEG-557).
- draft_composition.py runs and matches documented FFC data.
- qb_diag.py runs against current fixtures; QB bench share reads 13.3%
  (post-Razzball fix, consistent with finding 1).
- 725 tests pass; 1 pre-existing error (missing output/lineup-parameters.json).

## What remains (gated)

Steps 2-3 of JEG-566 (re-run on merged convention + new default roster,
emit chart-ready CSV/JSON) are gated on JEG-562 and JEG-563.

## Also done: JEG-554

Posted rank-based RB and WR lineup share tables to the ticket. Recommended
RB31 (9.70 PPG, 54.3% share) as the worked example at the starter line.
No player names, no specific week. Ticket marked Done.
