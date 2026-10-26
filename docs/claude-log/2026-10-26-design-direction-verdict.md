## 2026-10-26 - design direction, Check a trade readings

Contract: one more pass on the design preview so Check a trade shows DDF Value, the Market, and Projections as three readings with real numbers, and so the headline font and canvas are decided.

### Verified (check named)
- `python3 app/v2-concept/build_sample.py` printed the sample trade: DDF gain 11.5, their Market change 3.5, projection points 21.8 a week to 21.7 (−0.1) and rest of season 240.1 to 239.0 (−1.1).
- `node --check app/v2-concept/concept.js` passed.
- `python3 app/v2-concept/check_preview.py` passed. It checked the three readings (+11.5 for you, +3.5 for them, 21.7 against 21.8, the 0.1 and 1.1 gains, and the small lean the other way), Show the math naming ESPN, CBS rest of season, and Razzball with the weekly rates, and Jahmyr Gibbs flipping the fit to They'll pass while the points say the same thing as DDF Value.
- On a 390×844 shot the projections reading ends at 683px and Show the math ends at 735px. On 1280×900 the three readings sit on one row and end at 446px. Measured in Playwright.
- Light PNGs replaced: `docs/design/shots/compare-390-light.png` (390×844), `docs/design/shots/compare-1280-light.png` (1280×900). Settings shots were refreshed in the same pass because the Projections sentence there changed.

### Claimed, not confirmed
- The DDF Value figure is still the projection read on the value scale, not the position-weight-adjusted trade-chart average. The doc says so. `make validate` was not run. No production v2 file was edited.
