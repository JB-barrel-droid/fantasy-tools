## 2026-10-28 - Preserve validated rebuilds during monitoring pushes (JEG-1206)

Contract: keep a validated rebuild and its week-history index publishable when
independent monitoring jobs change main. Preserve source edits, the failed-chain
status-only boundary, and one publication/deploy sequence. Branch push and draft
PR are authorized; the parent session owns merge and release. No main push,
workflow dispatch, deployment, production writes, or cleanup deletion.

### Verified (check named)

- Read JEG-1206 and its comments, the Oct 28 takeover map, current `HANDOFF.md`
  and `AGENTS.md`, and open PRs. JEG-1206 remained Todo, unassigned, without
  comments or a matching implementation PR. No `.agents/skills` directory was
  present. Base: `origin/main` at `0137a8a7`.
- Read job `122818944296` from run `40689076971`: validation succeeded, the
  publication rebase conflicted on `dist/modules/source-import-health.json`,
  and the dispatcher skipped because run `40689841714` was already waiting.
  Pages dispatch was skipped. The old summary incorrectly claimed a fresh run.
- The commit handler now creates a normal publication commit in a temporary
  worktree at current main, overlaying only staged candidate changes. It keeps
  newer independent monitoring reports. Any other main change requires fresh
  regeneration, including source edits that would merge without conflicts.
  Push attempts are bounded at three, without rebase or force push. An accepted
  commit is recognized after a lost push acknowledgement, including a transient
  failure of the confirming fetch, so Pages still gets dispatched. The original
  checkout is preserved and the candidate binary patch is retained as a run
  artifact. The handoff summary includes the dispatcher's actual result.
- `python3 -m unittest tests.test_rebuild_chain_workflow
  tests.test_rebuild_chain_bake tests.test_rebuild_chain_consolidation_nonblocking
  tests.test_rebuild_chain_conflict_handoff tests.test_rebuild_chain_failclosed
  tests.test_rebuild_chain_source_resiliency tests.test_rebuild_chain_per_source_hold
  tests.test_chain_commits_legs tests.test_record_post_rebuild_validation`:
  130 passed (exit 0). Covers real local bare-remote races, source/history
  protection, status-only failures, retry exhaustion, no-ops, and lost push
  acknowledgements. Evidence: `/tmp/jeg-1206-final-targeted-tests.log`.
- Independent regression/review agent: all 18 conflict/retry tests pass on the
  change; the same suite produces ten expected failures against `origin/main`.
  Evidence: `/tmp/jeg-1206-regression-baseline.log`. No blocking review findings.
- Workflow YAML parsed, extracted commit script passed `bash -n`, and
  `git diff --check` passed.
- Merged current main `032cee07` into the ticket branch without conflicts,
  reran all targeted tests successfully, pushed only
  `be/jeg-1206-publish-retry`, and opened draft
  [PR #1054](https://github.com/JB-barrel-droid/fantasy-tools/pull/1054).
  Preview build and v2 render CI started; current-head CI completion remains a
  release prerequisite for the parent session.
- Final input audit: `pipelines/fidelity_hold.py` reads
  `dist/modules/fidelity-pulse.json` to apply source holds, so that report is
  excluded from the independent-monitoring allowlist. Its regression fails if
  it is mistakenly allowed. The separate import-health promotion input is
  `output/source-import-health.json`, also excluded; the five allowed paths
  under `dist/modules` do not control source holds.
- Full `CHROMIUM_PATH=/usr/bin/chromium make validate` is running in the isolated
  `/workspace/validate-jeg-1206` checkout based on `0137a8a7`. The initial command
  without `CHROMIUM_PATH` stopped at the missing Playwright-bundled browser;
  browser download returned HTTP 403, so the installed system Chromium was
  selected. Final outcome will be recorded before this lane stops.

### Claimed, not confirmed

- Production publication and the live history index are not verified;
  JEG-1206 is not Done. The parent release session must merge the reviewed
  branch on green CI and green main, let one serialized rebuild publish, wait
  for its Pages deploy, and compare the live history index with that committed
  by the run.
- A queued independent rebuild can still coalesce a regeneration request; its
  inputs are not replaced. The summary now reports that skip honestly. Newly
  dispatched retries carry `attempt+1` and the requested bake flag.
