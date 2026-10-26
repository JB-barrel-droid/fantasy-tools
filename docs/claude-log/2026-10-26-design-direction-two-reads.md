## 2026-10-26 - Check a trade, two reads

Contract: regroup the design-preview verdict so DDF Projections sit with DDF Value, and the Market is the other read. Proposal only. `app/v2/` is untouched.

### Verified (check named)

- `python3 app/v2-concept/check_preview.py` passed against `http://127.0.0.1:8765`. The sample is Don't do it. The DDF group shows charts −3.5 and projection sources +11.5, with point sizes −0.1 a week and −1.1 rest of season. The Market group shows +3.5. Jahmyr Gibbs still reads They'll pass, and both inputs agree.
- `node --check app/v2-concept/concept.js` passed.
- Playwright bounding boxes at 390×844 and 1280×900, `shot=1`: the two numbers sit side by side, the Market is a separate group, and Show the math is inside the viewport (button bottom 739 of 844 on the phone, 540 of 900 on the desktop). The points line sits inside the DDF card (bottom 473, card bottom 488).
- Light screenshots rewritten: `docs/design/shots/compare-390-light.png` (390×844) and `compare-1280-light.png` (1280×900). Home, Buy & sell, and Settings shots were rewritten because those labels changed with the terms.

### Claimed, not confirmed

- The chart figure is the indexed chart average, and the Market figure is the other seat of that same average. The position-weight adjustment is not in the fixture, so this preview does not show an adjusted DDF Value. Not checked against the live engine.
- `make validate` was not run. Production sources did not change.
