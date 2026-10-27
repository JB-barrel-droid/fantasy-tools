## 2026-10-25 - Nav overflow in CI's fallback face (part of JEG-1056, PR #918)

Contract: find why the clean build failed `tests.test_v2_waterfall_render` in the v2-render workflow only ("[1100x900] horizontal overflow 37px"; 113 px at 1024), and fix it in `app/v2/v2.css` with a test that fails without the fix.

Cause: head ed5104aa described a `.v2-tabs` CSS change but committed only the test, so CI ran the old rule. The rule itself is the culprit: `.v2-tabs { flex: 1 0 auto }` never shrinks. Without Inter (CI resolves `Inter, system-ui, sans-serif` to DejaVu Sans; the hermetic browser blocks Google Fonts) the eight tabs are 872 px, the freshness button is already at its 12 px minimum, and the page scrolls sideways. The plain shrink the earlier agent proposed would have broken JEG-675 (with Inter at 1366/1440 the tabs shrank and scrolled while the label grew). The fix lets the tabs shrink only after the label: `.v2-tabs { flex-shrink: 1; min-width: 0 }`, `.v2-freshness { flex: 0 100000 auto }`.

Reproducing CI: Playwright 1.49.1 in a scratch venv with its own Chromium 131.0.6778.33 (build 1148), and a `FONTCONFIG_FILE` that includes `/etc/fonts/fonts.conf` and rejects the Inter, JetBrains Mono, Carlito/Caladea, LibreOffice and Type1 fonts, so `fc-match sans-serif` gives DejaVu Sans. Forcing a CSS font is not the same check: the local machine's `sans-serif` is Inter.

### Verified (check named)
- Unchanged head, CI setup: WIDE FONT {1024: 113, 1100: 37, 1279: 0}, tabs 872/872, `[1100x900] horizontal overflow 37px`. These are CI's numbers exactly (run 40208576143).
- Culprit by bounding rects at 1024/1100: `nav#v2Tabs.v2-tabs` from x=243 to 1115 (872 px, flex 1 0 auto, min-width auto); `.v2-freshness` from 1125 to 1137; document scrollWidth 1137.
- After the fix, CI setup: overflow 0 at 1024/1100/1279/1280/1366/1440. With Inter: tabs and label widths match the old rule at every width that fit before (1100, 1279, 1280, 1366, 1440). Only 1024 changes, where the old rule scrolled the page 28 px.
- `tests.test_v2_waterfall_render` 4/4 OK with the CI setup, and all 9 GUARD CAUGHT lines print. The new guard catches the old rule ([1024] overflow 113px) and the plain shrink ([1279] tabs 797 of 872 px).
- `tests.test_v2_contract_render`, `tests.test_v2_phone_fallback_font_render`, `tests.test_v2_panels_render`: 11 OK with the CI setup.

- `make validate` exit 0 after merging origin/main at 9081a73f.

### Open: main's #915 breaks the Compare fold this test guards (not fixed here)
- After merging main, `test_waterfall_verdict_layout_example` fails at 1366x768. The trade sides and the verdict end at y=775 with Inter and Chromium 1248, and at y=792 with the CI setup; the fold is 768. The failure is the same with the JEG-1056 nav rule reverted, so this branch did not cause it.
- Cause: #915 (JEG-1076) adds the inputs status strip, 45 px at y=129: "These numbers use the site's default league settings (Full PPR · 12 teams) ... Edit league / Dismiss". It shows to every first-time visitor, so on main the JEG-917 promise (Compare fits on 1366x768) no longer holds for new visitors. This was measured with a script on #compare-trade.
- Not fixed here: whether the strip moves, shrinks or stays off Compare on short viewports is a front-end and product choice (inputs-status.js and v2.js belong to other lanes).

### Claimed, not confirmed
- That the ubuntu-26.04 runner's `sans-serif` is DejaVu Sans. This is inferred: the same numbers come from forcing DejaVu Sans and from the fontconfig repro. I did not read it from the runner.
- With a tab row narrower than its content, the last tabs are reached by horizontal scroll with a hidden scrollbar (the existing `overflow-x: auto; scrollbar-width: none`). That only happens at 1024 with Inter, or in a wide fallback face.

## 2026-10-25 (later) - Corrections: guard fixture, #930 merged (part of JEG-1056)

Contract: make the "verdict not DDF" guard real again, and finish #918 now that #930 (JEG-1084, the compact strip and league-row trim) is on main (1ed64422).

Corrections to the entry above:
- The "Open: #915" section is resolved by #930, not by this branch.
- On the 45 px strip, the guard lines "GUARD CAUGHT" did not all prove their mutation. Each was caught at least by the fold error the clean build already had. And "verdict not DDF" was invisible on its own: since JEG-1073, `ddf_value_charts` has the same numbers and name as `ddf_value`, so the fixture's "other" picker series was DDF Value itself.

Change (`tests/test_v2_waterfall_render.py`, commit 97abbe88):
- The fixture's picker series skips `ddf_value` and `ddf_value_charts` (same change as closed PR #929).
- The guard runs the clean build once and counts only errors whose shape (numbers masked) the clean build does not have.
- The guard is stricter; no assertion was loosened.

### Verified (check named)
- `test_guard_fails_on_broken_builds`, CI setup (Playwright 1.49.1, Chromium 131, Inter rejected by fontconfig):
  - On the old 45 px strip, and on a scratch merge with #930 before it landed, "verdict not DDF" is CAUGHT by the wrong verdict ("headline 'DDF Value (projections): you lose by −28.6' should name 'DDF Value' and say 'you lose by −13.0'").
  - With the old fixture on the #930 scratch merge it is "GUARD NOT CAUGHT: verdict not DDF (0 new errors)".
- After merging main with #930 (d6597673), `RENDER_TESTS_REQUIRED=1 python3 -m unittest -v tests.test_v2_waterfall_render tests.test_v2_contract_render` passes 10/10 with exit 0 in both setups:
  - the CI setup;
  - Inter, with system Playwright and Chromium 1248.
- All 9 mutation lines are GUARD CAUGHT in both setups.
- Compare fold measured on the clean build (bottom of the give, receive and verdict boxes):
  - CI setup: 765.66 at 1366x768 (2.34 px margin) and 853.98 at 1440x900 (46.02 px).
  - Inter: 749.47 (18.53 px) and 826.59 (73.41 px).
  - The CI-setup numbers equal #930's own.

### Claimed, not confirmed
- The 2.34 px margin at 1366x768 in the CI font is thin. One more wrapped line in the verdict, from a data rebuild, would fail the fold again. Not addressed here.
