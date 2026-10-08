# 2026-10-08 · v2 front end: Figma review (task 1)

Read every frame of "V3 · Resolved design & handoff" in a headless browser (no sign-in, no Figma
connector) from a local session, since the cloud session could not reach figma.com.

## Verified

- Node ids for all 25 frames read from the layers panel (`data-testid="<id>-layers-panel-row"`), and
  each frame opened by `?node-id=` and screenshotted: 05, 06, 07, 08, 13, 14, 15, 16, 18, 20, 21, 22,
  23, 24, 09–12, 17, 19 and 00.
- `docs/v2-design-notes.md`: frame map now lists all 25 frames; new section "Figma review: what the
  frames specify that the build lacks" lists the gaps per frame.
- Baseline on `origin/main` (fb0e7f7) before the change: `make validate` recipe exit 0 (run through a
  Makefile recipe runner, since this Windows machine has no `make`); all eight `tests/test_v2_*_render`
  suites OK.

## Claimed, not confirmed

- Mobile frames 06, 08, 14 and 16 are taller than the viewport; their lower parts were read from the
  overview screenshots at lower zoom. Nothing below the visible part looked like a new control.
- Frame copy that is design-fixture only ("Illustrative source snapshot", Week 4 numbers) is treated
  as not part of the spec.

## Environment notes for the next local session

- No `make`; `python3` is the Microsoft Store stub on this machine. A venv at `~/.venvs/ft` with a
  `python3.exe` copy, `playwright` and `tzdata` (zoneinfo needs it on Windows) runs the suite.
- Playwright's own Chromium at `~/AppData/Local/ms-playwright/chromium-1243` is what
  `_chromium_executable` finds; `CHROMIUM_PATH` is not read by that helper.
