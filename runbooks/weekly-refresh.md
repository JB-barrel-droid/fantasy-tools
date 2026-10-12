# Weekly refresh

The site is static. Scheduled jobs bake JSON into the repo and GitHub Pages serves it. Supabase pg_cron dispatches the producer workflows (producer table: `docs/watchdog.md`; cron list: `docs/architecture-current.md`). Nothing needs a hand dispatch in a normal week. This page is the check that it happened.

## 1. What week is it

```
python3 pipelines/nfl_week.py
```

Prints the content week the pipeline builds for: an integer (2026-10-12 printed `5`). The calendar lives in `pipelines/nfl_week.py`; bump `SEASON`, `CONTENT_WEEK_1_START` and `GAME_WEEK_1_START` there each August.

## 2. Did every source land

```
make import-health NFL_WEEK=<week>
```

Verifies the seven import sources against Supabase (needs Supabase credentials; in CI the chain runs it). Expected: every source `ok` for the week. A `stale` source means its producer has not written this week; go to step 4.

## 3. Did the chain publish

```
gh run list --workflow=rebuild-chain.yml --limit 5
python3 -c "import json;d=json.load(open('dist/modules/comparison-chain-status.json'));print(d['run_at'],d['nfl_week'],d['success'],d['outcome'],d.get('held'))"
```

Expected: the newest run is `completed success` and under about 6 hours old (pg_cron `rebuild-chain-live` runs at :17 every 6 hours). In the status file `success` is `True` and `outcome` is `published` or `published_with_holds`. On 2026-10-12 the committed status was `True`, `published_with_holds`, with FantasyCalc, CBS rest of season and Razzball held; see [source-held.md](source-held.md).

## 4. A producer missed

Re-dispatch only the missed producer (production writes):

```
gh workflow run espn-supabase-sync.yml
gh workflow run razzball-supabase-sync.yml -f mode=write
gh workflow run cbsros-supabase-sync.yml
gh workflow run trade-chart-ingest.yml -f mode=write -f source=usatoday
gh workflow run fantasycalc-weekly-save.yml -f mode=write
```

A dry run is the same dispatch without the write input (or a push to a `*/dry-*` branch). Then repeat step 2 and dispatch the chain ([run-the-chain.md](run-the-chain.md)).

## 5. Verify live

[verify-live.md](verify-live.md).

## Known noise

- USA Today answers GitHub runners with 402. The Supabase relay is the primary fallback (`docs/watchdog.md`, "USA Today fetch chain"). `SOURCE_BLOCKED` is a warning and the last good week stays published.
- CBS rest of season publishes Wednesdays; a retry runs at 17:00 UTC if there is no row that day.
