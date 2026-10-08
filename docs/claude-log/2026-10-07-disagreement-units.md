## 2026-10-07 - "Largest disagreement" mixed VORP vs waivers into the point-scale spread

Contract: confirm, then fix, a report that the main page's "Largest disagreement"
spread mixed VORP vs waivers series into the trade-value point scale (frame 22:
"never compute a spread or aggregate across unlike units"). No value math changes.
Branch `fix/disagreement-units`, pushed, not merged.

### Finding (read from code, then confirmed by test)
- `curve-widget.js` `disagreement()` took max - min over `visibleSourceKeys()`, which
  is every key (SOURCE_KEYS + PURE_VORP_KEYS), not just the shown curves. So the
  three VORP vs waivers curves (espn_vorp, cbsros_vorp, razzball_vorp) always
  entered the spread. In the VORP vs waivers view the published charts
  (usatoday, fantasycalc, fantasypros, cbs) also carry VORP vs waivers values
  (`buildSourceMap` -> `publishedViewMap`), so they entered it too.
- `comparison-dashboard.js` `rows()` computed the Disagreement column over all
  `renderKeys`, which include the same three VORP vs waivers keys.
- `app/v2/v2.js` "DDA spread" already uses `view.plotKeys` only; not affected.

### What changed
- `curve-widget.js`: new `spreadSourceKeys()` = visible keys minus PURE_VORP_KEYS,
  and minus the published charts while the VORP vs waivers view is on.
  `disagreement()` uses it. In the Adjusted values view the published charts stay
  in (Adjusted series are on the point scale).
- `comparison-dashboard.js`: the Disagreement spread filters out PURE_VORP_KEYS.
- New `tests/test_disagreement_units_render.py`, added to `make test-core`.

### Verified (check named)
- `python3 -m unittest tests.test_disagreement_units_render`: 3/3 OK on the fix.
  Indexed view: the page's disagreement order is sorted by the point-scale spread.
  VORP vs waivers view: sorted by the spread without published charts or *_vorp.
  Table: every rendered Disagreement cell equals max-min of the point-scale cells
  (within 0.11 for rounding).
- Negative tests: with the fix reverted (`git apply -R` of the two-file patch) all
  3 tests fail. In the table, a cell shows 32.6 where the point-scale spread is
  30.5. With only the view-mode clause removed, the VORP-view test fails (1/3). Each
  test also checks, independently of page order, that the live data separates the
  two spread definitions, so a pass cannot come from data that hides the bug.
- 12-combo headless sweep (3 scorings x 8/10/12/14 teams, scratch script against
  `dist/` after `make sync`, baseline = `make sync` on unmodified origin/main):
  `fixedPieIndexed`, `sourceScaleAgreement` and `sourcePeaks` are identical to main
  in all 12 combos. fixedPieIndexed is true everywhere. sourceScaleAgreement is
  false on both main and the fix: this is the existing non-blocking
  genuine-publisher-disagreement notice, not something this change caused. The
  disagreement top-20 order changed in all 12 combos, as expected.
- `make sync` exit 0. `CHROMIUM_PATH=<system Chrome> make validate` exit 0.
  `tests.test_public_copy_no_vorp` OK.

### Claimed, not confirmed
- Live site not checked; the branch is not merged or deployed.
- The Adjusted values view's published-chart values (`adj_values`, `adjScale`)
  are on the shared point scale. I inferred this from the methodology ("Adjusted
  values") and the brief. I did not measure it numerically.
