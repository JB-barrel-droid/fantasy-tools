## 2026-10-26 - JEG-1112 follow-up: compact Compare's header and Example banner, guard the example state

Contract: the live Compare example view (what a new visitor sees) ended 27 px past the 1366x768 fold, with the totals under both sides clipped. Jeremy chose, 2026-10-26 (multiple choice), "Compact the header + Example banner": Compare's own header only, other tabs untouched, and the guard extended to measure the example state.

### Changed
- `app/v2/shell.html`: the Example banner (`#v2CExample`, with the chip, the sentence and `#v2CUseExample`) moved inside `.v2-chead`. No id, no word and no JS changed (`app/v2/v2.js` is not touched).
- `app/v2/v2.css`: from 1280 px, `#v2Compare .v2-chead` is a grid. Row 1: title, Example chip, "Use this example", "Player values shown" picker. Row 2: subtitle, week line, sample-trade sentence. Below 1280 px (tablet, phone) the header is the old stack: the banner is a full-width flex item of the header with the same 8 px gap as before.
- `tests/test_v2_waterfall_render.py`: `test_example_state_fits_the_fold` and `test_example_fold_guard_fails_on_the_old_header`. No existing assertion changed.

### Wording
- No wording changed. Every word of the title, subtitle, week line and banner is kept. The sentence now shares row 2 with the subtitle and week line from 1280 px (it wraps to a second line when it does not fit).

### Verified (check named)
- Reproduced the live numbers on origin/main 99e3f5ef (own measure script, same built dist, 1366x768, example state): give / receive / verdict bottom 794.9 (Inter) and 794.2 (CI fonts: DejaVu Sans, Inter / JetBrains Mono / Carlito / Caladea rejected by fontconfig); totals row bottom 785.9 / 785.2. The Inter number equals the live 794.9. At 1440x900: 854.8 / 872.4 (verdict), totals 837.8 / 855.4.
- After, same script: 1366x768 give / receive / verdict 740.1 (Inter) and 739.5 (CI fonts), totals 731.1 / 730.5, i.e. 54.8 / 54.7 px saved and 28 px above the fold. 1440x900: 795.5 / 813.0, totals 778.5 / 796.0.
- The guard (`test_example_state_fits_the_fold`) requires give, receive, verdict and both totals rows to end 12 px or more above the fold at 1366x768 and 1440x900, in the browser's fonts and with DejaVu Sans forced; it does not seed the example (live data).
- Mutation: `test_example_fold_guard_fails_on_the_old_header` serves v2.css without the 1280 px grid rule (the old four-line header, measured equal to origin/main: give 794.2 at 1366x768) and gets "GUARD CAUGHT" in both fonts.
- Phones 390 / 360 / 320 (and 767 / 768 / 1100 / 1280): no sideways scroll; "Use this example" 44 px tall; heights of both sides and the verdict unchanged from origin/main to the pixel at 390 / 360 / 320 / 768 / 1100. The seeded scenarios (#942 / #947) read the same verdict bottoms as before (644.5 and 717.2 at 1366x768).

### Claimed, not confirmed
- The 12 px margin is a judgement: it leaves room for one more line of verdict text from a data bake (about 18 px would not be tolerated; the current spare is 28 px). A bake that makes the example's verdict text one line longer than today's still passes; two lines longer fails the guard in v2-render, which is the intent.
- Row 2 at 1280-1365 px in DejaVu Sans: the sentence wraps to a second line (header 85 px instead of 68), the fold is not checked at those widths.
- The old header is served by removing the CSS grid, which falls back to the old stack; it was compared against an actual origin/main build at 1366x768 and 1440x900 (794.9 / 854.8 Inter), not at every width.
