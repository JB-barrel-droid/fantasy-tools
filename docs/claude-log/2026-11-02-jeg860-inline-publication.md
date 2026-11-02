## 2026-11-02 - JEG-860 inline players publication recurrence

Contract: reproduce the static-export mismatch on clean main, trace both bot
write paths, and repair publication without changing value math or patching
generated data. Jeremy authorized this Mac bridge build and PR; no merge,
deployment, Supabase access or HANDOFF edit.

### Verified (check named)

- Clean worktrees at reported `fdae242b1` and freshly fetched main
  `6d8375e77` fail
  `tests.test_static_export.StaticExportTest.test_inline_players_match_fixture`:
  inline players are dated 2026-10-26; the fixture is dated 2026-10-31.
- `git ls-tree` and SHA-256 of both files show identical bytes at `b7dbd362`
  and `fdae242b`. The latter commits only four status/health artifacts. Its
  "fixture not updated" message is accurate; it did not cause the mismatch.
- `8a3855823` (2026-10-31 successful chain bake) commits the newer players
  fixture but no engine HTML. `rebuild-chain.yml` runs `bake_players.py`, then
  `make validate`; `sync_dashboard_artifacts.py` replaces inline players in
  `app/trade-value-chart/index.html`. The chain's success staging list omitted
  that tracked template. `bake-players.yml` already stages both fixture and
  HTML through its broader `git add ... dist app ...` command.
- Another bake with the old workflow repeats this omission. A canonical
  `make sync` repairs the working build: in the clean full-gate run, all 36
  unchanged static-export tests passed. The isolated equality test passed
  again after sync. The reported static-export failure inside `make validate`
  was therefore not reproduced; raw checkout parity was reproduced.
- The fix adds only the engine template to the chain's success staging list,
  including no-bake rebuilds. Failure publication remains status/health only.
  The existing concurrent-main logic refuses publication when a newer edit
  to the same template exists on main.
- New workflow behavior regressions execute the real publication shell against
  disposable local Git remotes. Green bake and restored-bake parity tests
  failed before the fix. All five new tests passed afterward: green bake,
  failed validation, restored bake, no-bake template publication, and a newer
  template edit on main. Existing assertions were not weakened.
- The broader command below ran 59 tests: 58 passed; the pre-existing
  `RebuildChainBakeTest.test_catches_validate_removed_from_the_chain` failed.
  The exact same method also fails on untouched `fdae242b`. Its mutation
  removes the initial `make validate`, while the isolation retry still contains
  another invocation, satisfying the existing textual guard. Left unchanged.

  ```text
  .venv/bin/python -m unittest tests.test_rebuild_chain_bake tests.test_rebuild_chain_concurrent_main tests.test_rebuild_chain_workflow tests.test_chain_commits_legs tests.test_post_validate_workflow_wiring
  ```

- `actionlint -shellcheck= .github/workflows/rebuild-chain.yml` and
  `git diff --check` passed.

### Claimed, not confirmed

- Full `RENDER_TESTS_REQUIRED=1 make validate` is running serially with the
  repo's installed Playwright runtime. No other `make validate` was running
  at the live `pgrep` check before starting it. Supabase environment variables
  are unset; no credentials were read and no production operation was run.
- No generated output is intended for this PR. Committed-checkout parity on
  main will be repaired by the first successful chain after the workflow fix
  merges; this session does not dispatch that chain or publish data.
- Bot write-path change is high-risk and flagged on JEG-860. Independent
  Claude high-risk review and final-head CI remain required. The ready queue
  exceeds AGENTS.md's cap of eight, so this PR must be draft.
