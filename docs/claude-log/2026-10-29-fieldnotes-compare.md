## 2026-10-29 - Compare a trade in Fieldnotes (JEG-1138, PR #1184)

Contract: put Compare a trade into the approved Fieldnotes language behind `?design=fieldnotes`, on the JEG-1137
foundation (#1143), without changing markup, copy, numbers or verdict rules. JEG-1139 reuses the value view and
disclosure styling.

### Verified (check named)
- Every verdict branch (none, win, lose, even, incomplete) renders Compare's text identically with and without the flag,
  at 390 and 1280 px: `tests.test_v2_fieldnotes_compare_render` (3 OK, local Mac, system Chrome).
- Keyboard: "Every pairing" opens and closes with Enter and a 3 px ring; "Show players" opens its row and keeps focus;
  "Copy link to this trade" puts the trade link on the clipboard. Same test.
- No sideways scroll, all controls at least 44 px, and text contrast at least 4.5:1 (3:1 large) in Compare under the
  flag. The phone verdict bar keeps its verdict edge. Same test, which also caught that bug before the push.
- The unflagged page's computed styles in Compare are unchanged, and a guard fails without the block. Same test.
- No regressions in `test_v2_fieldnotes_league_entry_render`, `test_v2_contract_render`, `test_v2_tokens` or
  `test_build_v2_page` after merging `main` `d67848c9`. `test_v2_deal_read_render`, `test_v2_share_render` and
  `test_doc_staleness` also passed before the merge.
- `test_v2_compare_render` fails identically at #1143's head `66d389c1` (optgroup label), so it's pre-existing.

### Claimed, not confirmed
- Safari, physical phones and screen readers; CI's bundled Chromium; `make validate`.
