## 2026-10-22 - JEG-843 Reset to default added *_adjusted series

Root cause: `defaultShown()` in `app/v2/v2.js` (the list Customize > Reset to default returns to, `startActive`) did not filter the retired `*_adjusted` engine aliases that `applyShown`, `pageDefault` and `sourceInfoWithFreshness` already filter (JEG-626/508). Reset + Done toggled the four aliases on and `saveSelection` persisted them. Fix: `defaultShown()` skips `isEngineAlias` keys.

Verified: `tests/test_v2_ddf_render.py` now asserts Reset-to-default shown set == the fresh-profile set, and no `_adjusted` in strip, table headers or chart paths, also after loading a saved selection holding aliases. Negative test: mutation "Reset default includes retired aliases" is caught by the guard test (it failed before the fix). A second mutation (saved aliases not cleaned) was not observable because `applyShown` already drops them, so it was removed.
