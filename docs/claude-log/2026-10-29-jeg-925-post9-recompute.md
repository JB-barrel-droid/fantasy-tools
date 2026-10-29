## 2026-10-29 - JEG-925 research post 9: numbers recomputed on the week 8 charts

Contract: the evidence hold on JEG-925 (week 8 charts not published, JEG-1175)
has cleared, so recompute every number in post 9 on the current engine and
describe the position weights as they are today. Docs and research script
only: no weight, default or value-math change. Carries the cma/JEG-925 draft
(6e758a42, session:cma retired 2026-10-27) onto a fresh branch from main and
replaces PR #837.

Done:
- Post 9 text and every table regenerated from `tools/research_post9_numbers.py`
  on main 7f212319, week 8 fixture built 2026-10-29 21:10 UTC: the 8-group
  weights, budgets, ESPN group totals and worked example, the seven sources'
  starter mixes, league size, scoring, superflex, bench and two-TE tables,
  leave-one-out and the 5-point sensitivity. Prose that rested on the old
  numbers was rewritten (running backs now lead wide receivers 43.0% to 41.7%
  at PPR/12; superflex more than quadruples the quarterback share; the old
  "charts pay quarterbacks more than projections" split no longer holds).
- The status note saying the tables must not be quoted is gone; the promotion
  model is described as switched off (JEG-1142); Razzball's amber hold is
  explained; a limit names the approved, unmerged method work that will move
  the numbers (JEG-1244, JEG-1286).
- `tools/research_post9_numbers.py`: leave-one-out was a no-op (it passed the
  reader's DDF selection, which does not touch the weights, so every row equalled
  the baseline). It now recomputes the weight average with one source dropped
  and refuses if the full-set average does not reproduce the pipeline's weights.
  The promotion-off rerun is replaced by recording the master switch.
- `docs/research/README.md`: the post 9 row points at the file.

### Verified (check named)
- `python3 tools/research_post9_numbers.py` exits 0, "all seven sources";
  `output/comparison-chain-status.json` on main: run 2026-10-29 21:11 UTC,
  success true, nfl_week 8, failed [], Razzball held amber and promoted.
- 24-combination check (3 scorings x 8/10/12/14 teams x no/one superflex):
  all seven sources included, eight weights sum to 1 within 1e-9, budgets equal
  pie x weight within 1e-6, zero failures.
- Leave-one-out with no source dropped reproduces `ddf_weights` exactly (max
  difference 0.0).
- Sensitivity: every running back's blended DDF Value moves by exactly 1.1162 and
  every wide receiver's by 0.88 (min equals max over 46 and 51 players).
- Every percentage, range and ratio in the prose was re-derived from the script's
  JSON (sums, ranges, the 5.29 and 4.35 ESPN rates).

### Claimed, not confirmed
- That the browser engine matches these reference figures (rests on the deploy
  gate's strict compare; no render run here).
- The bench-rule fit errors in Alternatives items 1 to 4 (quoted from the
  2026-10-10 bench research, not recomputed).
- The public-post checklist in `docs/research/README.md` (internal references
  such as ticket IDs and file paths) is not applied; the post stays a draft
  with its evidence notes, as posts 1 to 10 are.

## 2026-10-29 - JEG-1349 correction: leave-one-out as a real drop-out

Contract: the independent review of #1182 (head 1e7fbb69) found the
leave-one-out only re-ran the averaging step, so it missed that a source
dropping out also moves the shared allocation and the chart fill-ins.

Done:
- `tools/research_post9_numbers.py`: `leave_one_out` now reruns `run_pipeline`
  with the source removed from `included` (the Setting's own arguments);
  `leave_one_out_averaging_only` keeps the old measure, labelled. Both must
  reproduce the pipeline's weights with nothing dropped, or the script refuses.
- Post 9 Sensitivity: the stability paragraph is replaced by a leave-one-out
  table with both measures. The conclusion changed: CBS rest of season is the
  biggest mover (RB +2.5, WR -2.1), then ESPN (RB -1.4); FantasyPros and USA
  Today were wrongly named. Traceability says how both are computed.
- Nits: fixture time 21:11 UTC; the bench tier described as about two weeks of
  the league's expected missing starters (11 RB seats at PPR/12).

### Verified (check named)
- Failing before, passing after: a check that the script's cbsros leave-one-out
  RB differs from the averaging-only RB by more than 0.5. On the 1e7fbb69
  script output: 42.9 vs 42.9, exit 1. After: 45.5 vs 42.9, exit 0.
- The full drop-out table matches the reviewer's reproduction on JEG-1349 row
  for row (RB/WR).
- Headline weights unchanged (QB 7.2, RB 43.0, WR 41.7, TE 8.1, bench 6.7).

### Claimed, not confirmed
- How much of the projections' larger effect comes from the allocation versus
  the chart fill-ins (not separated; the post says so).
