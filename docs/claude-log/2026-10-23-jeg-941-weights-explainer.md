# 2026-10-23 JEG-941 position weights explainer in How values work

Added a collapsible "How position weights work" section to the league card on the v2 How values work view (app/v2/shell.html, v2.js, v2.css). Button with aria-expanded, collapsed by default, no separate card (Jeremy 2026-10-23). Copy condensed from the research post's dashboard draft; percentages dropped because the tab's copy guard forbids hard-coded numbers and the live shares sit in the card above.

Verified: tests.test_v2_how_render (2 tests, OK) at 1440 and 390, including a negative test that fails on three broken builds (open by default, dead toggle, changed wording).
Claimed, not checked: appearance in a real browser at 390 px beyond the overflow assertion; contrast in dark mode (reuses existing color tokens).
