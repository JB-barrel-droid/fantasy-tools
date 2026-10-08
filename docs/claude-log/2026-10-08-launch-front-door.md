# 2026-10-08 launch front door (branch feat/launch-front-door)

Jeremy's launch decisions (2026-10-08), implemented on top of origin/main
ba3b812. No value math touched; no app/v2 UI file edited.

## What changed

1. **v2 is the front door.** `make sync` now writes the chart dashboard to
   `dist/classic/index.html` (with `<base href="../">`, canonical to
   `/fantasy-tools/classic/`, `noindex, follow`, and the one in-page
   `href="#weightsSection"` rewritten to `classic/#weightsSection` so the base
   does not send it to the root). `pipelines/build_v2_page.py` reads that page
   and writes the v2 page twice:
   - `dist/index.html` (root): no `<base>`, the shell's `v2/#view` hrefs
     rewritten to `#view`, plus a small click shim so links v2.js builds at
     runtime as `v2/#view` stay on the page.
   - `dist/v2/index.html`: as before (`<base href="../">`), for existing
     `/v2/` and `/v2/#view` links.
   Both carry v2's own title, meta description, og tags, `og:url` and a
   canonical to `https://jb-barrel-droid.github.io/fantasy-tools/`; the
   classic base/canonical/noindex are stripped so they cannot leak in.
   Chose serving v2 at the root over a redirect page: no hop, no flash, and
   /v2/ keeps working as a duplicate whose canonical names the root.
   Classic is noindex so searches land on the front door, not the secondary
   chart view; its canonical names itself so it never claims the root.
2. **Dashboard health box hidden**: `hidden` on `.health-cluster` (plus a CSS
   rule so nothing can override it). Its buttons, dialogs and the scripts that
   fill them are unchanged and still run.
3. **Monitor pages unlinked**: no public page linked `modules/*` already; the
   new test pins that (source scan of every public page plus the rendered
   root, /v2/, /classic/, retired pages and 404).
4. **Chart build stamp in the footer**: `#asOfDate` moved next to
   `#buildStamp`. The "Source content: Week N / k of 10 on an older week" item
   stays in the header (freshness labelling is user-facing).
5. **Title branded** "Trade Value · Data Driven Football" on the main page.
   `tests/test_static_export.py::test_dashboard_copy_does_not_surface_old_branding`
   pinned "Trade Value Dashboard" and forbade the brand name: changed because
   Jeremy changed the rule (GAP-BRAND-TITLE-TEST), not to go green.

Tests and gates that loaded the chart dashboard at the dist root now load
`/classic/`: `tests/rendered_gate/gate.mjs`, `gate_flexibility.mjs`,
`bench_share_readout_harness.mjs`, `test_main_table_engine_parity`,
`test_week_history`, `test_below_leg_zero_render`,
`test_espn_zero_badge_render`; `test_v2_how_render` rebuilds v2 from
`dist/classic/index.html`. `dist/classic/` is gitignored like `dist/v2/`.

## Verified

- `make sync` then `CHROMIUM_PATH=<system Chrome> make validate`: exit 0 (the new test ran, not
  skipped; test_two_tier_frontend has 7 skips of its own).
- `node tests/rendered_gate/gate.mjs dist` (12/12 shapes, 0 page errors, pie
  check and self-test pass), `bench_share_readout_harness.mjs dist`,
  `gate_flexibility.mjs dist`: all exit 0 against /classic/.
- `tests/test_launch_front_door.py`: 7 tests pass. The rendered test serves
  dist/ under `/fantasy-tools/` with dist/404.html for misses and checks:
  root shows v2 with no page errors, branded title, canonical = root; a tab
  click stays on the root URL; a runtime `v2/#compare-trade` link switches to
  Compare a trade without reloading; `/v2/` and `/v2/#trade-targets` load
  (200, no errors, right view, canonical = root); `/classic/` shows the
  dashboard with `getAllRows()` identical to the root v2 engine's, health box
  not visible, footer reads "Chart build … · Build tv-…", the weights link
  stays on /classic/, no `modules/` links; waiver-dashboard, weekly-signals
  and a missing URL (404) all link back to the root.
- Negative checks: on an origin/main worktree the test errors
  (`classic_page_html` missing; rendered part skips, no dist/classic). With
  the root click shim removed from the build, the rendered test fails
  (URL went to `/v2/#compare-trade`). The static helpers reject the old
  header/footer markup and a `modules/status.html` link.

## Claimed, not verified

- That GitHub Pages serves `/fantasy-tools/classic/` from `classic/index.html`
  exactly as the local server does (standard Pages behaviour; check after
  merge).
- Search engines honouring the canonical on /v2/ and noindex on /classic/.

## For the front-end session (app/v2)

- `v2.js` builds `open.href = "v2/#compare-trade"` and shell.html uses
  `v2/#view` hrefs. The build rewrites the shell hrefs and shims the runtime
  link at the root (V2-ROOT-RUNTIME-LINKS); switching to hash-only behaviour
  lets the shim go.
- v2 render tests that build into a temp dist call `build_v2_page.build(dist)`;
  it now reads `dist/classic/index.html` and also writes `dist/index.html`.
  Code that passes the chart page to `build_v2_html` must use the classic page,
  not `dist/index.html` (which is now v2).
- v2 shows no build stamp of its own (the engine's `#buildStamp` is inside the
  off-screen legacy container, which is what live.mjs reads).
