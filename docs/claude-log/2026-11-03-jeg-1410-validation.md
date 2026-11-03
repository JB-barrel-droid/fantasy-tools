## 2026-11-03 - Manifesto validation / JEG-1410

Contract: Continue draft PR #1253 on its existing branch, preserving Jeremy's original article and approved explanation. Jeremy explicitly authorized the ownership claim and branch continuation; no merge, deploy or site publication.

### Verified (check named)
- Re-read JEG-1410 and all comments and PR discussion; no newer writer claim found. The November 2 Muse QA claim has a completed finding. Posted the authorized bounded claim as Linear comment d36b5373-ea3e-4514-90d2-94a7c5799213 and set the ticket In Progress, retaining Jeremy as assignee and the codex provider label.
- Merged current main 040474c552a324921bdc7f71008ab6da3f823629 normally into fe/jeg-1410-manifesto-block as 3cd2ff380fa090fe48b529f09bc15c27bff9db22. No conflicts, rebase or history rewrite. No authored shell change beyond the existing seven-line explanation.
- Registered the existing article pin test in test-unit-modules: the runner uses an explicit Makefile list, so the unlisted test previously did not run in that suite. `python3 -m unittest tests.test_jeg1410_manifesto_copy tests.test_run_suite`: 6 pass on the refreshed branch. `recipe_lines` confirms the pin is listed exactly once.
- The article remains 16,215 bytes with SHA-256 456641bd0b7348aed8144570b679d56cb7b3d5bd0738c6cb7b9705be075bf451, identical to main. The pin passes on the candidate and fails against untouched main because the explanation is absent.
- Local Chromium/Playwright on the isolated integration candidate at main 9605aa88: 390 x 844 and 1440 x 900 show the explanation after and outside the article, all 12 original headings, four paragraphs, no horizontal overflow, no added navigation link, and no page errors. The phone screenshot was visually inspected. The only changes from that main snapshot to 040474c5 are generated monitoring artifacts; app sources are identical.
- Existing tests.test_v2_manifesto_render fails two tests: the old Trade targets landing/one Writing-tab expectations and a stale landing mutation anchor. Repeating its render checks with current-main shell reproduces the same six complaints; current-main and candidate v2.js hashes match and both lack the mutation anchor. These failures are absent from the baseline registry; no test assertion was weakened and no registry entry added.
- On the old PR head 4b44c71b, preview and v2-render failed completion gates with expensive work skipped. The preview finalizer records RUN_EXPENSIVE=false, BUILD_RESULT=skipped, SHARD_RESULT=skipped; its gate ends with draft deferral. These do not establish an app regression or a full CI pass.

### Claimed, not confirmed
- The existing local make validate run is still active in the isolated candidate at main 9605aa88 (tool session 71106; log /workspace/scratch/jeg1410-evidence/validate.log). It is not a result on the new branch head. Heavy suites remain sequential; no second validation or browser suite was started while it runs.
- Full green CI and independent review on the pushed exact head remain required. PR #1253 stays draft. No main merge, deploy, production check or site publication.
