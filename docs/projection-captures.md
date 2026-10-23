# Forward-projection captures (JEG-944, parent JEG-943)

Decided by Jeremy 2026-10-23: "start storing CBS ROS and Razzball week-ahead projections now (every week, append-only, with the capture timestamp and source week)". Widened the same day: "We should be saving projections for all weeks ahead, not just one week ahead."

Purpose: score each source against actuals later (JEG-945). Nothing in this change feeds a value, the DDF Value definition or a published page. Table: `public.source_projection_captures` (migration `supabase/migrations/jeg944_source_projection_captures_20261023.sql`).

## What each source offers (checked 2026-10-23, week 7)

| Source | Per-week future projections | ROS total | What is stored |
|---|---|---|---|
| ESPN | Yes: a projection block for every unplayed week 1-18 (the puller already reads them; ROS in the chart is their sum) | None given; it is our sum | `horizon=week`, one row per player x unplayed week x 3 formats, points. No `ros` rows. |
| CBS | Current week and next week only. A later week's URL answers 200 with the current week's page titled "Week <current>" (weeks 9, 12 and 18 all returned the Week 7 page), so a page counts only if its title names the week asked for | Yes: totals, games, per game (nonppr; half and PPR add receptions) | `horizon=ros` (points, ppg, games) and `horizon=week` for each offered week (points) |
| Razzball | No. No per-week or week-ahead projection page exists at the URLs tried (`projections-{pos}-week`, `-weekly`, `-week-N`, `-next-week` all 404; the weekly-rankings and next-week links redirect to the 404 page). Only the four `projections-{pos}-restofseason` pages | Per-game columns and games; no total | `horizon=ros` (ppg, games) only |

Razzball week-ahead cannot be stored because it is not published in a scrapeable form; this is a finding, not a gap in the writer. ESPN's far-future weeks are as ESPN publishes them (rolling, so far weeks move week to week; that is the thing being recorded).

## Table rules

- Key: (source, season, source_week, horizon, target_week, player_key, scoring_format). `source_week` = the chain's content week at capture (`pipelines/nfl_week.py`, flips Tuesday). `capture_at` = timestamp. `target_week` 0 = ROS.
- One capture per source per content week: the first run of the week wins, later runs are no-ops (`on conflict do nothing`, plus a skip when the horizon already exists). A trigger rejects UPDATE and DELETE.
- Scoring formats `standard`, `half_ppr`, `full_ppr` (as `projection_snapshots`).
- Writers: `save_espn_weekly.py` (espn-weekly-store.yml, daily; the Tuesday run is the first of the content week), `save_cbsros_references.py` (+ `pull_cbs_ros_projections.py` writes `weekly_snapshot.json` beside `snapshot.json`), `save_razzball_references.py`. A capture fault in the CBS and Razzball savers prints a `::error` annotation and does not fail the save (they feed published values); the ESPN saver exits 1 after its existing writes.
- Gate: `pipelines/check_projection_captures.py`, a step in `espn-weekly-store.yml`, exits 1 listing each missing or short capture for content weeks 7 to now (grace Tuesday to Wednesday noon UTC for the current week only). Row floors in `projection_capture.MIN_ROWS`.

## Backfill and what is lost

`pipelines/backfill_projection_captures.py` (dry run by default; `--write` appends) turns `data/history/week-N.json` into `horizon=ros`, ppg-only rows with the file's `captured_at`:

| Source | Recoverable (source_week) | Rows planned |
|---|---|---|
| espn | 2, 3, 4, 5, 6, 7 | 1050, 1272, 1275, 1734, 1752, 1764 |
| razzball | 3, 4, 5, 6, 7 | 1533, 2076, 1863, 1860, 1923 |
| cbs (cbsros) | 4, 5, 6, 7 | 1047, 1101, 1089, 1098 |

Caveats: these are the chart build's per-game ROS values, not raw pages (no totals, no games). ESPN weeks 2-4 share `captured_at` 2026-10-08, a rebuild stamp, not the true time of each week's pull.

Lost, not recoverable from the repo: ESPN future-week projections before this change (only played weeks and the next unplayed week were ever stored, in `projection_snapshots`; ESPN weeks 1-7 next-week values are in `data/inputs/espn_weekly_projections_2026.csv`, already stored, not copied here); all CBS per-week projections; Razzball ROS for weeks 1-2 and CBS ROS for weeks 1-3 (no history file); Razzball week-ahead (not published); raw ROS totals and games for any week before 7 (only `data/raw/sources/cbsros/2026-09-30/snapshot.json` has them, one CBS snapshot, week 4 era; not loaded because the week-4 history rows already hold that key). The gate starts at content week 7.

## Size

`projection_snapshots` measured 340 bytes per row including indexes (106,415 rows, 36.3 MB, `docs/selfhost-tables.md`). Estimates (not measured): one ESPN capture is about 500 players x 3 formats x about 9 remaining weeks = 13k rows, so about 11 weekly captures = 150k rows = about 50 MB; CBS and Razzball add about 8k rows a week, about 30 MB for the season. A daily full ESPN copy would be about 7x the ESPN part (about 350 MB).
