# 2026-10-08 · v2 How values work tab (frames 15 / 16)

Branch `fe/how-values`. Front-end lane only.

## What changed

- `app/v2/shell.html`, `app/v2/v2.js` (`renderHow`), `app/v2/v2.css`: "How values work" tab at
  `v2/#how-values`, explaining the three views per docs/methodology.md: VORP vs waivers, Data Driven
  Adjustments, Indexed. No value math, no new numbers.
- `tests/test_v2_how_render.py` (added to `make test-unit`).
- `docs/v2-design-notes.md`: How values work section.

## Verified (named checks)

- `make sync`, then `CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome make validate`
  exit 0.
- `tests.test_v2_how_render`: headless dist/v2 at 1440 and 390 after switching the engine to 10
  teams. League and roster lines equal the engine's `getState`/`getRosterShape`; each view lists
  exactly the engine's series of that method with availability and older-week labels; no "Vegas";
  "VORP" only in "VORP vs waivers"; no digits outside the engine line and step markers; no page
  errors; no overflow at 390. `test_guard_fails_on_broken_builds` fails on 4 mutations (bare VORP,
  hard-coded number, hard-coded league line, sources not split by method).
- Screenshots at 1440 and 390 reviewed by eye.

## Claimed, not confirmed

- Layout matches frames 15/16: not checked (figma.com blocked from this cloud session).
- Copy is my wording of the methodology; Jeremy has not reviewed it. In particular the VORP vs waivers
  card says published charts are translated the same way, which is the methodology, but the engine
  only exposes VORP vs waivers series for ESPN, CBS rest-of-season and Razzball, so only those are
  listed.
