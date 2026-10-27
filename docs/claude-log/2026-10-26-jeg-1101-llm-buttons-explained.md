## 2026-10-26 - JEG-1101: what "Copy for ChatGPT/Claude" and "Paste from ChatGPT/Claude" do

Contract: explain the two JEG-1026 LLM round-trip buttons on the screen itself — one short line for each, an ⓘ with the
how-to, and the link to the MCP connect instructions — without moving or restyling the buttons.

Author: OpenRouter `deepseek/deepseek-v4.1-flash` headless run (T2, untrusted until a Claude T1 review re-reads the diff
and runs the gate).

### Verified (check named)
- `tests/test_v2_assist.py` (new `test_each_button_carries_a_line_and_an_info_slot`) — both lines, both ⓘ slots,
  `aria-describedby` and the `hidden` start are in `app/v2/shell.html`.
- `tests/test_v2_assist_render.py::test_copy_paste_round_trip_links_and_footer` — headless Chromium at 390 px: each line
  is drawn under its own button and unhidden, the ⓘ is a `.v2-info` in the button's `.v2-assist-action`, a **tap** opens
  it (no hover), the popover names the button's action, the assistant and the paste-back step, and its only link is
  `https://jb-barrel-droid.github.io/fantasy-tools/connect/` — the same href as the footer's `Connect the tool`. The
  pre-existing round-trip, deep-link and no-overflow checks in the same run stay green.
- `tests/test_v2_assist_render.py::test_guard_fails_on_broken_builds` — two new mutations, "no short line under the
  buttons" and "no ⓘ how-to beside a button", each make the checks fail.
- `tests/test_v2_waterfall_render.py::test_example_state_fits_the_fold` — the JEG-1112 Example fold at 1366x768 still
  passes (see the risk below: the margin shrinks).
- Measured before/after on a local build: the league strip is one row at 1366 px in both; the strip is 536 px wide
  (was 440) and the Example's give/receive/verdict bottoms move 740 -> 754 px against the 756 px limit.

### Re-run by Ba-Nana on the box after the hand fix (fresh `dist/v2` build)
- `tests.test_v2_assist` OK; `RENDER_TESTS_REQUIRED=1` `tests.test_v2_assist_render` + `tests.test_v2_phone_tap_targets_render`
  (5 OK; 320 px +3 px no longer scrolls sideways), `tests.test_v2_waterfall_render` + `tests.test_v2_contract_render`
  (13 OK).

### Claimed, not confirmed
- Not run here: `make validate`, `test_v2_a11y_render.py` (contrast of 11 px `--v2-muted` on the strip) and the rest of
  the suite. A T1 run should take them.
- The ⓘ opens on hover, keyboard and click by reusing `indexedInfoButton` (v2.js); the keyboard/click paths are the same
  code the contract test already exercises for the other ⓘ buttons, but this instance was not asserted on keyboard here.

### Risk / open question
- **The JEG-1112 Example fold margin.** A visible line cannot be added to the league strip for free. The line is a
  second grid row under its button (`.v2-assist-hint`, `grid-column: 1 / -1`, `overflow-wrap: anywhere`), so it cannot
  widen the strip; the row grows by about 14 px, so the Example's bottom edge at 1366x768 goes from 740 px to 754 px,
  leaving 2 px under the test's 756 px limit. Jeremy's recorded 2026-10-25 decision ("Trim the league row height", 6 px
  padding block) was not touched. Open question for Jeremy/PM: keep the line where it is (2 px margin), or compact
  something else in the header to hand the fold its margin back.
- **Phones (Ba-Nana hand fix after the run hit its turn limit).** Wrapping each button in `.v2-assist-action` dropped
  the old phone rule's flex share, and at 320 px with every font 3 px larger the strip scrolled sideways by 68 px
  (`test_v2_phone_tap_targets_render`). Below 768 px the action now takes the button's old share
  (`flex: 1 1 160px`, `minmax(0, 1fr) auto` columns) and the button may break "ChatGPT/Claude"
  (`overflow-wrap: anywhere`) so it fits beside its ⓘ. Desktop is untouched.

### New user-visible strings (all drafts for Jeremy)
- Under the Copy button: `Copies your league and your work.`
- Under the Paste button: `Applies a chat's answer here.`
- Copy ⓘ, accessible name: `What Copy for ChatGPT/Claude does`; title: `Copy for ChatGPT/Claude`
  - `Copies your league and what you are working on, ready for the chat.`
  - `Paste it into ChatGPT or Claude, ask, then paste the answer back here.`
- Paste ⓘ, accessible name: `What Paste from ChatGPT/Claude does`; title: `Paste from ChatGPT/Claude`
  - `Applies the answer a chat sends back, and says what it used.`
  - `Copy for ChatGPT/Claude first, paste that into the chat, then paste its reply here.`
- Both ⓘ foot links: `Connect the tool ↗`, href read from the footer's own link (no second URL).

No Sleeper/ESPN/Yahoo claim, no sign-up language and no publisher name in any of them; each line is under 15 words.

## T1 review (Ba-Nana merge wave, 2026-10-27)

