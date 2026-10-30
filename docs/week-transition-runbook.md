# Week transition runbook (week N to N+1)

What a normal week flip looks like from Tuesday to Thursday, what "lagging"
and "stale" mean, and when a person steps in. Sources publish week N+1 at
different times; each one is judged by the week it serves, never by one
global week (JEG-1176).

Status: Maintained. Owner JEG-1180. Last verified 2026-10-28 against
`pipelines/week_state.py` and `tests/test_week_stale.py`.

## The rule

- **Calendar.** The content week flips at 00:00 New York time on Tuesday
  (`pipelines/nfl_week.py`, `today_ny()`, one injectable clock).
- **Each source has its own served week** (`source_weeks` in
  `output/comparison-chain-status.json`, from JEG-1177).
- **current**: the source serves this content week (or later).
- **lagging**: the source still serves an earlier week, and it is before
  Thursday 12:00 CT of the week after the one it serves. Normal.
- **stale**: the source still serves week N at or after Thursday 12:00 CT of
  week N+1 (Jeremy, 2026-10-27, JEG-1176). A source two weeks behind is
  always stale.
- **unknown**: nothing dates the source's content.

Stale is a **warning**. It never fails the chain, never changes a hold, never
changes which sources a week's view uses, and never changes an exit code.
The site default week still follows the coverage rule (more than half of a
setting's sources on N+1 shows N+1), with no carry-forward.

The rule lives in one function, `week_state.source_week_status`, pinned by
`tests/fixtures/week_stale_vectors.json`.

## What normal looks like

| When (Central time) | Normal state |
|---|---|
| Monday night | Still week N everywhere. The flip is 23:00 CT Monday (00:00 Eastern Tuesday). |
| Tuesday | Content week N+1 opens. Most sources are **lagging**. FantasyCalc saves Tuesday 13:07 UTC; USA Today has posted on Tuesday in most observed weeks (once Wednesday); the trade-chart ingest (CBS, USA Today, FantasyPros) runs daily at 12:07 UTC; ESPN and Razzball move with their next daily pull (`docs/watchdog.md`, `pipelines/lib/publication_windows.py`). The site defaults to week N until more than half of a setting's sources serve N+1. |
| Wednesday | More sources on N+1. CBS ROS runs Wednesday 11:00 UTC. A source still on N is **lagging**; nothing to do. |
| Thursday before 12:00 CT | Last stretch of normal lag. The ingest's discovery guard (`DISCOVERY_OVERDUE`) can already fire from Thursday for a trade chart it cannot find; that is a discovery alarm, separate from this flag. |
| Thursday 12:00 CT on | Any source still on N is **stale**. Everything else is **current**. |

## Where it shows

- **Chain status** (`output/comparison-chain-status.json`,
  `dist/modules/comparison-chain-status.json`): each `source_weeks.<source>`
  carries `state`, `expected_week`, `weeks_behind`, `stale_after`; the top
  level lists `stale_sources` and `lagging_sources`. The run summary prints a
  `::warning title=Source stale (<source>)` annotation.
- **Reference freshness** (`output/reference-freshness.json`, built by
  `make sync`): each `comparison.source.<source>` row has `status` and
  `week_state` (current / lagging / stale / unknown) from the source's served
  week; the summary lists `comparison_sources_lagging` and
  `comparison_sources_stale`. Rows are never enforced.
- **`scripts/check_weekly_freshness.py`**: after the Weekly Signals checks it
  prints each chart source's served week and state; stale is a warning
  annotation and the exit code is unchanged.
- **Watchdog ingests** (`ops/watchdog/ingest_common.py`): a quiet "not
  published yet" result carries the source's `week_state` and `stale_after`;
  stale prints a warning.

Check the chain's view:

```
python3 -c "import json;d=json.load(open('dist/modules/comparison-chain-status.json'));print(d['outcome'],'stale',d.get('stale_sources'),'lagging',d.get('lagging_sources'))"
```

Replay a moment (the checks above read the same clock, `nfl_week`; `DDF_NOW` sets it):

```
DDF_NOW=2026-10-29T17:01:00Z python3 pipelines/check_reference_freshness.py --output /tmp/reference-freshness.json
```

## When a person steps in

1. **Tuesday and Wednesday: lagging needs nothing.** Do not re-dispatch
   producers or touch holds because a source is still on N.
2. **A source is stale (Thursday 12:00 CT on).** Find out why, in this order:
   - Did its producer run? `docs/watchdog.md` names the workflow and its
     monitored check; read the newest run's annotations.
   - Did the publisher post week N+1? If yes and our ingest missed it, that is
     a discovery bug: re-run the ingest with `--url`, then fix discovery
     (the `DISCOVERY_OVERDUE` message says the same).
   - Is the source held? Then `runbooks/source-held.md` applies; a hold is a
     separate decision and stale does not change it.
   - The publisher simply has not posted: nothing to fix. Leave it stale; the
     site keeps labelling it, and it rejoins when it publishes.
3. **Still stale a full week later (two weeks behind)**: open a ticket for the
   source and add or update its row in `docs/risk-register.md`.
4. **Never** make stale fail the chain, add a hold, or carry week N values into
   the week N+1 view to "fix" it (no carry-forward, Jeremy 2026-10-27).

Related: `runbooks/weekly-refresh.md` (the weekly check),
`runbooks/source-held.md` (holds), `docs/watchdog.md` (producers).
