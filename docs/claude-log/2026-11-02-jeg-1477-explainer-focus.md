## 2026-11-02 - Explainer focus readiness (JEG-1477)

Contract: diagnose the settings-render outline failure, retain the 3px focus contract, and open a ready PR on `claude/JEG-1477`. No merge or deploy; HANDOFF.md is unchanged.

### Verified (check named)

- Fresh worktree from `origin/main` at `b7dbd3621`. The requested `RENDER_TESTS_REQUIRED=1 .venv/bin/python -m unittest tests.test_jeg1140_explainer_fieldnotes_render` passed all five original tests with local Playwright 1.63.0. The five original tests also passed with isolated Playwright 1.49.1 / Chromium 131 (the settings workflow's version); its headless shell passed the focused original test too. The unmodified failure is timing dependent on this Mac.
- A Playwright probe holding `assets/comparison-sources-data.json` reproduced the exact failure on main: `#v2How` remained hidden, the frame had zero client rects, `a.focus()` left `contentDocument.activeElement` on BODY, `:focus` and `:focus-visible` were false, and outline width/style were `0px`/`none`. The Fieldnotes focus token was correctly `#175BC1`. Releasing the request and waiting for the section made the same link focusable with a solid 3px outline. This is a test readiness race, not a CSS override.
- `git bisect start b7dbd3621 fbb017a1` requested their merge base `302354fb6`. Endpoint validation with the same held-request probe also reproduced the failure on supposedly good `fbb017a1`; marking that endpoint bad produced `was both good and bad`. Reset the bisect. Thus the supplied CI-pass/CI-fail boundary cannot identify a new breaking commit. `git log` / `git show` trace the faulty helper to `b2809cd328b168e015421842cefb0edec7006ece` (#1229): it waited only for attachment and forced the iframe to load before the application revealed the section. Neither the bot commit `1c04d6fa` nor #1217 introduced that helper.
- New `test_focus_ring_with_delayed_engine`, before the readiness fix: FAIL, `{'focused': False, 'width': '0px'}`. It delays only the engine-data fetch by 1500ms. After the fix, the explainer module passes 6 tests with `RENDER_TESTS_REQUIRED=1 /tmp/jeg1477-playwright149/bin/python -m unittest tests.test_jeg1140_explainer_fieldnotes_render`. The original 3px assertion remains unchanged; the regression additionally requires actual link focus.
- Remaining settings workflow modules: `RENDER_TESTS_REQUIRED=1 /tmp/jeg1477-playwright149/bin/python -m unittest tests.test_jeg1140_settings_fieldnotes tests.test_jeg1140_settings_fieldnotes_render` passes 28 tests. Render runs were sequential; test harnesses close their browsers. `pgrep -fl 'make validate'` found no active validation.
- `RENDER_TESTS_REQUIRED=1 /tmp/jeg1477-playwright149/bin/python -m unittest tests.test_v2_contract_render` passes all 6 tests (including mutation guards) in 483 seconds.
- `git diff --check` passes. No application CSS, value math, fixtures, workflow, Supabase or credentials changed. F1 is inapplicable: this changes browser-test readiness only.

### Claimed, not confirmed

- Exact-head GitHub settings-render, preview and v2-render results remain to be read after pushing. Broad local `make validate` is deferred to CI to honor the requested narrow render scope and Mac memory constraint.
- A separate job must independently review the pushed head. Nothing has been merged, deployed or checked on production.
