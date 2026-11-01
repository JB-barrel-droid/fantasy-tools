## 2026-11-01 - Bot-only catch-up / JEG-1466, PR #1262

Contract: prepare an optional local-Git bot-write exception to the freshness
gate. Both flags remain off until Jeremy approves a standing rule in his 4 PM
Central window. Jeremy, Nov 1: "Queue up the work next that speeds up efficiency
from in progress to merged". Do not edit HANDOFF, promote the draft, or post to Linear.

### Verified (check named)

- Initial `df -k /System/Volumes/Data`: 3,747,716 KiB, above the 2,097,152
  starting floor. Subsequent observed values stayed above the 1,572,864 runtime
  floor. The core runner checked disk while active and would terminate on a dip.
- `gh api rate_limit --jq .resources.core`: remaining **0**. Used local git
  thereafter; no more GitHub/Linear API calls. The requested fetch downloaded
  the branch but reported a shared origin/main update race; local inspection
  confirmed the ref had already reached the fetch's intended `5f7c6295`.
  Did not retry the fetch. Merged the remote branch into this clean worktree,
  fast-forwarding `7a79e5c1` to the supplied `5dac2030` before editing.
- All ten writers' explicit `git config user.name/user.email` commands were
  inspected. The main-writer App uses the same Git author as Actions: the
  config contains the two observed `github-actions[bot]` name/email pairs,
  not an invented App author. Author metadata alone does not prove push identity.
- Inventoried every staged path from the ten main-writer workflows (table
  below). Only exact paths and the two actually staged directory subtrees are
  allowed. Committed flags in `pipelines/pr_freshness_config.json` are both
  `false`, with no environment override.
- Local Git verifies the REST-observed main equals origin/main, one merge
  base, the complete main-side history/count, each author and per-commit path,
  no overlap with the PR diff, and clean `merge-tree --write-tree`. It inspects
  intermediate writes, deletions and both sides of renames. Missing evidence
  fails closed; the gate never fetches, changes the index or merges the branch.
- Existing exact-head checks still run after the optional ancestry exception.
  Success output names `fresh` or `bot-only-behind` and all skipped commit SHAs.
- `python3 -m pytest tests/test_pr_freshness_gate.py tests/test_draft_ci_workflows.py -q`:
  **46 passed**. New real-Git/fake-REST cases cover default-off, status-only
  success, data flag separation, non-bot/unrecognized author, PR overlap,
  actual directory/file merge conflict, red head, unknown path, stale local
  main and intermediate disallowed writes. Test repos remain unchanged by gating.
- AST comparison against `5dac2030` confirmed every pre-existing test/helper
  method in `test_pr_freshness_gate.py` is unchanged; no assertion was edited.
- `make test-core`: **failed**, not a disk stop. First command passed 26 tests;
  the second ran 29 with one error in
  `TestPromotionModelSwitchedOff.test_python_reference_flag_on_equals_baseline`.
  Its `_render_env.ensure_built()` failed launching the missing Playwright
  `chromium_headless_shell-1208`. No install or retry. Preserved the full log at
  `output/jeg1466-bot-only-test-core.log`, restored its 19 tracked generated
  files, and moved new build artifacts into
  `output/jeg1466-bot-only-build-artifacts/` without deleting them.
- `git diff --check` passed. HANDOFF.md is unchanged from the starting remote
  head. The requested runbook heading contains options A/B, not an activation.

### Writer/path classification evidence

| Writer workflow | Config classification of staged output |
| --- | --- |
| espn-supabase-sync | data_inputs: `pipelines/pull_espn_projections.py` (auto-updated source, not a status report) |
| espn-history-probe | status_only: `output/espn-history-probe.json` job summary |
| espn-weekly-store | data_inputs: two weekly CSV stores and `output/espn-weekly-store.json` |
| player-status-history | status_only: `output/player-status-history.json` job summary (not the Supabase history itself) |
| player-trace-rebuild | data_inputs: `dist/modules/player-trace.json` |
| rebuild-chain | status_only: Actions report; data_inputs: fixtures, baked players/manifest, comparison copy, lineage, value-check, divergence, chain/health copies, ESPN anchor, lineup parameters, `data/history/**`, `data/ddf-two-tier/**` |
| source-vintage-check | data_inputs: `.github/source-vintage-state.json` orchestrator input |
| sleeper-identity-refresh | data_inputs: `data/inputs/sleeper_identity_base.json` |
| health-artifacts | status_only: monitoring and ops reports; data_inputs: source-import-health and pipeline checkpoints |
| fidelity-pulse | data_inputs: `dist/modules/fidelity-pulse.json` |

Health/chain reports are conservative data inputs where the build reads them:
`sync_dashboard_artifacts.import_health_source` reads the runtime/dist health
copies; `build_pipeline_checkpoints` reads the chain output; rendered monitor
tests consume pipeline checkpoints. Ops/monitoring/Actions and the two job
summaries are report outputs, not committed engine/build/test inputs. Therefore
option A deliberately does not exempt every commit with a status-like title.
Option B includes the inventoried inputs and ESPN scraper source, but still
refuses any path outside these lists.

### Claimed, not confirmed

- No standing-rule approval has been given or applied. Both flags remain off.
  Option A enables status-only; option B additionally enables data_inputs.
- No live API/check run was attempted after discovering exhausted core quota.
  The PR's draft state is left untouched; it cannot be re-verified via API in
  this job. No merge, deploy, settings change or Linear post.
- `make validate` was skipped because Playwright Chromium is missing, as
  requested. Full core/deploy validation is not green in this environment.
