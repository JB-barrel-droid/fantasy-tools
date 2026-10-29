## 2026-10-29 - JEG-1266 homepage AI connection panel (isolated phase, part of JEG-1137)

Contract: build the homepage "Find your best trade in Claude or ChatGPT" panel as an isolated component with truthful setup and
sharing states, fixtures and tests, not loaded by the site. Integration stays with the JEG-1137 owner (plan below).

New files only, plus one CI line:
- `app/v2/ai-connection-panel.js`: `window.TradeValueAiConnectionPanel` (COPY by string ID, UI, viewModel, copyLink, liveAdapter, render, mount).
- `app/v2/ai-connection-panel.css`: scoped to `.ai-connection-panel`, v2.css tokens only, no Fieldnotes (JEG-1209/1250) adoption.
- `tests/fixtures/ai-connection-panel/synthetic-states.json`: nine labelled synthetic contexts.
- `tests/ai_connection_panel_harness.cjs`, `tests/test_jeg1266_ai_connection_panel.py`, `tests/test_jeg1266_ai_connection_panel_render.py`.
- `.github/workflows/v2-render-test.yml`: one step that runs the two JEG-1266 test modules where Chromium is installed.

What the panel can show:
- Setup: available (the Connect the tool link to `connect/`, same href as the footer) / unavailable / unknown. Unknown never shows the link.
- Share: ready (Copy link, plus what the link carries) / missing (no saved league and no trade, target or rosters) / unavailable
  (no link builder) / unknown (not attached yet). Clipboard off relabels the button "Show the link to copy".
- Copy: copied / failed (the pack's "Couldn't copy. Copy this link:" plus the link selected in a text box) / nothing / error.
- Connection: none. There is no connection input; the connected-user step is always the pack's conditional "Already connected? Try asking:".

### Verified (check named)
- `python3 -m unittest tests.test_jeg1266_ai_connection_panel`: 7 pass, 1 skip (the verbatim pack check skips until PR #1078's
  doc is on the branch). 14 harness checks pass; 14 mutation proofs each caught by the named check.
- Copy is the pack verbatim except one line: with `docs/product/jeg-1223-ai-onboarding-copy.md` from PR #1078 head 91b0328
  copied in temporarily, `test_copy_is_the_pack_verbatim` passed for all 13 strings (file removed again; it lands with #1078).
  The exception is `ai.link.local`: the pack says "stays in this browser", which `tests/test_launch_copy_guard.py` (JEG-1130)
  forbids, so the panel says "stays on this device" and the verbatim test maps that one pack line to the launch wording.
- CI v2-render on 2458fb0: the JEG-1266 step ran 12 tests, OK (skipped=1). Its first run (1962b44) caught a real bug: mount's
  `update()` returned the container, not the view model, so the result after a click threw before it was announced or the
  link was selected. Fixed in 2458fb0.
- Preview shard 1 on 2458fb0 failed `test_launch_copy_guard` on the browser wording above; fixed in the next commit.
- Acceptance checks 2, 3, 4, 8, 9, 10 of the pack run over every COPY and UI string (`AiConnectionPanelCopyTest`).

### Claimed, not confirmed
- `tests.test_jeg1266_ai_connection_panel_render` (9 states x 1280/390/320, keyboard order, focus ring, copy success and failure,
  no storage writes) ran only in CI (above): this container has no Chromium. Screenshots are the run's `ai-panel-previews`
  artifact; nobody has looked them over by eye yet.
- The live adapter is checked against fake pages only. It has not run on the built dashboard (the panel is not loaded there).
- `make validate` and the contract test were not run: no loaded file changed.

### Integration plan for the JEG-1137 owner
1. `pipelines/build_v2_page.py`: add `v2/ai-connection-panel.js` (defer) after `ddf-assist.js` and before `v2.js` in the script
   list; add `ai-connection-panel.js` and `ai-connection-panel.css` to the copy list; link the CSS where `v2.css` is linked.
2. `app/v2/shell.html`: one `<section class="ai-connection-panel" id="v2AiPanel"></section>` in the homepage view, where the new
   home layout puts the AI block. The panel brings its own h2, so the home view keeps its h1.
3. `app/v2/v2.js`, right after `window.DDFAssist.attach({...})`:
   `const aip = window.TradeValueAiConnectionPanel; const aipEl = $("v2AiPanel"); if (aip && aipEl) aip.mount(aipEl, aip.liveAdapter(window));`
   The panel re-reads on hashchange; call the returned `update()` after a league load if the home view stays mounted.
4. Tests: point `test_copy_is_the_pack_verbatim` at the merged pack (it runs automatically once #1078 merges), and add a
   built-page check that `#v2AiPanel` shows `data-setup="available"` and `data-share` of `ready` or `missing`, never `unknown`
   after load. Fixtures stay labelled; the live adapter never sets `fixture`.
5. Public rollout still waits on JEG-1209 design review and the JEG-1130 copy gate.
