# Weekly Signals — dashboard + pipeline

The **Weekly Signals Dashboard** is the public-facing dashboard of the
football-signal project: a weekly "Vegas vs ECR" disagreement signal page for
NFL fantasy football, rebuilt every morning during the season.

This tree holds the dashboard page **and the code that builds it**, so any AI
tool can read, modify, and extend the whole project from this repo alone.

```
weekly_vegas/
  README.md            <- you are here
  dashboard/
    index.html         <- the current Weekly Signals Dashboard page (self-contained)
  pipeline/            <- the build pipeline that produces the dashboard's data
    bin/               <- runbooks: game_day.py (ECR gate), weekly_chain.py, calibrations
    collectors/        <- data pulls: propline.py, odds_api.py, fds_weekly.py, season_totals.py
    engine/            <- core math: vegas.py, fds_fallback.py, propline_primary.py,
                          snapshot_v4.py, disagreement.py, scoring.py, canonical_players.py, ...
    v4/                <- weekly signal snapshots: compute_v4.py, build_widget.py
    loaders/           <- ESPN / Sleeper / FantasyPros / news loaders
    sql/               <- DDL for the projection/signal snapshot tables
    docs/              <- methodology, workbench spec, accounts notes
    research/          <- research notes behind pipeline decisions
    demo/              <- widget demo page
  cron/
    daily-refresh.md   <- the daily refresh runbook (what the scheduler runs every morning)
```

## What this dashboard is

- **Public name:** "Weekly Signals Dashboard". Public URL is published separately;
  `dashboard/index.html` is an exported, self-contained copy of the current page
  with the week's data baked in.
- **The disagreement is the unit of interest:** Vegas-implied fantasy points vs
  expert consensus (ECR), per player, per scoring (Standard / Half PPR / Full PPR).
- **Copy rules (hard):** the market side is always called **"Vegas"**, never "the
  market". Say **"ECR"**, never the underlying provider brand. FDS (First Down
  Studio) stats are fantasy-only coverage and are never presented as Vegas.

## How it refreshes (daily ~09:07 CT, in-season)

The runbook lives in `cron/daily-refresh.md`. In short:

1. Roll to the current NFL week; refresh PropLine (primary raw-book leg, free tier).
2. Translate raw book prices to fantasy points with our own math (`engine/vegas.py`);
   FDS fills only players PropLine missed (Sunday-only, vegas-attributed stats only);
   Odds API is the selective audit leg (quota guarded, never below 66 remaining credits).
3. Enforce the two-layer ECR gate (pull time AND expert-content vintage <= 3 days),
   fail-closed. Stale experts block the Vegas-vs-ECR comparisons.
4. Rebuild weekly signal v4 snapshots + signals for all three scorings.
5. Positive-EV play gate: a "play" needs a fresh (<=24h), two-sided quoted book
   line+price where the distribution-modeled cover probability beats breakeven by
   >=5pp. Everything else is a "fantasy" read. Missing/stale/one-sided/
   translated-only/post-kickoff inputs fail closed.
6. Fast-tier tests + weekly QA bundle; any failure = no bake.
7. Re-bake the dashboard and verify the rendered page shows the new data.

**Hard rules:** never bake or publish on a known flaw; never zero-fill Vegas;
free sources first, paid quota only for audit/verification; the plays section
honestly says when there are no verified plays.

## For an AI tool picking this up

- Start at `pipeline/docs/methodology.md` for how the numbers work, and
  `cron/daily-refresh.md` for the operational loop.
- Identity is the canonical player key (`engine/canonical_players.py`): one
  players table, one numeric key, one resolver. Ambiguous/unmatched stays NULL,
  never guessed.
- **What's NOT in this tree (regenerated at runtime):** `data/` snapshots and
  caches (~80MB+), the Supabase database (production; tables per `pipeline/sql/`),
  API keys, and the Hatch scheduler definition that runs the daily job.
- Several `bin/` scripts still carry absolute workspace paths from the live
  environment (Supabase skill helpers, goal-workspace lottery paths). `BASE`
  paths have been made repo-relative; the environment-specific ones are marked
  and must be adapted to your own checkout.
- Migration note: `pipeline/loaders/espn.py` had a docstring indentation bug that
  made it unimportable; fixed during migration (function docs merged back into
  the module docstring). Everything else is a faithful copy of the operational
  source as of 2026-09-22.
