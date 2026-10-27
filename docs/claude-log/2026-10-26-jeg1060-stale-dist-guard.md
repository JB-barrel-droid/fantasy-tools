# JEG-1060: value_check compare refuses a stale dist

Ticket: JEG-1060. Run by an OpenRouter deepseek-v4.1-flash session (T2/T3),
untrusted until a Claude T1 review.

## What changed

`pipelines/value_check.py compare` reads the built `dist/`, which is tracked in
git and lags the source, so in a fresh worktree it diffed the old committed
engine against the current Python reference. Root cause is a stale build
artifact, not value math; no user-visible values were affected (`make validate`
depends on sync, which rebuilds dist first).

- New `stale_engine_files(dist)` + `ENGINE_SYNC_FILES` (value-model.js,
  curve-widget.js, product-data.js, player-tags.js, roster-convention.js,
  fundamental-bench.js, comparison-sources-data.json). Byte-compares each
  synced file in dist against its `app/trade-value-chart/` source.
- `cmd_compare` runs the check before `run_engine` and raises
  `SystemExit("dist is stale (<file> differs from <source>): run make sync first")`.
  New `--sync` flag runs `make sync` first; default stays fail-loud.
- `tests/test_value_check.py::DistFreshness` (4 tests): fresh dist passes;
  changed file, missing file and the CLI non-zero exit are asserted.
- Doc line in `runbooks/sweep-and-rank-guard.md` section 3; risk-register row
  `GAP-VALUE-CHECK-STALE-DIST`.

## Verified (check named)

- `python -m unittest tests.test_value_check.DistFreshness` — 4 tests, OK.
- Mutation (guard forced to always report fresh): the changed-file and
  missing-file tests fail, the fresh one still passes — the guard is negative
  tested.
- `python pipelines/value_check.py compare --rerun-engine --strict` on this
  worktree's stale dist: prints the stale message and exits 1 (no browser run).
- `python -m unittest tests.test_value_check.Attribution` — 11 tests, OK.

## Claimed, not confirmed

- The full `compare --rerun-engine --strict` after `make sync` was NOT re-run
  (slow; ticket says at most once and only if cheap). Prior runs report
  `agree`; the guard only refuses stale builds and does not change the compare.
