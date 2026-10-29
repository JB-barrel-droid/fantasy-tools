## 2026-10-28 - League finder release batch (JEG-1213, JEG-1134, JEG-894)

Contract: Jeremy approved small integrated release batches and pushing draft PRs.
Prepare one release candidate; parent owns independent review, #1056 live QA,
merge and publication. No subagents were used in this integration.

### Manifest

| Input | Exact included head | Outcome |
| --- | --- | --- |
| Main baseline | `7e4f2603a67aa121ee22239b9cf601f83ac1e851` | Includes merged #1056/JEG-1170 `904d07ae99320dc5d47ed3d38499af891d6c2dcf`; preserve all current-main changes |
| #1058 / JEG-1213 | `acd4b0c2ee18b3d8a3796d1106f7885ae49eeb74` | League transfers/settings sharing, paste cleanup/collapse, count warnings, summary columns/filters, ordering and fit explanations |
| #1043 / JEG-1134 | `d886fc9f8151b6f13f4cfdc639bf3c3d305245f4` | Phone context summary and override/Reset/Undo behavior, including fallback-font repair |
| #969 / JEG-894 | `391308edbd932396c72b23fe2524892b0b55e7a6` | Compare and finder share links preserving rosters/settings/search choices |

Both dependency heads are ancestors of #1058. Started from exact main and normally
merged #1058 once; no cherry-picks or duplicate source changes. Sole conflict was
HANDOFF's concurrent lane insertion; kept both sections and added this batch status.
Application files match #1058 exactly. Engine sources and generated assets match
baseline main (excluding local test output, which is not committed).

`git ls-remote` shows the real #1043 branch at `d886fc9f`, matching the PR API;
its synthetic `refs/pull/1043/head` still advertises `68b95fa5`. Verified the actual
branch directly and proved `d886fc9f` is an ancestor of the integrated candidate.

### Release choices and exclusions

- Only the three approved PRs are new release scope. Current-main #1044 engine and
  #1056 workflow behavior is inherited, not reimplemented.
- Supported team counts are explicitly **8 / 10 / 12 / 14**. Expanded the existing
  browser test across all four exact-count quick fixes, below-eight silence, and
  unsupported 9/15 counts: explanation/settings link, no invented value mode,
  settings and rosters preserved.
- Oversized shares retain existing marked-team fallback and Download explanation.
- Exclude #1059 release switch, source health, connector/Supabase, and other backlog.
- Underlying PRs and Linear tickets remain open; this draft batches their combined
  diff rather than landing dependencies separately. No branch deletion or production
  deployment. Parent must complete #1056 live QA before a main merge.

### Verified (check named)

- Read current HANDOFF/AGENTS, merge runbook, live PR API metadata and Linear
  JEG-1213/1134/894 plus JEG-1213 comments. Linear get_agent_context was attempted;
  server returned tool-not-found, so no shared field notes were available.
- Exact heads verified using GitHub PR API and git ls-remote actual branch refs.
- `git merge-base --is-ancestor` for both dependency heads: exit 0.
- `git diff origin/release-input-1058 -- app/v2 tests/_render_env.py`: empty.
- `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_jeg1213_import tests.test_jeg1213_logic tests.test_jeg1213_summary_fields tests.test_jeg1213_acceptance_render tests.test_v2_phone_context_row_render tests.test_v2_share_links tests.test_v2_share_links_render`: 27 tests PASS, no skips. Includes all count boundaries, fresh-context shares, malformed links and mutation guards.
- `python3 -m unittest tests.test_preview_workflow_matches_pages`: 40 PASS.
- `python3 -m unittest tests.test_ci_speedup_workflows tests.test_validate_shards`: 28 PASS. Integrated core shard coverage/parity remains exact.
- Two initially guessed extra module names did not exist and produced import errors;
  discovered the correct modules above and ran them successfully. No test assertions
  weakened. `git diff --check` passed.

### Claimed, not confirmed

- Inherited independent acceptance and repair reviews on #1058 are recorded in its
  PR/log; these do not substitute for parent-owned final integrated-head review.
  #969 needs final-head review as part of that combined review.
- Required final-head Preview build (validate-base, exhaustive core shards, all
  rendered harnesses) and v2-render CI: PENDING. No full local duplicate gate.
- Live release behavior and #1056 production timing/publication remain parent-owned.

### Exact incoming commit manifest (including normal merge ancestry)

