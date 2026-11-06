## 2026-11-06 - Private /next/ preview of the redesigned pages (part of JEG-1534)

Contract: publish the redesign wireframes (ddf-handoff `03-built-site`) from the same Pages build at
`/fantasy-tools/next/`, noindex and unlinked, without changing any live route. Local branch only;
not pushed (Jeremy: "Prepare a preview path, no PR yet", 2026-11-06).

Changes: `app/next/` (verbatim copy of `03-built-site` minus `assets/doc*`, `assets/mascot-trust-me`,
`link-fixture.html`); `pipelines/build_next_preview.py` (copy to `dist/next/`, add robots noindex,
site icon, `?v=<build tag>` on own js/css); one call in `sync_dashboard_artifacts.py`; `dist/next/`
gitignored; `tests/test_next_preview.py` wired into test-core and shard 5.

### Verified (check named)
- `python3 -m unittest tests.test_next_preview`: 3 tests OK.
- `make sync` (Python 3.12) builds `dist/next/` (27 top-level entries, 81 files) with build tag stamped.
- `python3 -m unittest tests.test_launch_front_door`: 12 OK with `dist/next/` present.
- `python3 -m unittest tests.test_validate_shards tests.test_preview_workflow_matches_pages tests.test_render_sweep_coverage`: 60 OK.
- `pipelines/dist_manifest.py compare` of a main `make sync` vs this branch: only `next/*` added;
  the 6 other differing files differ only in wall-clock `generated_at` / prior-report fields.
- Playwright (Chrome channel) against a Pages-like server (`/fantasy-tools/` prefix, 404.html):
  16 pages x 1440/390 x no league/`#s=` league = 64 views, 0 console errors, 0 page errors,
  0 failed same-host requests, 0 requests outside `/fantasy-tools/`, 0 horizontal overflow, noindex on
  every page; 21 same-host link targets all 200; LINK-FORMAT 6.1 vector via connect.html lands on
  `next/build.html` with overrides, basis and position weights stored; an `app_url` built by the
  handoff mcp `state.ts appUrl` with `DDF_APP_ORIGIN=<preview>/next` opens `next/team.html` showing the
  imported 8-team Superflex league with "Not priced yet"; check/trade/compare redirects stay in `/next/`.

### Claimed, not confirmed
- The CI rendered gate (`tests/rendered_gate/gate.mjs`) and full `make validate` were not run locally;
  the live files are byte-identical apart from timestamps, so they are expected to behave as on main.
- GitHub Pages serves `/next/` the same as the local Pages-like server (not deployed).
