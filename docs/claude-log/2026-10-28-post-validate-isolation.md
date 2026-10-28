## 2026-10-28 — JEG-1203 post-validation source isolation

### Contract

`pipelines/isolate_post_validate.py isolate --log output/post-rebuild-validate.log --week N`
accepts a failed `make validate` only when every unittest failure has a terminal
assertion naming the same changed, successfully rebuilt source. It restores
that source's published section and `source_validation` entry, marks the kept
section held, and retires a matching promotion record. Projection legs are
restored from HEAD. It declines ambiguous or unstructured failures, an
unchanged/already held source, ESPN (the shared reindex anchor), and a
projection rollback when `players.json` changed. It also declines a missing
published section/leg, unverifiable promotion record, or a rollback that would
hold every review-gated chart.

The resulting status is `validation_retry_pending` with `success: false`. A
caller must run the complete `make validate` once more. On success it calls
`pipelines/isolate_post_validate.py confirm`, which marks
`published_with_holds`. On failure it records the failed validation and exits
without publishing. A corrected source build releases only its prior
`chain hold: post-validate source failure`; unrelated holds stay in place.

The 2026-10-28 independent review found two fail-closed gaps. The revised
attribution requires the unittest `FAILED (...)` count to equal all `FAIL:` and
`ERROR:` blocks, including subtests, and rejects unknown summary fields or
unexpected successes. The revised isolation writes `isolation_in_progress`
with `success: false` before changing any source data, rolls back on a later
failure, and advances to `retry_pending` only after every mutation succeeds.
`confirm` independently checks the held section, source validation metadata,
DDF legs, and retired chart promotion record. A lost status write
acknowledgement followed by an incomplete rollback cannot turn the chain
green. No workflow change is included.

This PR owns the pipeline script, release hook, Makefile test registration and
focused regressions. The rebuild workflow is owned by the release/publishing
lane, so **the recovery is not active until that lane wires the two commands
and the single retry**. The original red-validate publication block remains.

### Verified (check named)

- `python3 -m unittest tests.test_isolate_post_validate tests.test_validate_shards tests.test_record_post_rebuild_validation tests.test_rebuild_chain_workflow`: 45 passed. Cases cover a named bad source, unknown or multiple culprits, unchanged source, ESPN anchor, promotion rollback, failed retry, retry confirmation and corrected-save release.
- `python3 -m unittest tests.test_rebuild_chain_per_source_hold`: existing chain isolation regressions passed.
- `git diff --check`: passed.
- The one local `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium make validate` run passed the #1051 seeded hold matrix and the new isolator module, then stopped at `tests.test_player_aliases`: the new source-label table was named `ALIASES`, which that guard reserves for player identity. Renamed it to `SOURCE_NAMES`. The failing module, `tests.test_razzball_refresh` (which found and prompted a missing-fixture fix), and related isolation/workflow checks then passed together: 71 tests. The full gate was not repeated locally.
- `python3 -m unittest tests.test_isolate_post_validate tests.test_player_aliases tests.test_razzball_refresh tests.test_validate_shards`: 54 passed after correcting promotion-record matching for the shared reindex stage, which changes section hashes while retaining `promoted_at`. This also checks that a projection with a changed shared `players.json` cannot be isolated unsafely.
- Repair check: `python3 -m unittest tests.test_isolate_post_validate tests.test_record_post_rebuild_validation tests.test_rebuild_chain_per_source_hold tests.test_razzball_refresh tests.test_validate_shards`: 77 passed. The isolator tests include mixed/unknown subtests, mismatched failure counts, unexpected successes, falsey malformed validation metadata, existing or dangling-symlink rollback-record protection, and injected failure at pending-status, fixture write/readback, DDF leg restore, promotion rename, final-status, and rollback boundaries.

### Claimed, not confirmed

- The #1051 held-source matrix is merged into this branch at `30a87ccf` and
  was previously tested on its own PR. It has not been re-run as a full
  browser matrix on this branch.
- Workflow integration, final-head remote CI and a live publication check are
  pending. No site publication or Supabase change was made here.
