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

Independent review (separate Opus agent, diff only, head 7a74beea): CHANGES NEEDED, fixed in the next commit:
- a chat link's league settings were saved over the reader's own (DDF.engine.apply): now `applyVisit` (visit only);
- `tests/rendered_gate/live.mjs` (daily live synthetic) still expected the v2 tabs at / and /v2/: now renders every
  root page (200, build tag, <main> with text, no page error) and checks the old addresses redirect;
- a plain old route's league (`#risers-fallers?scoring=&teams=&roster=`, chat site_url without rosters) was ignored:
  `ddf-engine.js` applies a hash query league for the visit (`hashLeague`);
- partner tags judged lineups with a starter the charts do not list (missing counted as 0): now only complete lineups
  are tagged and partners.html shows "—" for an incomplete chart total;
- nav league check reads the active saved league only; "choose" on explore.html; a late link translation after the
  15 s fallback no longer redirects twice; build.html and compare.html added to the rendered gate's root sweep.
- Recorded, not changed: the D4 storage bridge in ddf-engine.js stays (localStorage `ddf.v2.league-settings` and
  `ddf-v2-value-overrides` are now the one persistent store for settings and overrides; the `ddf:overrides` mirror
  feeds site.js link encoding). Converted links drop league extras (weeks, bench share, injury, confidence).

Review round 2 (head 78384a1b) and round 3 (ee9dc767), same reviewer: chat league settings now apply on every engine
page in the tab (`ddf-engine.js` chatLeague, visit only); live.mjs requires 10+ players with a DDF Value on values.html
(DDF column and engine rows) and checks `#s=` lands on connect.html. Round 3: APPROVE after the DDF-column fix
(30770ea8). Open minor: a chat league stays in the tab's ddf:league until a new paste (JEG-1538 clears it then).

Merged main at c892bf97 (JEG-1538): connect.html and setup.html join ROOT_PAGES; v2.js keeps no redirect code;
test_entry_pages drops ?swapped=1 and a team view link now lands on team.html (live since this PR).

Later findings (2026-11-07):
- get-values (supabase/functions/get-values/index.ts) and the MCP tools parse the players-data island from the root
  page. The front door now carries that island alone (`DATA_ISLAND_PAGES`, about 1.1 MB inert JSON; the v2 front door
  was 1.4 MB); contract test in test_build_root_pages. Follow-up: have get-values read a data file and drop it.
- `build_v2_page.build(site=True)` (make sync only) writes the /v2/ stub and the shared build-only shell; harness copies
  (`build(tmp_dist)`, site=False) keep the shell at / and /v2/ of their copy as before, so the v2 suites run unchanged.
  `build(DIST)` without site=True raises.
- v2 suites that serve the real dist moved to /v2-app.html (lane tests); the league journey suite needed no change
  once harness copies kept /v2/.
- Final delta review (93bd70fc): APPROVE after the shared-shell fix (8bd688a2).

### Verified (check named)
- Local, head 7a74beea plus the review fixes, after `make sync` (Python 3.12, Chrome):
  `tests.test_validate_shards`, `test_build_root_pages`, `test_legacy_routes`, `test_legacy_links_state` (6 tests,
  incl. visit-only settings and the plain-route league), `test_build_swap_routes`, `test_values_swap_routes`,
  `test_learn_engine_parity`, `test_launch_front_door`, `test_team_engine_parity`, `test_find_engine_parity`,
  `test_build_page_engine_parity`, `test_values_page_engine_parity`, `test_next_preview`, `test_verify_live`,
  `test_build_v2_page`, `test_main_table_engine_parity`, `test_asset_load_retry`: OK.
- Parity: team / explore / partners (`test_team_engine_parity`) and find / waivers (`test_find_engine_parity`) equal
  independent engine and Finder reads at 3 scorings x 10/12 teams x superflex on/off; each has a drift test.
- Rendered gate `node tests/rendered_gate/gate.mjs dist`: passed (12/12 shapes, 0 page errors, 12 root pages clean).
- QA sweep (scratch `qa1539.py`, Chrome, served dist): 13 pages x 1440/390 x no league / pasted 12-team league =
  52 views, 0 console errors (Google Fonts blocked by the hermetic browser excluded), 0 page errors, 0 failed
  same-host requests, 0 horizontal overflow, 35 same-host link targets, 0 broken.
- `live.mjs` against a local Pages-like server (/fantasy-tools/ prefix): every root page and redirect passes except
  connect.html, which is JEG-1538's page and not yet on main.

### Claimed, not confirmed
- CI (`make validate`, test-core shards, rendered gate) on the PR head: see the PR checks.
- Live behaviour after deploy: pending `verify_live.py` and a live Playwright pass (recorded on JEG-1539).
