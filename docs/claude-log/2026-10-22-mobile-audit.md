## 2026-10-22 - Mobile audit and optimization plan (JEG-927)

Audit-only pass: no app code changes. Screenshotted all 7 tabs at 4 viewports
(390x844, 360x740, 320x568, 844x390 landscape) with Playwright touch emulation.
Catalogued defects per tab, researched mobile best practices, wrote
`docs/v2-mobile-plan.md` with phased ticket breakdown and three product
decisions for Jeremy.

### Verified (check named)

- Screenshots captured for all 7 tabs x 4 viewports -- files in
  `~/code/fantasy-tools-selfhost-notes/mobile-audit/`.
- Automated audit measured tap targets, overflow, hover rules, and font sizes
  via Playwright `page.evaluate()` -- JSON results in each viewport directory.
- Code audit confirmed: main chart (v2.js) uses `mousemove`/`mouseleave` only,
  no touch handlers; curve widget canvas correctly uses `touchstart`/`touchmove`.
- Info popovers correctly gate hover behavior behind `matchMedia("(hover: hover)")`.
- iOS Safari does not support `screen.orientation.lock()` -- confirmed via
  caniuse.com and WebKit bug tracker.

### Claimed (not confirmed in app)

- The plan's phased ticket breakdown is a proposal; actual implementation
  complexity may differ once code changes begin.
- Touch target measurements are from Playwright's layout engine, not physical
  device testing.

### Linear

- Created umbrella ticket JEG-927 (Todo, session:fe-mac, project Trade Value Chart).
- No child tickets yet -- waiting for Jeremy's decisions on A/B/C in the plan doc.
