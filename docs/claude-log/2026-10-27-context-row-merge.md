## 2026-10-27 - JEG-1119 merge wave (PR #959): context row, terminology, h1s, playoff hide

Contract: get PR #959 mergeable: merge main in, fix drift, check the layout at 390 and 1280 px, and fix it in scope if broken.

### Verified (check named)
- Main merged in (merge commit, no rebase). Conflicts in `app/v2/shell.html` and `app/v2/v2.js`: kept main's short freshness label and the league-wide finder page; dropped the removed `#v2Methods` bar.
- The PR's layout was broken (headless Chromium screenshots of the built page, `#player-values`, `#compare-trade`, `#waivers`): at 390 px the league name, the basis and freshness had zero width, Copy/Paste were clipped off screen, and the row was 287 px tall. At 1280 px the basis had zero width and the season notice was white text on white. After the fix: no horizontal scroll at either width. At 1280 px it is one 48 px row. At 390 px it is three short rows: league; Edit league, Customize, Week, ⋯; basis.
- ⋯ menu (same harness): it opens with focus on Position weights and lists Position weights, Copy and Paste. Picking Position weights closes the menu and opens the panel, and Escape returns focus to ⋯. No page errors at 390 or 1280.
- `#v2League` was removed but `inputs-status.js` and `overrides.js` still hosted on it, so the inputs note and the "Overrides active" bar had vanished. Both now attach to the context row.
- Render tests run locally (results in the PR comment): the contract test, the waterfall test, the tests the PR touched, and the phone, nav and a11y tests in `make test-core`.

### Claimed, not confirmed
- CI `v2-render` and `preview` results: see the PR checks.
- The sticky context row at 1024–1439 px was not screenshotted. Only 390 and 1280 were.
