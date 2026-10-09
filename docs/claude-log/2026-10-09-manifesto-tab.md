## 2026-10-09 - v2 Manifesto tab

Contract: add Jeremy's "Fantasy Football Manifesto" to v2 as a long-form "Manifesto" tab at `#manifesto`, first in the nav, wording verbatim, landing tab unchanged (Trade targets).

### Verified (check named)
- Text is verbatim: a one-off script compared every p / h1 / h2 / li in `#v2Manifesto` (minus the eyebrow) with the doc's lines (`**` and list / heading markers stripped): 129 of 129 blocks equal; 20 bold spans = 20 `**` pairs.
- Manifesto is first in the nav, routes at `#manifesto`, hides every other tab's page, the league bar and the Showing bar; landing with no hash is still Trade targets; h1 + eyebrow; 12 section h2s in order; no "Vegas" / "VORP"; no page errors; no overflow at 390: `tests.test_v2_manifesto_render` (OK), no links, buttons or form controls on the tab; it fails on 4 broken builds (section 7 dropped, Manifesto not first, a link added to the text, Manifesto as landing).
- Nav order and the six short tabs on one row at 390: `tests.test_v2_nav_render` (OK).
- Contrast on the tab, light and dark, 1440 and 390: `tests.test_v2_a11y_render` with "manifesto" added to its tabs (OK).
- Manual Playwright run: the page shows before the engine is ready (loading card hidden).
- Simplified to plain text on Jeremy's request before shipping: the contents list and the three "See it in the tool" links were removed.

### Claimed, not confirmed
- The page also shows when the engine fails (`showFailure` calls `applyStatic()`); not exercised by a test.
- Dark-mode look was checked only by the a11y contrast sweep, not by eye.

### Known, not ours
- `tests.test_v2_targets_render` fails one deliberately broken build ("waiver rule removed" not caught). Known on main: JEG-482's pure rescale removed chart values at or below 0, so the mutation has nothing to catch. The Trade targets agent is fixing it. The test's main check passes.
