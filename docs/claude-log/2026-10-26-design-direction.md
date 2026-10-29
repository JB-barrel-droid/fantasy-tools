## 2026-10-26 - Design direction for a friendlier front door

Contract: a proposal Jeremy can review, not a production redesign. A direction doc, a clickable preview that does not touch the live v2 pages, and screenshots at 390 and 1280 in light and dark.

### Verified (check named)
- `python3 app/v2-concept/check_preview.py` (Chrome via Playwright, local server on port 8765, after the final copy): all checks passed. Home title at y=106 on a 390×844 viewport. Desktop title at y=314 on 1280×800. Default `--dur` is 200ms. With `prefers-reduced-motion: reduce`, `--dur` is 0ms. Targets opens on "The charts are split on Puka Nacua," Sells switches the headline to Chris Olave, a row expands to the four chart names, Compare starts at "Close for the charts. Not for the projection read," swapping in Jahmyr Gibbs updates the verdict to "You come out ahead," Clear returns to "Add a player to each side," the theme toggle sets `data-theme="dark"`, and More shows the desk group. Desktop shows the top nav and hides the phone tab bar.
- `node --check` on `app/v2-concept/concept.js` and `sample.js` exited 0.
- Screenshot PNGs in `docs/design/shots/` were written by headless Chrome at the named viewports (390×844 or 1280×800, and 390×900 / 1280×900 for a few opened states). The set covers home, targets, and compare in light and dark at both widths, plus an opened target row, the sell list, opened compare charts, and the More sheet.
- `pipelines/build_v2_page.py` copies an explicit file list from `app/v2/` (the `for name in (...)` loop). `app/v2-concept/` is not in that list. Read from the file, not from a publish run.
- Contrast of the token pairs was computed in this session (relative luminance). The light and dark pairs used in `concept.css` were at or above 4.5:1. The action button was 5.34:1 light (`#FFFFFF` on `#0C7A56`) and 10.96:1 dark (`#062018` on `#6EE4B8`).

### Claimed, not confirmed
- `make validate` was not run. The diff does not touch the production v2 sources, the engine, or the pipelines' publish list. A future session can confirm the gate is still green on this branch.
- The 200ms rise, thumb slide, and verdict cross-fade were not filmed frame by frame. The duration token and the reduced-motion override were measured, as above. The click-through confirmed the views, the expand, and the verdict text change.
- The sample numbers were not compared to a live engine read of DDF Value. They are the comparison fixture's rescaled chart values, as the preview's footnote says.
