## 2026-11-03 - Producer integration and identity correction / JEG-1481

Contract: correct the independent review findings against PR #1294 head
`d0cc5098bb3517f8b32a9813cb242214b46b7cd4` on the existing owner, branch and
PR. No producer, source fetching, live route, writer, Supabase, credential,
production data, merge or deploy changes. Source main remains
`ad0cfc3a40ed3cdbb6d3291e4bb1c735d5bd6dfc`.

### Verified (check named)

- Confirmed the actual offline producer emits ECR source `fantasypros_ecr`,
  while the initial adapter accepted only the shared fixture's `fantasypros`.
  The new test `test_producer_cli_output_builds_preview_without_relabeling`
  ran both actual CLIs on committed producer fixtures and failed before the
  fix with preview exit 2: `experts.ecr_weekly must use fantasypros; got fantasypros_ecr`.
  No test stub or manual artifact relabeling is used.
- `test_producer_source_label_also_accepts_populated_weekly_points` failed
  before with the same source error, and `test_player_identity_provenance_is_preserved`
  failed before with `KeyError: 'resolved_by'`. Before-fix receipt is
  `/tmp/jeg1481-review-regression-before.log`.
- The adapter now accepts exactly `fantasypros_ecr` and `fantasypros` on the
  weekly ECR leg, with PropLine still the sole Vegas source. Existing wrong-source
  refusal tests remain unchanged. The producer is untouched.
- The adapter preserves `resolved_by` and `source_ids` with `player_key`;
  the page exposes all three via per-player identity disclosure using
  `textContent`. Missing provenance is displayed explicitly as unavailable.
- `python3 -m unittest tests.test_weekly_inputs_contract tests.test_build_weekly_inputs tests.test_versus_vegas`:
  107 tests passed, including the three new regressions. The end-to-end test
  checks every producer row stays visible, missing stays null with the actual
  producer reason, unresolved rows survive, and identity metadata is retained.
- `node --check app/versus-vegas/view.js` and `git diff --check`: passed.
  Focused CI path filters now include the actual producer and its fixtures,
  so changes to those dependencies exercise the integration regression.

### Claimed, not confirmed

- The browser test now expands a player's identity detail and asserts the
  canonical key, resolver and source IDs are rendered. Exact corrected-head CI
  is pending push; its receipt will be on JEG-1481 and the draft PR.
- Local Chromium remains absent and its download was previously denied by
  the environment proxy. No retry or bypass was attempted. `make validate`
  previously stopped at sync on that absence; full validation remains blocked
  locally. Existing required preview/render checks defer heavy jobs for drafts.
- No independent re-review, live page or runtime source freshness is claimed.
