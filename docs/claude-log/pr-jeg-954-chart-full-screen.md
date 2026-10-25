## 2026-10-25 - JEG-954: chart Full screen and touch-to-inspect on phones (cloud worker)

Jeremy, 2026-10-23 (multiple choice): chart on phones is a "Full screen" pop-out with a rotate-to-landscape prompt (A1) plus touch-to-inspect.

### What changed (front end only: `app/v2/shell.html`, `v2.css`, `v2.js`)

- A "Full screen" button (44 px) in the chart head, shown below 768 px and on a sideways phone (short and touch). It opens the existing expanded-chart dialog (JEG-483), which already moves the live plot in, locks page scroll, traps focus and closes on Esc and the close button. Focus returns to the Full screen button. Desktop keeps the corner icon and shows no new button.
- The full-screen chart is compacted on phones: one-line head, Show chips and legend in one scrolling row, search and position on one row, and the plot takes the rest of the viewport (was 70vh under a tall stack of controls).
- A dismissible "rotate your phone to landscape" prompt shows in portrait only; Dismiss holds for the session (sessionStorage, with an in-memory fallback). No orientation lock (iOS Safari has none).
- Touch-to-inspect on both charts: a tap or drag shows the same player card as hover, placed on the side of the screen away from the finger, held 4 s after lifting. A tap only inspects; a second tap on the player still shown opens the details (hint reads "Tap again for player details"). The inline chart is `touch-action: pan-y` (vertical scroll stays with the page); the full-screen chart is `none`. Mouse compatibility events after a touch are ignored; keyboard arrows and the announcement from the a11y batch are unchanged.
- Not touched: nav, tables, `trade.js`, engine or value files.

### Verified (commands run)

- New `tests/test_v2_chart_fullscreen_render.py` (320x640, 360x740, 390x844, 844x390 with touch emulation, 1440x900 control): button size, open/close/Esc/focus return, scroll lock, full-viewport box, no sideways overflow, rotate prompt portrait-only and dismissible, tap and drag name the engine's row (`TradeValueV2.chart()`), second tap opens details, arrow-key announcement kept, no page errors. Passes.
- Discrimination: `test_guard_fails_on_broken_builds` serves eight broken builds (touch handlers removed, first tap opens details, prompt cannot be dismissed, focus not returned, no scroll lock, button missing on a sideways phone, full-screen chart lets the page scroll, prompt shown sideways) and each one fails the checks.
- Existing render files run one at a time, all green: `test_v2_expand_render`, `test_v2_a11y_batch1_render`, `test_v2_contract_render`, `test_v2_values_tab_ux_render` (it failed once on my first CSS, which hid the search box in the full-screen chart; the CSS was wrong, the assertion was kept). `test_v2_phone_layout_render` skipped 2 locally (cause not checked; not compared to `origin/main`).
- 12-combo engine sweep (`tools/engine_dump.py`, 13 settings) before and after: `fixedPieIndexed` true and `indexedOrderOk` true for all 13; the two JSON files differ only in the last float digit of `ddfPrior` (about 1e-16, run to run); no value moved. `sourceScaleAgreement` was retired (GAP-026) and is not in the dump. `check_rank_guard.py`: 0 inversions, 12 checks.
- Screenshots taken at 390x844, 320x640 and 844x390 (scratchpad, not committed).

### Not verified (assumed)

- Real-phone behavior: iOS Safari and Android Chrome touch, address-bar resize, rotating a real device with the dialog open, `safe-area` insets, and double-tap zoom. Emulation only.
- Chrome touch emulation drops a tap that follows a drag within about 300 ms, so the test waits 700 ms before the second tap.
- Held for Jeremy (on the ticket): whether the first tap should inspect and the second open the details (built), versus the first tap opening details as before.
- Sideways phone: the full-screen chart is about 124 px tall at 844x390 after the head and the search row; the chart scrolls if it needs more.
- Not built (from the plan, not in the brief): swipe-down to dismiss, history/back-button close, double-tap trigger.
