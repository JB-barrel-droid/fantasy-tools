## 2026-10-29 - Draft PR CI deferral

Contract: Keep cheap PR checks running on drafts, defer runner-heavy Preview and
render jobs until ready for review, and preserve failing required checks until
full verification passes at the current PR head.

### Verified (check named)

- `python3 -m unittest tests.test_draft_ci_workflows tests.test_preview_workflow_matches_pages tests.test_ci_speedup_workflows tests.test_v2_render_runs_on_data_push tests.test_validate_shards tests.test_deploy_gate_unconditional`: 103 passed. The new tests execute finalizer shells for failed, skipped and cancelled dependencies, and exercise draft toggles, stale heads, API errors and push/manual paths.
- `python3 -c 'import yaml; [yaml.safe_load(open(p)) for p in (".github/workflows/preview.yml", ".github/workflows/v2-render-test.yml")]'`: both workflows parse as YAML.
- `git diff --check`: passed. Pages production workflow and its unconditional validation are not changed by this branch.

### Claimed, not confirmed

- GitHub has not yet executed the draft or ready transitions on this branch.
  The PR must show deferred required checks on its draft head; moving it ready
  should run the full jobs, and exact-head successful CI and review are required
  before merge. Branch protection settings were inaccessible through the
  connector (403), so their configuration is not claimed.
- The release-window main-write pause remains off. PR #1125 and its runbook
  still require separate merge, old-run drain, activation and restoration.

### Correction after review (JEG-1292)

- `current_pull()` made one request, so one API blip left an idle ready PR's
  required check red with no further event to clear it. `live_pull()` now wraps
  it: three reads over about 30 seconds (sleeps of 10 and 20 s) for network
  errors, timeouts, HTTP 5xx, 429 and rate-limit 403s. A live draft flag that
  differs from the event (same head, still open) is read again before it is
  called stale. 404, 401 and other 403s are not retried. After the last read it
  still fails closed.
- `python3 -m unittest tests.test_draft_ci_workflows`: the 7 new
  `PrStateRetryTest` cases fail at reviewed head `af167e82` (the one-blip read
  raises `URLError`; a lagging draft flag writes `run_expensive=false`) and pass
  after. The focused suite above now runs 110 tests, all passing.
- Recovery: if a ready PR still shows `preview` or `v2-render` red with "PR
  state verification failed", use Re-run failed jobs, or push, or toggle draft
  and back to ready.
- The HANDOFF.md note was dropped from this PR; this log holds the evidence.

Reversal: revert this branch's workflow, script and test changes in a reviewable
PR; the original Preview and v2-render jobs then run on every matching PR event.
