# 2026-10-23 JEG-884 Compare search: overlap already fixed, dropdown widened

Session: fe-mac agent. Branch fe/JEG-884-expand-button.

## Verified
- On origin/main (35205b89) the Expand/Collapse buttons no longer overlap `#v2GiveSearch` / `#v2GetSearch`: JEG-861 part A (#820) gave the search its own row under the title. `elementFromPoint` at the input centre returns the input at 1280x800 and 1366x768 (probe, headless Chromium), and the existing guard (`tests/test_v2_phone_tap_targets_render.py`, overlap sweep at 375/768/1024/1280/1440 plus search hit test at 1024/1280/1366) covers it and fails on the old CSS.
- Remaining acceptance gap: the suggestion list was 217 px (1280) and 237 px (1366) wide, under the ticket's 240 px. Fixed in `app/v2/v2.css` (width max(100%, 260px), left-aligned, overlays the next column): 260 px at 1280, 265 px at 1366. Breece Hall row is on one line in both screenshots (`~/code/fantasy-tools-selfhost-notes/jeg-884-1280x800.png`, `jeg-884-1366x768.png`).
- New guard: `DROPDOWN` check in the same test (width >= 240, inside the window, first row not wrapped) at 1024/1280/1366 on both sides. Negative test: serving the CSS without the new rule yields four failures (217px and 237px on both sides); with it, green.
- Render tests run one at a time, green: test_v2_phone_tap_targets_render, test_v2_waterfall_render (JEG-917/932 fold), test_v2_compare_render, test_v2_modules_render. The change is absolutely positioned, so card and verdict heights (the ~6 px slack at 1366x768) are unchanged.

## Not verified
- Live site; touch devices; 1024-1279 widths beyond the existing guard (list is already wider than 260 px there).
- Full `make validate` not run.
