## 2026-10-29 - JEG-1274 target answer card

Contract: build the isolated trade-target answer card (buy, sell, fair, empty, missing, unavailable) with a mocked
evidence detail slot, its contract doc, synthetic fixtures, a preview and tests, without touching shared files.

### Verified (check named)
- Every contract rule holds and each guard catches a deliberate break: `python3 -m unittest tests.test_target_answer_card_contract`
  (3 tests OK; 14 harness checks; 12 mutations each caught by the named check).
- Mount behaviour in jsdom 24 (scratch script, not committed): all eight fixture cases mount with the right state;
  focus stays on the detail toggle across 4 toggles and 3 re-renders; open state kept on re-render and reset on a new
  player; Escape closes and returns focus; slot mounts minus cleanups is 1; a throwing slot leaves the card up; destroy
  clears the host; zero shows 0 and a missing value shows No value.
- No shared or excluded file changed: `git diff --name-only origin/main` lists only the new paths.

### Claimed, not confirmed
- Layout at 320, 390 and 1280 with no sideways scroll, real keyboard and touch input, and no storage or network in a
  real browser: `tests/test_target_answer_card_render.py` is written but was not run here (no Chromium in this cloud
  session; the browser download host is blocked). It needs a run on a machine with Playwright.
- Neither test module is in a Makefile run list (CI wiring is Codex's).
