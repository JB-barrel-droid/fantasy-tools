# FantasyCalc scoring-variant captures (JEG-1565 provenance check)

Only name, position and the published `value` are kept, to check how FantasyCalc's
Standard and Full PPR numbers relate. Each capture is one request per scoring format
to FantasyCalc's public values endpoint (no credentials), with the URL as recorded:

- live pull, 2026-11-07T18:02:51Z: `https://api.fantasycalc.com/values/current?isDynasty=false&numQbs=1&numTeams=12&ppr=0` and `...&ppr=1` (two requests, 2 s apart).
- week 4 cache, 2026-09-29T15:34:18Z: the same requests, copied from the weekly pull cache
  (`ops/watchdog/pull_fantasycalc.py` output) that predates the repo's raw snapshots.

The repo's own raw week 4 snapshot (`data/raw/sources/fantasycalc/week-4/snapshot.json`,
2026-10-04) and the weekly history (`data/history/week-5..9.json`) are read in place.
Used by `pipelines/research_trade_value_audit.py` (`fantasycalc_scoring_history`).
