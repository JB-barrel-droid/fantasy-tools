# What "late" means for each source (JEG-1200, JEG-1201)

Jeremy, 2026-10-28: "dynamic sources should update daily, and never late for
a week." And: "Projection sources update constantly, so they should never be
delayed. So does fantasycalc. Trade chart articles tend to publish at the
same time every week. We should organize on a source by source basis, make
checks for the data lightweight."

`pipelines/source_lateness.py` checks every source once an hour
(`.github/workflows/source-lateness.yml`, at :50). It reads only what already
exists: the probe state each change check writes
(`public.source_probe_state`) and the week each source serves on the site
(`data/history/index.json`). It never fetches a source, never holds a value
and never fails a job. When any source is late it opens one GitHub issue,
"A data source is late" (label `source-late`), updates it when the set of late
sources changes (otherwise at most every 6 hours) and closes it when every
source is on time again. GitHub emails the repository owner.

## The rule for each source

| Source | Kind | Normal | Late when |
|---|---|---|---|
| FantasyCalc | live | changes all day; probed hourly, saved at most every 6 h | not confirmed current for 9 h; check silent 3 h; site on last week after Wednesday 12:00 CT |
| ESPN, CBS rest of season, Razzball | live | projections change all week; probed every 4 h | not confirmed current for 9 h; check silent 9 h; site on last week after Wednesday 12:00 CT |
| FantasyPros | weekly article | Tuesday 8 to 11 AM CT | week's article not out by Wednesday 12:00 CT (publisher late), or out and the site still on last week (we are late); not confirmed current for 26 h; check silent 13 h |
| USA Today | weekly article | Tuesday 1 to 4 PM CT | as FantasyPros |
| CBS | weekly article | Tuesday 4 to 5 PM CT | as FantasyPros |
| DraftSharks, FantasySharks | fidelity reference, not on the chart | a few times a week; probed twice a day | not confirmed current for 36 h; check silent 26 h |

"Confirmed current" is the last change check when that check read the source
and saw the same content the last good save holds; otherwise it is the last
good save. So a source whose new content never gets saved, or that the check
cannot read, goes late even though nothing else looks wrong.

The weekly times are from the probe log and the articles' own dates, weeks 5
to 8 of 2026. Wednesday noon is a day before the Thursday 12:00 CT stale flag
(JEG-1180, `docs/week-transition-runbook.md`): late is the early alarm, stale
is what the page says. Change a rule in `RULES` in `pipelines/source_lateness.py`
and its test in `tests/test_source_lateness.py`.

## What to do when the issue opens

- **Check silent**: the pg_cron probe job did not dispatch, or the probe
  workflow failed. Look at the Source change probes runs and
  `select jobname, active from cron.job`. Pausing or editing a job is a
  production change: ask Jeremy.
- **Not confirmed current**: the probe or the ingest keeps failing. The probe
  run's warning and `source_probe_state.last_error` say why (a 403 means the
  site turned the scraper away).
- **Publisher late**: nothing is broken on our side. The page keeps showing
  last week's chart, labelled, and the live sources carry the week.
- **Site still on last week**: the rebuild chain is not publishing. See the
  `chain-stuck` issue (JEG-1194) and `runbooks/source-held.md`.

## Why this workflow has its own schedule

Every other job here is scheduled by Supabase pg_cron (AGENTS.md "Supabase
first"). This one is the watchdog for those schedules. On Oct 20 and 21, 2026
the probes logged nothing for two days, a Tuesday included, and nothing
noticed. A check that shares the scheduler it watches goes quiet with it.
