## 2026-10-22 - Research post 8: when do the trade charts agree (JEG-883)

Contract: draft `docs/research/posts/08-when-charts-agree.md`, a reproducible
script `tools/research/chart_agreement.py`, outputs in
`docs/research/data/post8/`, a README row, and label/threshold options for
Jeremy on JEG-883. Branch `docs/research-post8-agree` from origin/main
`cc576e71`.

### Verified (check named)
- The Python port of the verdict rules equals the site's JavaScript:
  `chart_agreement.py --verify-port` runs 400 week-7 trades and 200 live-week
  trades (three charts, FantasyCalc held) through `app/v2/trade.js` and
  `app/v2/finder.js` in node and diffs propose answer and level, agree count,
  accept answer and level, deal cell and finder listing: 0 mismatches
  (`docs/research/data/post8/port_check.json`).
- The port check catches a wrong port: with THIN_MARGIN set to 0.10 it
  reported 125 mismatches of 400; with the "as shown" cut set to 0.5, 75 of
  400 (one-off run in the session, not committed as a test).
- Three live trades on https://jb-barrel-droid.github.io/fantasy-tools/v2/
  (deploy cc576e71, 2026-10-22) read through the browser pane matched the
  port: "Yes, High, 3 of 3 / Unlikely, High, 0 of 3 / Win, but a hard sell";
  "No, High, 2 of 3 / Likely, Medium, 2 of 3"; "Unclear, Low, 0 of 3 /
  Likely, Low, 3 of 3". Live week 7 shows "of 3" because FantasyCalc is held.
- Full run: `python3 tools/research/chart_agreement.py` (38 s), 72,000
  trades (12,000 per week, weeks 2 to 7), every table in
  `docs/research/data/post8/summary.md`. Headline numbers: "Yes, High" with
  1 of 4 charts agreeing changes its answer next week 36.2% (95% bootstrap
  34.1 to 38.4) and DDF Value flips sign 21.5%; with 4 of 4, 18.7% and 6.7%.
  "Likely, High" repeats next week 82.5%; "Toss-up" 30.2%.
- `gh pr view 814 --json state`: OPEN at run time, so DDF Value in the study
  is the live blend; a projections-only column is reported alongside.
- Reference rows for history weeks come from `value_reference.run_pipeline`
  on each week's saved natives (all complete sources included, hidden set
  empty); the live week from `value_reference.Setting` with the build's
  holds. Rows match in shape to `Setting.rows('indexed')` (same code path).

### Claimed, not confirmed
- That `value_reference` equals the browser engine for history weeks. The
  repo's `value_check compare` proves it for the current week and the prior
  week only; weeks 2 to 5 rows are the reference's reading of the saved
  natives with no holds applied.
- Bootstrap intervals resample trades that share players, so they are
  narrower than the true uncertainty.
- No `make validate` run locally (CI is the gate for this docs-and-tools PR).