- Fix: if the footer's connect link is missing, the ⓘ keeps the shared default link instead of a "Connect the tool" label pointing at the how-values page (`ddf-assist.js` `explain`).
- Merged origin/main in (no conflicts).
- Verified (check named): `tests/test_v2_assist.py`, `tests/test_v2_assist_render.py` pass locally after the merge.
- Claimed, not confirmed: the 1366x768 Example fold margin; the local fold test could not load the Example state from this worktree's committed `dist/`, so CI's `v2-render` is the check.

## Rework to Jeremy's decision (Ba-Nana run, 2026-10-27)

Jeremy, on JEG-1101 (2026-10-26 10:14 PM CT): "I don't think the chatgpt/claude buttons are good. if possible, We should
focus on copying the site link to llms and having them decode whats in it, as opposed to code from a link".

What changed (supersedes everything above: the per-button lines, the ⓘ how-tos and the `v2.js` popover hooks are reverted):
- Removed **Copy for ChatGPT/Claude**, **Paste from ChatGPT/Claude** and the paste box (`shell.html`, `v2.css`,
  `ddf-assist.js`: `PROMPT`, `copyText`, `applyPaste`, the JEG-1101 `explain` block). Links still open with their state (`applyLink`).
- One **Copy link** button in the league strip (same id `v2AssistCopy`): puts the current view's plain site URL on the clipboard,
  nothing else. One line under it (draft for Jeremy): `Opens this view. A chat with the DDF tool reads it too.`
- Connect guide (`docs/use-ddf-in-claude-chatgpt.md`) and skill (`app/llm/skill/SKILL.md`) now say the link is the hand-off.
- `supabase/functions/mcp/tools.ts`: `make_state` text no longer points at the removed paste box. **Not deployed**; it goes live
  only with the next `mcp` deploy.

How an LLM decodes a site link (investigated):
- The hash query (`docs/design/llm-site-state.md`) carries the league (`scoring`, `teams`, `roster`, `shares`, weeks, `bso`) and
  the work (`give`, `get`, `mine`, `theirs`, `target`, `view`). Players travel as site player numbers (`give=217`), or as
  `n:<name>` when only a name is known.
- The live MCP `read_state` already accepts a plain site link and resolves `player_key` (`tools.ts:860`): no MCP change is
  needed for links. Without the tool, a chat can read the league settings but not the player numbers.
- Live check 2026-10-27 through the DDF connector: `read_state` on a site link decodes the league but matches **no player**,
  because the live `get_values` returns `players: []`. Filed as JEG-1157 (High, `session:be`); not caused by this branch.

### Verified (check named)
- `tests/test_v2_assist.py` (new `test_one_copy_link_button_and_no_chatgpt_claude_buttons`) and
  `RENDER_TESTS_REQUIRED=1 tests/test_v2_assist_render.py`: the clipboard is the bare site link and reopens the same league
  and trade; a hand-written name link fills Find a trade and reports the unmatched name; no ChatGPT/Claude button or paste
  box on the page; the line sits under Copy link; no overflow at 390 px; 8 mutation guards each fail the checks.
- After merging origin/main `f7287c2e`, `RENDER_TESTS_REQUIRED=1` `test_v2_waterfall_render` (Example fold at 1366x768),
  `test_v2_phone_tap_targets_render`, `test_v2_assist*`, `test_v2_contract_render`, `test_mcp_remote`, `test_ddf_state` pass.
- `test_v2_share_render::test_shared_trade_link` and `test_v2_a11y_render` (contrast + 3 guard mutations) fail here and
  identically on a clean origin/main `f7287c2e` checkout: not caused by this branch.

### Claimed, not confirmed
- The live MCP decoding a site link end to end (blocked by JEG-1157).

## 2026-10-27 merge run (Ba-Nana T1 merge wave, Claude)

- Jeremy's decision (2026-10-27): the line under Copy link is option A, "Opens this view. A chat with the DDF tool reads it too."
- Merged origin/main. JEG-1119 had moved the assist buttons into the context row's ⋯ menu. Resolution: main's layout,
  with this PR's single Copy link button and its line inside the menu, and the paste box removed. The line now sits in the
  menu, so the 1366x768 fold margin question no longer applies.
- `tests/test_v2_assist_render.py`: kept this PR's checks, retargeted from `#v2League` to `#v2Context` and opening the ⋯
  menu before measuring (as main's version does).
- Generated churn (`dist/`, `app/trade-value-chart/`, `data/history/`) reset to main's; this PR ships no generated files.
- Verified (local, after the merge): `tests.test_v2_assist` and `tests.test_v2_contract_render` pass; `node --check` on
  `ddf-assist.js` and `v2.js`.
- `tests.test_v2_assist_render` fails one check: at 390px on `#find-trade`, `#waivers`, `#value-overrides` and the health check
  the ⋯ menu's left edge is at -40px. Cause is main's JEG-1119 menu (`min-width: 240px`, anchored right to ⋯, which sits at
  x≈182 on those tabs), not this PR: the menu is 240px whatever it holds. Main's own version of the check measures the same
  222px buttons at the same place (inferred, not run on main). The test is in the non-blocking full suite. Follow-up for JEG-1119.
