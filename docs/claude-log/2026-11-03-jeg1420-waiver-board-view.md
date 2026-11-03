## 2026-11-03 - Standalone waiver-board reader / JEG-1420

Contract: implement the desktop/phone view against merged #1239's
`waiver-board` 0.1.x artifact. The parent authorized an independent renderer
and draft PR; dashboard wiring is a later coordinated change. T2 implementation
against the written contract, with no valuation or verdict decisions.

### Verified (check named)

- Linear issue/comments and GitHub open-PR search: JEG-1420 was Backlog,
  had no comments, and no duplicate renderer PR was found. PR #1239 is merged.
  Started from main `ad0cfc3a40ed3cdbb6d3291e4bb1c735d5bd6dfc` in isolated
  worktree `/workspace/jeg-1420`, branch `fe/jeg-1420-waiver-board-view`.
- `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest
  tests.test_waiver_board_view_render`: 12 tests pass, no skips. Standalone
  fixture reads the unchanged #1239 golden. Real builder/validator produces
  stale, previous-season, modeled, one-week-behind and unknown source variants.
  Checks cover 1366/650/390/320 widths, native table roles, keyboard disclosures,
  minimum 44px disclosure targets, zero versus missing, signed change, byes,
  injury/practice reasons, unsupported versions, empty boards, safe text,
  repeat rendering, settings callbacks and unchanged input objects.
- Same suite: temporary in-browser zero-fill and weekly-sort mutations are
  distinguished by the missing/order checks. No source files or existing
  assertions are mutated. Weekly points/status/byes changes preserve values
  and DDF ordering; missing sorts below negative and zero values, ties by key.
- Screenshot inspection found and fixed a narrow-caption issue missed by the
  initial overflow assertion. Caption width/height assertions now cover it.
  Final phone screenshot: `/tmp/jeg-1420-mobile.png` (local, not published).
- `node --check app/v2/waiver-board-view.js`, `git diff --check`, and
  `python3 -m unittest tests.test_render_sweep_coverage tests.test_validate_shards`:
  pass (20 registry/shard tests). Makefile changes only register the standalone
  test in the existing unit/core lists and core shard 3, so full preview CI and
  nightly unit checks execute it; no build recipe or pipeline is changed.
- `tests.test_render_sweep_shards`: four failures caused by
  `test_uso_site_journey_render` in `test-render-extra` but absent from its
  shards. `problems(git show HEAD:Makefile)` reproduces that exact missing-module
  result on unchanged main. This PR does not repair unrelated shard ownership.
- `make validate` launched through `pipelines.baseline_reds --context local`,
  with system Chromium explicitly selected and rendering required. Result pending.
- Linear state/provider metadata updates succeeded: In Progress, `codex`.
  Automatic approval review **denied** the claim comment, saying its project,
  branch and implementation details would be disclosed to Linear without
  explicit authorization for that payload/destination. The comment was not
  retried or relayed. The Linear field-notes read also returned tool-not-found.

### Claimed, not confirmed

- No independent review, full green gate, deployment or live-site behavior is
  claimed. Coordinator must assign review risk from the final diff; the new
  `tests/fixtures/waiver_board_view/standalone.html` triggers the fixture risk
  floor under AGENTS.md.
- Jeremy's copy/layout approval remains outstanding. No new verdict thresholds
  or eligibility rules are inferred from the design proposal.

### Integration handoff

- Load the new JS/CSS, obtain the validated built artifact for the selected
  setting, then call
  `TradeValueWaiverBoardView.render(host, board, {onSettings: openSettings})`.
  `onSettings` receives a copy of the board's setting. Without a callback,
  settings render as read-only context. Caller owns fetch errors and route/
  setting synchronization. The renderer never fetches, prices or saves data.
- Reader accepts 0.1.x only and clears old rows for an unsupported envelope.
  This version shows players and exact unavailable reasons for sections/swaps.
  Coordinate a reader update with JEG-1417/1418's future versioned contract;
  do not guess their shape or fabricate ADD/PASS/HOLD/DROP verdicts.
- JEG-1419 supplies artifact publication; dashboard script/style registration,
  board loading and mount/settings wiring belong to the later coordinated
  integration. `app/v2/v2.js`, `app/v2/shell.html`, contract, producer/build
  pipelines, swap adapter, package and bench sources are untouched.
