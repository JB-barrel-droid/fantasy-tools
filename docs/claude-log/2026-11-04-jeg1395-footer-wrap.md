## JEG-1395 shared explainer footer correction for PR #1296

Bounded handoff from the existing explainer owner. JEG-1395 remains owned by this Codex lane; its latest ticket comments and PR #1289 head were reconciled before changes. Open PR file/patch checks found no competing footer metadata edit. The #1296 owner retains its branch and promotion responsibility.

### Reproduction and cause

- Isolated worktree/branch `codex/JEG-1395-footer-wrap` starts at #1296 head `8d6030e490dcae53face5ac06d1ea8f71687547f`, without #1289's arithmetic delta. Its template blob is `60e61ed21cad7c84c656eecef360450f2946a6f9`.
- The original `test_frame_mirrors_the_tokens_in_both_themes_and_widths` fails at 390px in both themes, with 3px horizontal overflow locally; 1280px passes. CI's reported 36px is not reproduced exactly in this environment (Playwright 1.62.0, system Chromium 151.0.7922.173).
- The actual built merge subject contains full SHA `d7881b1c105f33a51caecba74e76326987f802eb`. At 390px, frame width is 324px and its provenance paragraph grows to 318.765625px instead of the available 308px. Replacing only that subject with short text, or applying only `overflow-wrap: anywhere` to that paragraph, reduces frame overflow from 3px to 0 and paragraph width to 308px in both themes. This isolates the long subject's contribution to grid minimum sizing.

### Change and validation

- One footer-paragraph CSS rule permits long words to wrap. Existing layout, subject text, provenance rendering, value math and arithmetic are unchanged.
- Regression intercepts the locally served embedded metadata before the real renderer runs and supplies the full merge subject, independent of HEAD's future subject. It checks the complete rendered subject, paragraph and iframe overflow, and page errors at 390/1280px in light/dark themes. All original assertions remain intact.
- Before CSS change: the new regression fails both 390px subcases (3px overflow); desktop subcases pass. Baseline registry does not list this failure; the wrapper labels it new red.
- After CSS change: `CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 -m pipelines.baseline_reds --context local -- python3 -m unittest tests.test_jeg1140_explainer_fieldnotes_render` passes all 7 tests, no skips, in 34.436s. Both original responsive checks and the injected-subject regression pass all four theme/width combinations. `git diff --check` passes.
- Receipts: `/tmp/jeg1395-footer-before.log`, `/tmp/jeg1395-footer-regression-before.log`, `/tmp/jeg1395-footer-after.log`. Generated build output is excluded from the commit.

### Integration boundary

Hand off only this isolated correction commit to #1296's owner; do not merge this branch or combine #1289's feature. Original #1289 head `996306920fcc5a677be41d8b0bdabbfd26e58a8e`, its template, risk-register entries and separate JEG-1398 wording patch remain intact. No builder/engine/value inputs, risk-register edits, raw-log retry, broad suite duplication, PR readiness transition, merge, deployment, Supabase operation or deletion. Integration-head CI and the owning lane's required independent review remain gates.
