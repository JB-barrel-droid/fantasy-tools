## 2026-10-26 - Render sweep + overrides-basis render test (JEG-1135)

Contract: two checks red on main after the JEG-1093 / JEG-1106 nav work —
`tests.test_render_sweep_shards` (four render modules in no sweep shard) and
`RENDER_TESTS_REQUIRED=1 tests.test_v2_overrides_basis_render` (3 failures,
2 errors). Done when the shard test is green and each overrides-basis failure is
either fixed or explained with a recommendation.

Run by an OpenRouter deepseek-v4.1-flash session (T2 build lane; no Claude T1
review yet, so treat these edits as untrusted until a T1 pass).

### Verified (check named)
- `python -m unittest tests.test_render_sweep_shards` → OK (6 tests). The four
  orphan modules (test_v2_league_oppanel_render, test_v2_find_split_render to
  shard 1; test_v2_league_parsed_render to shard 2; test_v2_league_top10_render
  to shard 3) are added to the `test-render-sweep-*` recipes in the Makefile;
  the union of the three shards again equals `test-render-extra`. Shards are
  18/17/18 modules.
- `RENDER_TESTS_REQUIRED=1 python -m unittest tests.test_v2_overrides_basis_render`
  → 17 of 18 pass (79 s). The five original failures are gone:
  - the two `Page.fill` timeouts and the radiogroup focus failure: a blend now
    starts on our methodology (the four trade charts, `DEFAULT_SOURCES`), so a
    projection's slider is disabled until its `#v2OvOn-<key>` tick is on; the
    tests now tick ESPN on before moving it, read the first enabled slider
    (FantasyCalc), and drive the "last source stays on" guard on the remaining
    trade chart.
  - `test_all_three_projections_ticked_...`: renamed to
    `..._carries_over_as_a_blend` and re-pinned to the delivered behaviour (see
    Claimed below).
  - rubric item 6 (0 after the first fix): `set_player_override` now reads the
    editor's `#v2OvRange` max and returns the value it applied, because the
    editor clamps to its scale — top RB + 40 (87.7) clamps to 80, so the old
    `abs(bumped - (a.value + 40)) < 0.06` could never hold. Probed directly:
    applied 80, engine read back 80.
- `git status --short` clean of generated churn before each commit (dist/
  app/trade-value-chart dropped; only Makefile and the test file staged).

### Claimed, not confirmed
- Rule change: JEG-1073 (Jeremy, 2026-10-25 — our methodology is the four trade
  charts, equal weight) removed the old special case where a saved legacy blend
  with all three projections ticked migrated to our methodology *silently*. The
  code (`migrateLegacyBlend`, app/v2/overrides.js:165-181) and its comment now
  carry such a record over as a blend of what was ticked, with the one-time
  notice. `docs/feature-contract.md` states no rule either way. I treated the
  test as stale and re-pinned it to the code. If Jeremy wants the old silent
  migration back (a reader who never chose a blend should not be pinned to one),
  that is a one-line change in `migrateLegacyBlend` — flagging, not deciding.
- Layout regression, NOT fixed: `test_compare_layout_is_unchanged_at_1366x768_with_the_indicator_showing`
  still fails — `#v2Compare` top moves 215 → 283 and `#v2League` height 57 → 125
  when the indicator shows. This is a real regression, not a stale anchor: the
  bar's own code says "The indicator sits in the league row (no extra height on
  any tab)" (app/v2/overrides.js:262) and the test pins that invariant. Probed
  the row at 1366x768: with the indicator on, the row's items (league name 126 px
  + roster line + ov bar 324 px + league actions 278 px + assist actions 440 px +
  24 px gaps) exceed 1366, so `#v2AssistActions` wraps to a second line (+68 px).
  There is no room for the bar in the row: the fixed content already needs
  ~1564 px, so shrinking the bar alone would ellipsize the "Overrides active…"
  badge to a few characters. A correct fix is a design choice (a compact/short
  form for the badge, or moving the assist/Copy-Paste actions out of the league
  row), so it does not meet the ticket's "small UI fix" bar. Recommendation:
  raise a follow-up ticket (front end, layout) and let Jeremy pick the compact
  form. The test is left red on purpose; it is a true failure.
- The four newly sharded modules are placed by count (18/17/18), not by measured
  run time — the sizes in the Makefile comment's run have not been re-measured.
- No `make validate` / `make test-core` run here (out of scope: no value math,
  config, fixtures or `dist` changed).
