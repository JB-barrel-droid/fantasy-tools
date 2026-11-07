## 2026-11-07 - JEG-1539 Workspace swap and the new front door (plan step 5 of JEG-1534)

Contract: put the workspace pages (team, explore, partners, find, waivers, settings, ai, compare stub) and the
redesigned index.html on the live root, wired to the live engine; retire the v2 shell and the Simplified site;
every old hash route redirects; remove the swap steps' `?swapped=1` automation escape and move the old-route tests
to the new mechanism. Lane logs: `2026-11-06-jeg1539-lane-team.md` (DDF.league, tiers), `2026-11-06-jeg1539-lane-find.md`
(Finder and Waivers).

What changed
- `pipelines/build_root_pages.py`: the pages above at the root; a page gets the engine when its source has the
  `<!-- ddf-engine -->` marker (values/learn/build must). `legacy-routes.js` is copied as is (it is the redirect map).
- `pipelines/build_v2_page.py`: the v2 shell is build-only (`build/v2/index.html`, never published, like the engine
  page since JEG-453); `dist/v2/index.html` is a stub that runs `legacy-routes.js`; `dist/index.html` is the new front
  door. `tests/_dist_server.py` and `tests/rendered_gate/engine_page.mjs` serve the shell at `/v2-app.html`, so the
  v2 render suites, value_check and the rendered gate keep their numbers.
- `app/next/legacy-routes.js` (first script in the front door's head, and on the /v2/ stub): every v2 route to its
  page, query carried (`values.html#?valuecontext=..`, `build.html#?give=..`), `#s=` to connect.html, the retired
  `#simplified-site` to the front door. Links that carry rosters (mine=, theirs=, target=, `#find-league?workspace=`,
  i.e. chat site_url and ddf-assist links) become a `#s=` league link through `DDF.link.encode` on build / find /
  values Buy / Sell. Not carried: `tc` (carried trade) and the league finder's own filters (size, fit, opp, mcap, mch,
  trade).
- `app/v2/v2.js`: SWAPPED_ROUTES, COMPARE_STAYS and the `?swapped=1` escape removed (the redirects live in
  legacy-routes.js; the build-only shell keeps every view for its suites).
- `app/next/site.js`: the nav counts a pasted or saved league on every page.
- Pages (lanes): `ddf-league.js` (DDF.league), team / explore / partners / settings, `find-engine.js`,
  `find-page.js`, `waivers-page.js`; sample data removed.

Durable notes
- Local `make sync` rewrites committed artifacts under `dist/` and `app/trade-value-chart/` from local inputs;
  restore them (`git checkout -- dist app/trade-value-chart`) before committing, then `make sync` again before
  testing (otherwise every DDF Value reads missing).
- The root build's link rewrite (`rewrite_links`) also runs over copied `.js`; a JS string containing `\"` breaks.

### Verified (check named)
(filled in below as each check runs on the PR head)

### Claimed, not confirmed
- CI (`make validate`, test-core shards, rendered gate) on the PR head: see the PR checks.
- Live behaviour after deploy: pending `verify_live.py` and a live Playwright pass (recorded on JEG-1539).
