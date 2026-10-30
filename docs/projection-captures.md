# Forward-projection captures (JEG-944, parent JEG-943)

Decided by Jeremy 2026-10-23: "start storing CBS ROS and Razzball week-ahead projections now (every week, append-only, with the capture timestamp and source week)". Widened the same day: "We should be saving projections for all weeks ahead, not just one week ahead."

Purpose: score each source against actuals later (JEG-945). Nothing in this change feeds a value, the DDF Value definition or a published page. Table: `public.source_projection_captures` (migration `supabase/migrations/jeg944_source_projection_captures_20261023.sql`).

Cadence and formats, decided by Jeremy 2026-10-23: "a full copy per source after the Tuesday flip AND a Sunday pre-kickoff copy" (about 160 MB for the season); keep all three scoring formats.

## What each source offers (checked 2026-10-23, week 7)

| Source | Per-week future projections | ROS total | What is stored |
|---|---|---|---|
| ESPN | Yes: a projection block for every unplayed week 1-18 (the puller already reads them; ROS in the chart is their sum) | None given; it is our sum | `horizon=week`, one row per player x unplayed week x 3 formats, points. No `ros` rows. |
| CBS | Current week and next week only. A later week's URL answers 200 with the current week's page titled "Week <current>" (weeks 9, 12 and 18 all returned the Week 7 page), so a page counts only if its title names the week asked for | Yes: totals, games, per game (nonppr; half and PPR add receptions) | `horizon=ros` (points, ppg, games) and `horizon=week` for each offered week (points) |
| Razzball | No. No per-week or week-ahead projection page exists at the URLs tried (`projections-{pos}-week`, `-weekly`, `-week-N`, `-next-week` all 404; the weekly-rankings and next-week links redirect to the 404 page). Only the four `projections-{pos}-restofseason` pages | Per-game columns and games; no total | `horizon=ros` (ppg, games) only |

Razzball week-ahead cannot be stored because it is not published in a scrapeable form; this is a finding, not a gap in the writer. ESPN's far-future weeks are as ESPN publishes them (rolling, so far weeks move week to week; that is the thing being recorded).

## Table rules

- Key: (source, season, source_week, capture_phase, horizon, target_week, player_key, scoring_format). `capture_phase`: `midweek` (the first capture of the content week, from the Tuesday flip), `sunday` (the pre-kickoff copy), `backfill` (week-history rows). `source_week` = the chain's content week at capture (`pipelines/nfl_week.py`, flips Tuesday). `capture_at` = timestamp. `target_week` 0 = ROS.
- One capture per source per content week per phase: the first run of a phase wins, later runs are no-ops (`on conflict do nothing`, plus a skip when the horizon already exists). A trigger rejects UPDATE and DELETE.
- Scoring formats `standard`, `half_ppr`, `full_ppr` (as `projection_snapshots`).
- Phase is the clock: a run on a Sunday (UTC) is `sunday`, any other day `midweek`.
- Writers: `save_espn_weekly.py` (espn-weekly-store.yml, daily 12:40 UTC plus the Sunday 16:20 UTC run: Tuesday's run is the midweek copy, Sunday's the Sunday copy), `save_cbsros_references.py` (+ `pull_cbs_ros_projections.py` writes `weekly_snapshot.json` beside `snapshot.json`), `save_razzball_references.py`. A capture fault in the CBS and Razzball savers prints a `::error` annotation and does not fail the save (they feed published values); the ESPN saver exits 1 after its existing writes.
- Sunday copy for CBS and Razzball: `projection-capture-sunday.yml` (pg_cron `projection-capture-sunday`, Sunday 15:30 UTC, in the migration) pulls both sources and runs `capture_projections_only.py`, which writes only this table: it never upserts `cbs_ros_projections` or `razzball_projections` and dispatches nothing, so it cannot move a published value. (The CBS and Razzball savers on a Sunday run also write the Sunday copy, first one wins.)
- Gate: `pipelines/check_projection_captures.py`, a step in `espn-weekly-store.yml` (a workflow that feeds no published value), exits 1 listing each missing or short capture. Midweek copies are required for content weeks 7 on (due from Wednesday 12:00 UTC of the week); Sunday copies from content week 8. The workflow runs it with `--pre-kickoff` (JEG-1377), so a Sunday copy is due from that Sunday 16:00 UTC and a missing one fails the 16:20 UTC Sunday run, before the noon CT main slate (without the flag it is due the following Monday 12:00 UTC). Row floors in `projection_capture.MIN_ROWS`.
- Sunday timing and retries (JEG-1377): pg_cron runs in GMT, so `projection-capture-sunday` fires at 15:30 UTC every Sunday: 10:30 CDT before the DST change, 9:30 CST from 2026-11-01. The capture step tries three times, 2 then 4 minutes apart (pulls are read-only and the writer keeps the first copy, so a retry never doubles rows). If the run never starts or still fails, the 16:20 UTC Sunday run of `espn-weekly-store.yml` pulls CBS and Razzball and runs the capture-only writer when a capture is missing, then goes red on the `--pre-kickoff` check if a copy is still missing. `workflow_dispatch` with mode `dry` builds both sources' rows, writes nothing and fails under a row floor (`capture_projections_only.py --dry-run`).
- Note (2026-10-30): because the phase is the UTC day, the CBS and Razzball savers' early-Sunday-UTC runs (Saturday evening CT) usually store the Sunday copy first, so the 15:30 UTC capture then reports "already stored". That is the first-one-wins rule as written in JEG-944.

## Backfill and what is lost

`pipelines/backfill_projection_captures.py` (dry run by default; `--write` appends) turns `data/history/week-N.json` into `horizon=ros`, ppg-only rows, `capture_phase=backfill`, with the file's `captured_at`:

| Source | Recoverable (source_week) | Rows planned |
|---|---|---|
| espn | 2, 3, 4, 5, 6, 7 | 1050, 1272, 1275, 1734, 1752, 1764 |
| razzball | 3, 4, 5, 6, 7 | 1533, 2076, 1863, 1860, 1923 |
| cbs (cbsros) | 4, 5, 6, 7 | 1047, 1101, 1089, 1098 |

Caveats: these are the chart build's per-game ROS values, not raw pages (no totals, no games). ESPN weeks 2-4 share `captured_at` 2026-10-08, a rebuild stamp, not the true time of each week's pull.

Lost, not recoverable from the repo: ESPN future-week projections before this change (only played weeks and the next unplayed week were ever stored, in `projection_snapshots`; ESPN weeks 1-7 next-week values are in `data/inputs/espn_weekly_projections_2026.csv`, already stored, not copied here); all CBS per-week projections; Razzball ROS for weeks 1-2 and CBS ROS for weeks 1-3 (no history file); Razzball week-ahead (not published); raw ROS totals and games for any week before 7 (only `data/raw/sources/cbsros/2026-09-30/snapshot.json` has them, one CBS snapshot, week 4 era; not loaded because the week-4 history rows already hold that key). The gate starts at content week 7.

## Size

`projection_snapshots` measured 340 bytes per row including indexes (106,415 rows, 36.3 MB, `docs/selfhost-tables.md`). Estimates (not measured): one ESPN capture is about 500 players x 3 formats x about 9 remaining weeks = 13k rows, so about 11 weekly captures = 150k rows = about 50 MB; CBS and Razzball add about 8k rows a week, about 30 MB for the season. Two copies a week (midweek and Sunday) doubles that: about 160 MB for the season, the size Jeremy accepted 2026-10-23. A daily full ESPN copy would have been about 350 MB.
