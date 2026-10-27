## 2026-10-26 - DDF Charted Value and DDF Projected Value

Contract: name the two DDF numbers DDF Charted Value and DDF Projected Value, keep the Market separate, and give each an (i). Proposal only. `app/v2/` is untouched.

### Verified (check named)

- `python3 app/v2-concept/check_preview.py` passed against `http://127.0.0.1:8765`. The sample gives Puka Nacua for Christian McCaffrey and reads Don't do it. DDF Charted Value is −6.1, DDF Projected Value is −10.7, and the points are −3.9 a week and −42.7 the rest of the season, the same direction. The Market is +6.1. A tap opens the charted sentence, Enter opens the projected sentence, and Escape closes it. Jahmyr Gibbs still reads They'll pass.
- `node --check app/v2-concept/concept.js` passed.
- On a 390×844 shot, Show the math ends at 762px and the tab bar starts at 783px.
- Light shots rewritten: `docs/design/shots/compare-390-light.png`, `compare-1280-light.png`, `targets-390-light.png`, `targets-1280-light.png`.

### Claimed, not confirmed

- The (i) sentences describe the live adjustment. This preview's charted figure and the Market figure are still the two seats of one unadjusted chart average, and DDF Projected Value is one projection source on the value scale. `make validate` was not run. No production v2 file was edited.
