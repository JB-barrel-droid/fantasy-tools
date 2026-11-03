## 2026-11-03 - JEG-1217 / JEG-1255 main integration after PR #1255

Contract: integrate current functional main once after PR #1255, preserve manager features and all existing work, run focused changed-delta checks, push the existing ticket branch and follow its exact-head CI. Parent retains merge and serial release ownership.

### Verified (check named)

- Main pin `832a18d90704ffa547ad5aae22e179e28843f3f1` includes PR #1255 merge `4c60f8fd0e631f3fb961174f9be8f9f77ab67796` (`git merge-base --is-ancestor`). Previous PR head is `ee0b0710dd2cd8cecc554bd18bdbf4b583d7af8d`.
- Normal `git merge --no-commit --no-ff 832a18d9` completes without conflict. `git write-tree` equals `git merge-tree --write-tree HEAD 832a18d9`: `e821579e375cf7a2f6d050eb34569af57db352d9`. This log is the only manual addition.
- Main adds baseline-red attribution tooling, CI workflow wiring, registry/docs and operational status changes. The wrapper attributes failures and preserves failed-gate exit status; it does not waive failures. No registry, wrapper, source test, workflow or feature was manually changed in this integration.
- `git diff --cached --quiet HEAD -- app/v2 app/trade-value-chart/assets pipelines/build_v2_page.py tests/test_launch_front_door.py`: manager/league/pricing feature code and shared canonical fix are unchanged.
- `python3 -m pipelines.baseline_reds --context local -- python3 -m unittest tests.test_baseline_reds tests.test_validate_shards tests.test_draft_ci_workflows tests.test_ci_speedup_workflows tests.test_render_sweep_shards`: 60 tests pass, no skips, exit 0. Includes known/new failure exit preservation, local versus CI context, malformed registries, signatures/expiry, streaks, and CI/shard registration guards. Log: `/tmp/pr1084-post1255-focused.log`.
- `git diff --cached --check`: passes. Existing generated outputs remain in their earlier isolated checkouts; no broad suite was restarted.
- Historical exact-head CI on `ee0b0710` is fully green (Preview, all five shards, render tests/v2, settings, security, waivers). Original full local validation on `2683f7e5` exited 0. These are not claimed as new-head clearance.

### Claimed, not confirmed

- The pushed integration still requires its own exact-head green CI and independent high-risk delta review before parent-owned merge/release.
- Subsequent operational-status-JSON-only main drift uses Jeremy's option-A batch exception. Functional/test/configuration/pricing changes still require integration and fresh checks.
- No merge to main, deployment, cancellation, deletion, force push, rebase, access change, duplicate broad suite, or denied-comment retry.
