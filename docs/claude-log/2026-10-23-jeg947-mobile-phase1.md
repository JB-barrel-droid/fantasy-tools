## 2026-10-23 - JEG-947 mobile phase 1 (part of JEG-927)

Scope: scrolling tables with pinned name column and edge fade (Jeremy decision B1, 2026-10-23), 44 px tap targets, hover rules
under `@media (hover: hover)` with touch equivalents, 12 px minimum body text on phones. Chart and nav untouched (later phases).
Changes: `app/v2/v2.css` (touch rules apply below 768 px and on coarse pointers; desktop rules unchanged),
`tests/test_v2_mobile_phase1_render.py` (new). Merged origin/main (plain merge, no conflicts).

### Verified (named checks)
- `tests.test_v2_mobile_phase1_render.test_phase1_guards_hold`: OK before and after the merge (overflow at 320/360/390, scroll container + sticky first column + fade cue, 44 px hit areas incl. 844x390, no unguarded :hover, 12 px text, desktop 1366/1280/1024 unaffected).
- `test_guard_fails_on_broken_builds`: OK; 11 simulated broken builds each reported an error.
- Screenshots 390/360/320 and 1366x768 in `~/code/fantasy-tools-selfhost-notes/mobile-phase1/`.

### Not verified
- Real-phone behavior (iOS Safari sticky + mask, momentum scroll). Chromium emulation only.
- Full `make validate` not run (value lanes in flux; only the new render file run).
- CSS scroll-driven fade needs `animation-timeline`; browsers without it show no fade (table still scrolls).
- Name column is narrow when pinned, so long names clip at 390 px.
