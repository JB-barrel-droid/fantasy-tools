## 2026-10-16 - JEG-565: front-end default roster (K/DEF, 7 bench) and Tier column

### Changed

- curve-widget.js: DEFAULT_ROSTER K 1 / DST 1 (engine key stays DST, shown as DEF), bounds 0-3. They feed no value (JEG-298 / JEG-211 still hold; the legacy chart panel is untouched).
- v2.js: K and DEF steppers in Edit league, roster line names them, copy explains bench slots as how many players real leagues roster; Tier column and drawer heading "ESPN Tier" -> "Tier" (tierFor already used engine zones since JEG-503; the old label was wrong for non-ESPN series).
- feature-contract GL-28 (GL-25/GL-26 were already taken in the repo by JEG-609 / JEG-490, so the new line is GL-28; the Doc's GL-25/26 need a renumber or merge).
- test_v2_panels_render check_league: first-load roster and roster line, K/DEF steppers reach the engine on Apply, each row's tier equals its rank against getZones(); mutations "no K and DEF steppers" and "Tier column says ESPN Tier".
- Share links unchanged (K/DEF carry no value).

### Verified

- test_v2_panels_render panels_drive on a clean tree after make sync: only the four known failures remain (same as origin/main: row height, From/To, cbs week 6, 1366 row height); no league or tier errors.

### Not verified

- Guard-mutation test not re-run end to end after the final edit; full render suites not run (value lanes in flux).
- A dirty WIP commit from test runs rewrote dist freshness files; rebuilt the branch from origin/main and ran make sync instead.
