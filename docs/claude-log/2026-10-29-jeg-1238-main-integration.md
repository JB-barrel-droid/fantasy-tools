## 2026-10-29 - JEG-1238 main integration

Contract: prepare Claude's reviewed [PR #1103](https://github.com/JB-barrel-droid/fantasy-tools/pull/1103) on a separate Codex integration branch, preserving its source and normal history. Release ownership stays with the coordinator.

### Verified (check named)

- Rechecked GitHub source head `da354145934faea4631ee3905dd9121909a27932` and all Linear comments before edits. The ticket description explicitly assigned this integration phase to Codex; no competing author claim was present.
- New branch `codex/JEG-1238-release-prep-20261029` starts at that exact source. Normal merge `45f452371942e6e5f44a01c937ba1ba48dc414cc` integrates main `430791c41ca9578d878c14c3a37d37a0f3fe0670`, with no conflicts or resolution edits.
- `git diff --exit-code <source> HEAD -- tests/test_player_identity_guard.py pipelines/lib/projection_capture.py pipelines/save_cbsros_references.py` passes. Guard blob `66ab57b142774ab461d7719d06a23c6ea9a06562` is identical to the independently reviewed source.
- `git diff --exit-code <main> HEAD -- app pipelines data dist Makefile` passes. Current-main generated output and both separately audited accidental pushes are retained unchanged. The separately owned #1117 revert is not included.
- Focused offline integration command below: **7 tests PASS, no skips**, exit 0. It checks current-pipeline canonical enforcement, pinned production injection, real-file bypass mutations, CBS rows and saver wiring, and capture-only isolation. All database/HTTP behavior is stubbed; no source refresh or production write ran.

```sh
python3 -m unittest -v \
  tests.test_player_identity_guard.TestPlayerIdentityGuard.test_player_resolution_uses_canonical_players \
  tests.test_player_identity_guard.TestPlayerIdentityGuard.test_production_injected_resolver_is_canonical \
  tests.test_player_identity_guard.TestPlayerIdentityGuard.test_real_capture_wiring_mutations_fail \
  tests.test_projection_captures.SourceBuilderTests.test_cbs_ros_and_offered_weeks \
  tests.test_projection_captures.SaverHookTests \
  tests.test_projection_captures.SundayCaptureOnlyTests.test_capture_only_never_calls_the_published_table_writers
```

- Prior independent review evidence is reused for unchanged source: canonical positive control, eight unsafe probes rejected and 10 focused tests passed, recorded on JEG-1238 at 14:27 UTC. Those are historical source-head results, not fresh broad-suite claims.

### Claimed, not confirmed

- Fresh required preview validation and v2-render CI must pass at the final integration head before release. Local broad suites were not repeated merely to duplicate unchanged source review.
- The coordinator must choose a final merge candidate, recheck main health, perform any applicable delta review and approval checks, and serialize publication/live verification. This preparation does not authorize merging, deletion, production refresh recovery or Supabase actions.
- Automatic cleanup approval for original #1103 does not transfer to the new branch or integration PR.
- Automatic review rejected the attempted Linear claim comment as unauthorized external coordination. The comment was not posted and was not retried; the coordinator was informed.
