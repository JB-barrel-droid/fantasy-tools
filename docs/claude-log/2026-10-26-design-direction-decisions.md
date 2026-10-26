## 2026-10-26 - design direction, Jeremy's decisions

Contract: revise the design preview on the same branch so it matches the paste-only launch, the approved voice, and the trade-viability rule, and refresh the direction doc and the light screenshots.

### Verified (check named)
- `python3 app/v2-concept/build_sample.py` wrote 25 players. Featured buy Puka Nacua, DDF Value 59.0 against a Market of 50.1. Featured sell Chris Olave, 24.4 against 34.6. Sample trade gives Jaxon Smith-Njigba (47.5 / Market 53.6) and gets Puka (59.0 / Market 50.1): gain 11.5 DDF Value, their Market change 3.5.
- `node --check app/v2-concept/concept.js` and `node --check app/v2-concept/sample.js` passed.
- `python3 app/v2-concept/check_preview.py` passed (Playwright, system Chrome, local server on port 8765). It checked the hero micro-line, the positioning line, "Paste my league", the four paste tips, the running count, "Got it: 12 teams, 186 players", the toast, localStorage team `The Sharp Friends`, the Settings data line and Export / Import / Copy link, "Buy Puka Nacua", "Sell Chris Olave", the Send it sentence, "They'll pass" after swapping in Jahmyr Gibbs, "Show the math", the share card, no publisher names or debug strings or bench-shape copy, duration 200ms and 0ms under reduced motion, and confetti suppressed for reduced motion and for `shot=1`.
- The same check recorded the home headline at y=107 on a 390×844 viewport and y=124 on 1280×900, after the desktop hero was aligned to the top.
- Light PNGs in `docs/design/shots/` are 390×844 or 1280×900 (IHDR). The set includes the Sleeper paste screen, the match step, and the Check a trade verdict.
- `pipelines/build_v2_page.py` copies a named list from `app/v2/` (`APP_V2`). `app/v2-concept/` is not in that list. Read, not executed. `make validate` was not run. No production v2 file was edited.

### Claimed, not confirmed
- Contrast of the existing token pairs is unchanged from the earlier preview (light action 5.34:1, dark action 10.96:1). This pass did not re-measure them.
- A one-for-one Market gain is only a stand-in for "their lineup improves". The preview does not parse a paste.
