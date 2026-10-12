# Runbooks

One page per recurring job. Each states the exact commands and the expected output. Owner ticket: JEG-601 (2026-10-12).

Run every Python command with the Python 3.12 virtualenv first on PATH (`export PATH=$HOME/code/fantasy-tools/.venv/bin:$PATH`). Python 3.9 fails an unrelated timestamp test.

| Runbook | Job |
|---|---|
| [weekly-refresh.md](weekly-refresh.md) | Confirm the week's producers ran and the chain published. |
| [source-held.md](source-held.md) | A source shows held (amber or red). Find why and how it releases. |
| [run-the-chain.md](run-the-chain.md) | Dispatch or reproduce the rebuild chain. |
| [sweep-and-rank-guard.md](sweep-and-rank-guard.md) | The 12-combo engine sweep, the rank guard and the value check. |
| [verify-live.md](verify-live.md) | Prove the live site is the build you shipped. |
| [heavy-suites-and-hot-files.md](heavy-suites-and-hot-files.md) | Which machine runs heavy suites, and the hot-file merge rule. |
| [weekly-dashboard-freshness.md](weekly-dashboard-freshness.md) | Weekly Signals dashboard staleness rules (paused lane, JEG-396). |
| [consolidated-values-loader.md](consolidated-values-loader.md) | Loading `public.consolidated_values` (JEG-324). |

## Status of "followed once by a session that did not write it"

JEG-601 asks that each runbook be followed once by a different session. The author ran the commands in the first five pages on 2026-10-12 in a fresh worktree against the committed fixture and the live site; the outputs quoted are real. A second session still has to follow them cold. Record it in `docs/claude-log/` and move the date here.

| Runbook | Author ran | Second-session check |
|---|---|---|
| weekly-refresh | read-only commands (`nfl_week.py`, `gh run list`, status file) | pending |
| source-held | read-only commands (status files) | pending |
| run-the-chain | `gh run list`, local `make sync`; `make validate` not re-run for this page | pending |
| sweep-and-rank-guard | all three commands | pending |
| verify-live | all commands (found JEG-629) | pending |
| heavy-suites-and-hot-files | policy page, no commands | pending |

## Retired pages

`docs/watchdog.md` is now the producer and schedule table (the Muse-era watchdog it once described is retired); `docs/guard-harness.md` documents a live gate (`make guard-harness`, part of `make validate`). Neither is deleted: their jobs are not retired.
