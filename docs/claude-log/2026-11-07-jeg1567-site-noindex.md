## 2026-11-07 - JEG-1567 Site-wide noindex

Contract (Jeremy, via lead, 2026-11-07): add a robots noindex to every published page so search engines skip the
site while it stays reachable by link, because source-data permissions are still being settled and the link is
going out by email. Reversible with one line.

Change
- `pipelines/site_noindex.py`: `SITE_NOINDEX = True` and `apply_site_noindex(dist)`. `make sync` calls it as its last
  step (after value-logic is written), so it covers every `*.html` under `dist/` from one place. Pages that already
  carry noindex keep it; an indexable robots meta would be replaced; a page with no head fails the build.
- No page source, title, link or visible text changed. `learn/posts/manifesto.md` is untouched.
- Reverse: set `SITE_NOINDEX = False`, run `make sync`. Noted in AGENTS.md and README.md.
- robots.txt is not an option: this site is a Pages project path (`/fantasy-tools/`), and crawlers read robots.txt
  only from `datadrivenfootball.github.io/robots.txt`, outside this repo. No user-site repo was created.
- Not covered: non-HTML files (`learn/posts/*.md`, JSON, `llms.txt`, the skill zip) cannot carry a meta tag and
  Pages cannot send an X-Robots-Tag header. Learn posts render inside `learn.html`, which is noindex, and no page
  links the .md files as pages. A direct .md URL could still be indexed in principle.
- Learn posts and research: this build publishes no separate HTML for them (Learn is one page, `learn.html`).
  The research draft PR (#1352) is not on main; any HTML it adds is covered automatically once merged.

### Verified (check named)
- `python3 -m unittest tests.test_site_noindex` (7 tests): injector adds once, idempotent, changes nothing else;
  `SITE_NOINDEX` is the only switch (False writes nothing, True marks every html); built `dist/` check that every
  HTML file has a noindex robots meta (15 marked by this step, 26 already had it, 41 total on a local sync).
- A/B with the switch off: `make sync` marks 0 files and `dist/values.html` has no robots meta.
- Get-values reads `players-data` from `dist/index.html` by regex: the island still matches after the change.
  `tests.test_endpoint_parity`, `test_get_values_value_context`, `test_mcp_remote`, `test_jeg_1061_logging_contract`
  give the same result with the switch on and off locally (1 failure, 6 errors both ways: week-parity and
  value-context parity, unrelated to the meta; CI is the authority).
- `tests.test_validate_shards`, `test_build_root_pages`, `test_next_preview`, `test_published_surfaces` pass.

### Claimed, not confirmed
- `make validate` and the rendered gate were not run to completion locally (local `npm ci` for the gate is missing
  and local Python data differs); CI on the PR is the check.
- Live result (meta present on root, values, learn, build; `verify_live.py`) is pending the deploy.
