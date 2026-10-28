# Runbooks

One page per recurring job. Each states the exact commands and the expected output. Owner ticket: JEG-601 (2026-10-12).

Run every Python command with the Python 3.12 virtualenv first on PATH (`export PATH=$HOME/code/fantasy-tools/.venv/bin:$PATH`). Python 3.9 fails an unrelated timestamp test.

| Runbook | Job |
|---|---|
| [weekly-refresh.md](weekly-refresh.md) | Confirm the week's producers ran and the chain published. |
| [../docs/week-transition-runbook.md](../docs/week-transition-runbook.md) | Week N to N+1: lagging is normal Tuesday to Thursday morning; stale (still on N after Thursday 12:00 CT) is a warning and when to step in (JEG-1180). |
| [source-held.md](source-held.md) | A source shows held (amber or red). Find why and how it releases. |
| [run-the-chain.md](run-the-chain.md) | Dispatch or reproduce the rebuild chain. |
| [sweep-and-rank-guard.md](sweep-and-rank-guard.md) | The 12-combo engine sweep, the rank guard and the value check. |
| [verify-live.md](verify-live.md) | Prove the live site is the build you shipped. |
| [heavy-suites-and-hot-files.md](heavy-suites-and-hot-files.md) | Which machine runs heavy suites, and the hot-file merge rule. |
| [weekly-dashboard-freshness.md](weekly-dashboard-freshness.md) | Weekly Signals dashboard staleness rules (paused lane, JEG-396). |
| [consolidated-values-loader.md](consolidated-values-loader.md) | Loading `public.consolidated_values` (JEG-324). |
| [merging-prs.md](merging-prs.md) | Merge checks: bot report matches head, v2-render green, mergeable, validate step read, generated churn, stacked order, nav tab count; what to do while the preview log is unreadable (JEG-874, 2026-10-22). |

## Status of "followed once by a session that did not write it"

JEG-601 asks that each runbook be followed once by a different session. A second session followed them cold on 2026-10-15 (Python 3.12 venv, fresh worktree on origin/main e71e8262); log: `docs/claude-log/jeg-601-runbook-second-session.md`. Commands needing production credentials (`make import-health`, producer dispatches that write) were not run.

| Runbook | Second-session check 2026-10-15 |
|---|---|
| weekly-refresh | Steps 1 and 3 followed: `nfl_week.py` printed `6`; `gh run list` and the status file read as documented (chain red, outcome `failed`). Steps 2 and 4 need credentials or write production: not run. |
| source-held | Step 1 followed: the three commands ran as written. Found four held or fidelity-held sources (cbs, cbsros, fantasycalc, razzball), value check `agree []`, pulse holds on fantasycalc, cbsros, razzball. Steps 2 and 3 are consistent with what was observed. |
| run-the-chain | `gh run list` matches; `make sync` printed the documented last line. `make validate` not run (red on main for week 6, per the board). |
| sweep-and-rank-guard | All three commands ran as written: rank guard pass (12 checks, 0 inversions), engine sweep `13 True`, value check `agree`, exit 0. Fixed a stale "known red" note. |
| verify-live | `verify_live.py` ran: HTTP 200, tag `tv-20261012-1829-8851351`, `LIVE OK`. The live tag is old because recent deploys failed; the page itself is healthy. |
| heavy-suites-and-hot-files | Policy page, no commands. Read; consistent with `AGENTS.md`. |

## Retired pages

`docs/watchdog.md` is now the producer and schedule table (the Muse-era watchdog it once described is retired); `docs/guard-harness.md` documents a live gate (`make guard-harness`, part of `make validate`). Neither is deleted: their jobs are not retired.
