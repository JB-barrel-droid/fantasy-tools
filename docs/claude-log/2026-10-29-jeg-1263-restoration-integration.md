## 2026-10-29 - JEG-1263 restoration integration

Contract: prepare and release only the six-file revert in PR #1117, preserving unrelated main changes and both Simplified site implementation branches. Jeremy specifically authorized Codex to normally integrate main into this existing Claude branch; no force push, other Claude branch writes, expanded revert or Supabase changes are included.

### Verified (check named)

- Remote checks before integration found revert head `0be53fcd8d4944eae371f2177a40407928acae00` and main `430791c41ca9578d878c14c3a37d37a0f3fe0670`. PR comment `6503717695` announced the narrow integration claim and requested the author hold concurrent writes; no newer owner claim was visible.
- Normal merge and explicit non-force push produced `37b49b6e41c9a6345ce7da56e4839ca0b5754cb3`, with parents `0be53fcd` and `430791c4`. A second remote-head check immediately before push confirmed the author branch had not moved.
- Full-tree `git diff --name-status origin/main HEAD` and a six-path assertion found exactly the authorized Simplified CSS, script, fixture, harness and two test-file deletions. Fieldnotes assets, build registration, data and every surviving file match current main. `git diff --check` passed; the release worktree was clean.
- `python3 -m unittest tests.test_build_v2_page tests.test_v2_tokens`: nine tests passed in 0.328 seconds. No duplicate heavy local suite was run.
- Independent read-only delta review passed on `37b49b6e`: exact six-file scope, Fieldnotes/data preservation, no dangling asset, route, build or test references. Reviewer performed no edits or external actions.
- Remote reads preserved `claude/JEG-1263-simplified-site` at `6be60d2e48fb30d6c8315c6601aff6b5becfb2ef` and `claude/JEG-1263-simplified-site-review` at `f76cf55b9a970eea49098169b67a84f88ba06acb`. This executor did not change #1118.

### Claimed, not confirmed

- Fresh exact-head Preview `40921629158` and v2-render `40921629146` were pending/queued at 17:29 UTC; current-main Pages `40917652462` was queued. No merge, publication or live success is claimed by this checkpoint.
- Live Pages access in this environment was previously denied by the network proxy. Publication SHA/build must be handed to the coordinator for the existing Mac live-check task after successful deployment; no browser QA execution by this worker is claimed.
- Documentation is prepared on a separate Codex branch to keep #1117's approved diff at exactly six deletions. Its merge and branch deletion remain held.