- Serve the repo root with `python3 -m http.server 8000` and open
  `/tests/fixtures/waiver_board_view/standalone.html` to inspect the independent
  renderer. All names/numbers are the contract fixture, not current production.
- Validation regenerates app/dist/history artifacts. Those outputs are excluded
  from the PR; only the new renderer, CSS, harness/test, log and test registration
  are authored changes.

### Continuation - terminal results and inherited source-link readiness

- The existing sequential core continuation reached a terminal failure, not a
  parked running state: 74 recipes passed, then
  `tests.test_v2_phone_source_links_render.PhoneSourceLinksTest.test_source_links_have_44px_targets`
  found zero visible links at 320/375/414px. Exit 1 was captured in
  `/tmp/jeg-1420-core-terminal-observation.json`; the baseline wrapper called it
  a new, unattributed red. The original full `make validate` had separately
  stopped on a 20-second Razzball harness timeout; that exact case and this
  renderer's complete suite subsequently passed together (13 tests).
- Only the 42 previously unattempted core recipes were then run, sequentially,
  through the unchanged Makefile recipes and baseline wrapper. All 42 passed;
  terminal receipt `/tmp/jeg-1420-core-tail-terminal-observation.json`, full log
  `/tmp/jeg-1420-core-tail.log`. No duplicate broad run was launched and the
  earlier failures were not waived or removed from their logs.
- The source-link failure reproduced with the original assertion on untouched
  pinned main `ad0cfc3a40ed3cdbb6d3291e4bb1c735d5bd6dfc` in a detached checkout:
  one test, exit 1, the same zero-link results at all three widths. Receipt:
  `/tmp/jeg-1420-source-links-base-result.json`. This PR's renderer is not loaded
  by that existing Targets test, and its app scripts/styles/builder are unchanged.
- A read-only 375px probe found 44 source anchors in the DOM but zero visible
  links at the fixed 1.2-second measurement. After eight more seconds, 32 were
  visible, none were undersized, and horizontal overflow was zero. Metadata
  returned HTTP 200 and no page errors occurred. Evidence:
  `/tmp/jeg-1420-source-links-diagnostic.json`.
- The small validation repair replaces that fixed sleep with a bounded wait
  for the existing minimum of four visible links. It waits for visibility,
  not for 44px size. All three assertion calls, `_errors`, and the test methods
  (including the old-CSS negative control) are unchanged by AST comparison:
  `/tmp/jeg-1420-source-link-assertion-proof.json`. No registry exemption,
  assertion removal, timeout increase in the app, or test skip was introduced.
- Applied-source verification:
  `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m unittest -v tests.test_v2_phone_source_links_render`
  through `pipelines.baseline_reds --context local`: both tests pass, no skips,
  206.392s, captured exit 0. Actual test-file SHA-256 is
  `c5ca0766619ef9fb3e845435b6886a49489fd369e576c28689a02513cd784576`.
  Log and receipt: `/tmp/jeg-1420-source-link-repair-actual.log` and
  `/tmp/jeg-1420-source-link-repair-actual-result.json`.
- The previously unreached strict parity and integration targets also completed:
  `make value-check-compare test-integration` through the baseline wrapper,
  rendering required, exit 0. Engine/reference verdict is **agree** for
  1,234,507 values across 25 settings, with no page errors. Eight integration
  modules passed all 170 tests. Evidence: `output/value-check.json` and
  `/tmp/jeg-1420-parity-integration.log`.

Validation was completed in explicit phases after the first failures; this is
not a claim that a fresh, uninterrupted `make validate` passed after the repair.
No application, valuation, producer, bench or contract source was changed by
this continuation. The only code delta is the existing phone-test readiness
repair; the standalone renderer remains byte-identical to `f3efacfd`.

Full required CI, a current-head independent review receipt, Jeremy's copy/layout
approval and the separately coordinated dashboard hookup remain open gates.
The publication interface in draft #1264 is `/data/weekly/waiver-boards.json`:
select `boards[].setting` by scoring/teams/superflex and load `boards[].file`
before calling the renderer; the manifest is not a board. JEG-1417 still needs
before/after comparisons and Jeremy's threshold pick. JEG-1418's opt-in local
0.2 swap artifacts need a coordinated versioned reader update; this reader
continues to accept 0.1.x only. No denied external write was retried.