```text
acd4b0c2ee18b3d8a3796d1106f7885ae49eeb74 Record verified phone CI repair and dependency integration (JEG-1213)
010f7a7d83db2825b5e55f676d9c4802b06cfcd3 Merge remote-tracking branch 'origin/main' into fe/jeg-1213-league-finder
df20ab3e830216e22f5d3aa59d28525d8676d57d Merge commit 'd886fc9f8151b6f13f4cfdc639bf3c3d305245f4' of https://github.com/JB-barrel-droid/fantasy-tools into fe/jeg-1213-league-finder
6153bc89c60f5918341b51ac8d5eb8550e99ed2f Record JEG-1213 draft delivery and validation checkpoint
8019b99a6ae38f76bde8028ec762a78c6f4a9cc6 Read all opportunity rows when only More is offered (JEG-1213)
3c08ed3260cff07b91efb16b0e3d22cb25c51d92 Keep fit explanations and expanded opportunities usable (JEG-1213)
3a8d38cbc1196156d248436834280190ab63bc74 Preserve K and DST identity in copied league links (JEG-1213)
a07ea23e75e7ddab0752e687c26035f7bd0c8a12 Test league-wide finder improvements and share roundtrip (JEG-1213)
fd2b79a26df8307f8f7868f4d1d03ce70a8cf827 Improve league transfers, sharing and pasted roster review (JEG-1213)
56d024e127283bc43245078a19a6cd192f416b5a Explain opponent market totals and retain package context (JEG-1213)
2da11d8e05a914c0ffb3a81de8b86d748a3a1e4c Add summary columns and filters to league opportunities (JEG-1213)
1ced49377ff90f933e07f9b2ebf2a40523e459cb Merge remote-tracking branch 'origin/pr-969' into fe/jeg-1213-league-finder
9c4ac88f5e3489718d4a9c31d76c3cb6c21f1a49 Merge remote-tracking branch 'origin/main' into fe/jeg-1213-league-finder
d886fc9f8151b6f13f4cfdc639bf3c3d305245f4 JEG-1134: fit the phone summary in CI fallback fonts
68b95fa5a7159f179c354dcce23b403f5d0e22fd JEG-1134: record latest-main validation and review handoff
7d016a8469ae5e0628b228ba357f9bbb3d6fa6ba Merge remote-tracking branch 'origin/main' into fe/jeg-1134-context-phone-summary
5a43670762136903b16e2e8e722e57071e09adad JEG-1134: keep phone overrides and Copy link usable with a closed summary
7dbe28a9cf83d7a86cb2ef681532fae9a4161dce Merge main into JEG-1134; preserve Copy link checks and picks logs
21c6252ff19ca8fd672db75f49873ebfe623447e JEG-1134: keep the Overrides indicator on the closed phone row (review)
2549bfed0c9f63425081d9336e47e58b05749727 Merge remote-tracking branch 'origin/main' into fe/jeg-1134-context-phone-summary
baaf76b4dbb539ef99c64d1a8fd3386bd4b55bb0 JEG-1134: review fixes (advanced test opens the phone row; Overrides indicator stays on the closed row)
365d050c8a2314513516b48a37641b3fdc2f20ea JEG-1134: leave HANDOFF.md to the handoff PR on main
a4c065771bb9619ade2325c739d1ff40bae21f83 Merge remote-tracking branch 'origin/main' into fe/jeg-1134-context-phone-summary
c59a5de34174f236bc893d214a5bbb505e713106 Phones: the context row collapses to a one-line summary (JEG-1134)
98c4ce705f2b4c20dd077bbf3e9039bc62512427 Merge remote-tracking branch 'origin/main' into fe/jeg-1134-context-phone-summary
391308edbd932396c72b23fe2524892b0b55e7a6 Merge remote-tracking branch 'origin/main' into fe/JEG-894-share-links
6f4984457814baf2850a02bb70c6a61d35d4f331 JEG-1134: measure the phone context row height on main (render probe)
b6cea06c3116f52cce4fad0a824b491a43d1d4ca Merge main into JEG-894 share links
4ec24a81a6226a736e27272ccaf845c867ba507c ci: retrigger preview (previous run cancelled mid-validate)
ad24d24814fdd8513f68f5d41cf166c24b66f00d Merge remote-tracking branch 'origin/main' into wave/merge-969
d4a0a665e0dcdc640b5189bac2fbe9a8c469d88c JEG-894: log the T1 review and main merge-in (part of JEG-894)
eec4a8abecbded55870601cf52d5f41c99e44826 Merge remote-tracking branch 'origin/main' into wave/merge-969
84560c941c849b23248bc9893d72ba01a5d04d3f Merge origin/main into fe/JEG-894-share-links (resolve finder.js api export)
68d28a28dd86a125874fb98faf6eb60ffe15b298 JEG-894: Copy link beside the verdict; a finder search link
```
