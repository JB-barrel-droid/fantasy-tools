# Not reviewed caption on Optimize for playoffs (JEG-1023)

**Date:** 2026-10-24

## Changed
- `app/v2/v2.js` (renderSeasonWeeks): plain-text caption "Playoffs: not reviewed, may not work as expected" right after the Optimize for control (id `v2OptimizeNotReviewed`); the Playoffs button gets `aria-describedby` to it.
- `app/v2/v2.css`: `.v2-optimize-caption` margin and wrapping.
- New `tests/test_v2_optimize_caption_render.py`. No existing test changed. Setting behaviour and value math untouched.

## Verified
- `tests.test_v2_optimize_caption_render`: 2 tests OK (caption present, aria-describedby, in the panel, no page overflow, 44 px buttons at 1440/390/320). The guard test fails three broken builds (no caption, not associated, overflowing caption).
- `make -o sync validate`: exit 0 (generated files left unstaged, not committed).
- `test_v2_season_weeks_render` and `test_v2_contract_render`: not run locally (render lock queue); left to CI v2-render.

## Not verified
- No visual screenshot review; the 320/390 fit is from the DOM measurements above.
