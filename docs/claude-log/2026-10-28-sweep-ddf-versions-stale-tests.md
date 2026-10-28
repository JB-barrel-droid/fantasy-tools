## 2026-10-28 - Render sweep: two stale DDF Value version tests

Contract: get `test_v2_ddf_versions_render.test_versions_follow_the_engine` and
`test_v2_customize_pages_render.test_customize_on_every_page` green on main by
naming each root cause. Both are tests left behind by decided product changes;
no app code changed.

### Root causes
- ddf_versions, "[1440px] Targets' our value offers []": `check_pickers` went to
  `#targets`, which was never a route (the route is `#trade-targets`). It reached
  Trade targets only because an unknown hash landed there (JEG-913, 8b822775,
  `DEFAULT_ROUTE = "#trade-targets"`). JEG-1106 (Jeremy, 2026-10-25: land on the
  value chart; commit 9cffc5cb, part of PR "Find a trade: two screens ...")
  set `DEFAULT_ROUTE = "#player-values"`, so the test stayed on Player values
  and `#v2TOurs` was never filled. Fix: go to `#trade-targets`.
- customize_pages, "[values|targets|risers|compare] Customize lists ...;
  every dataset is [... 'ddf_value_charts' ...]": the test takes "every
  dataset" from `getSourceInfo({includeComposite: true})`, which lists all
  three DDF ids. JEG-863 (f72c8ff0, 2026-10-23) hid the duplicate DDF id from
  every picker, Customize included (`ddfPickKey(item.key) === item.key`), and
  JEG-1073 (679fa54e, Jeremy 2026-10-25: "Keep adj trade chart avg as the main
  ddf and projections as an alt") moved `sameAs` to `ddf_value_charts`. That
  PR updated the contract test's GL-07/GL-09 and ddf_versions for the hidden
  id, but not this test. Fix: drop the hidden duplicate from the expected set
  and fail if Customize lists it.

### Verified (check named)
- `git log -S` on `app/v2/v2.js` for `DEFAULT_ROUTE` and
  `ddfPickKey(item.key) === item.key` gives the commits above.
- `#targets` is in no route table (`viewFor`, `LEGACY_ROUTES`) on main; it
  appears in no other test.
- Targets' `#v2TOurs` is built from `TT.ourChoices` (all `OUR_KEYS` minus the
  hidden id), not from Customize, so on `#trade-targets` it offers
  `ddf_value` and `ddf_value_projections`.
- Mutation anchors of both guard tests still match `app/v2/v2.js` once each
  (grep -cF).
- Both files compile (`python3 -m py_compile`).

### Claimed, not confirmed
- The two render tests were not run: Chromium is not installed in this
  environment. They need the render sweep or a machine with Playwright.
- Not touched: `test_v2_customize_cleanup_render` (also red in the
  2026-10-26 shard run) and `docs/feature-contract.md` GL-07/GL-09, which still
  say "three versions"; the contract test already pins two pickable versions.
