# 2026-10-08 · v2 player detail on mobile and empty / loading / failure states (frames 13, 14, 18)

Branch `fe/detail-states`. Front-end lane only.

## What changed

- `app/v2/v2.js`: player detail grouped by method (VORP vs waivers in its own group); `renderEmpty`
  for Player values; `showFailure` replaces the error pill with a failure card and hides every tab.
- `app/v2/shell.html`: loading / failure card, Player values empty state; Player values starts hidden.
- `app/v2/v2.css`: bottom sheet below 768 px, state cards.
- `tests/test_v2_states_render.py` (added to `make test-unit`), `docs/v2-design-notes.md`.

## Verified (named checks)

- `make sync`, then `CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome make validate`
  exit 0.
- `tests.test_v2_states_render`: detail at 1440 (right drawer) and 390 (bottom sheet, full width,
  flush bottom, ≤ 85% height); every detail value equals `getRows()` for that player and series;
  VORP only in its own group; empty search state names the search and Clear filters restores rows;
  built page starts with Player values hidden behind the loading card; with the engine script served
  empty the failure card shows with Try again and no tab or number. `test_guard_fails_on_broken_builds`
  fails on 4 mutations (groups not split, failure leaves values visible, empty state never drawn,
  no bottom sheet CSS).
- `tests.test_espn_zero_badge_render` (drawer note) and the other v2 render tests still pass.
- Screenshots of the sheet (390), empty state (390) and failure card (1440) reviewed by eye.

## Claimed, not confirmed

- Layout matches frames 13/14/18: not checked (figma.com blocked from this cloud session).
- The failure card waits up to 30 seconds (the existing engine timeout) before showing on a hang;
  an engine error message shows it immediately.
