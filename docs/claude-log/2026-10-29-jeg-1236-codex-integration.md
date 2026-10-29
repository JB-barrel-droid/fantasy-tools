## 2026-10-29 - JEG-1236 Codex integration preparation

Contract: prepare Claude PR [#1097](https://github.com/JB-barrel-droid/fantasy-tools/pull/1097)
on a new Codex branch without modifying its author branch. Retain the reviewed
phone hit-target checks and narrow 44 px summary-filter input correction.

### Verified (check named)

- Live source head and all Linear comments rechecked before work: source remains
  `18571e920f8e1da080ae06ac8a58d5578e1e8573`, no competing newer preparation claim.
  Source author/feature credit remains Claude; Codex owns this integration only.
- New isolated branch `codex/JEG-1236-release-prep-20261029`, worktree
  `/workspace/wt/jeg-1236`. Normal merge of main
  `430791c41ca9578d878c14c3a37d37a0f3fe0670` completed without conflicts as
  `843eacc54abaf9473d0197aca866b0237dceab2d`. No authored runtime hunk changed.
- Byte comparison: `tests/test_v2_league_phone_render.py` equals the source head;
  SHA256 `a4ecb88a4ad23585c07ed0158f4f05d10b182d326f1bd13d49ac62356ccc70fb`.
  Merged `app/v2/v2.css` equals current main byte-for-byte after removing only
  the already-reviewed JEG-1236 comment and 44 px text-input rule.
- Preservation comparison: all 16 other changed app/pipelines/tests/Makefile
  files from main are byte-identical to main. Existing main content is retained;
  no application, fixture, workflow or data edit was authored during integration.
- `python3 -m unittest tests.test_build_v2_page tests.test_v2_tokens`: 9 PASS,
  no skips. `python3 -m py_compile tests/test_v2_league_phone_render.py` PASS.
  `node --check` on main's `design-flag.js` and `simplified-site.js` PASS.
  `git diff --check` PASS.
- Initial preservation script incorrectly included the intentional source phone
  test among main-owned files; after excluding the reviewed source test/rule,
  the explicit source-test and main-file preservation checks passed.

### Claimed, not confirmed

- Prior independent Mac evidence (two tests, eleven mutations) is retained for
  the unchanged phone code, per the coordinator handoff and source ticket;
  it was not rerun here. Main includes additional default-loaded builder script
  and opt-in styling, so current-head CI remains a distinct release gate.
- Fresh required preview/v2-render CI, independent integration delta review,
  healthy current main, release sequencing, publication/live verification and
  approval for new-branch automatic cleanup remain coordinator-owned gates.
- The Linear claim announcement was rejected by automatic approval review; no
  comment was created and no alternate posting route or blind retry was used.
- This preparation does not authorize merging, deployment, production workflows,
  Supabase writes, force pushes, original-branch pushes or branch deletion.
