## 2026-10-23 - JEG-932 Compare verdict still past the 1366x768 fold after JEG-917

- Question: was main changed after #839 (#840 roster paste, #842 label rename) or was the #839 measurement environment-dependent?
- Finding (verified): checked out #839 itself (901c023a) in a throwaway worktree; the test is red there too, verdict
  bottom 782.66 (height 520.66), identical to main 14c1f5b4. So #840/#842 did not move it. #839 logged 502px (bottom 763.9)
  in its own environment; here the same commit measures 520.7. The 18.6px difference is text wrapping in that environment
  (the hermetic browser blocks the Archivo web font, so the width of the fallback sans-serif decides wraps); not pinned
  down further. Treat the layout as font-dependent and leave slack.
- Cause of the extra height here: the three "Deal read" net chips (`.v2-deal-nets`: 216 + 389 + 251 px) wrap one per line
  because two chips plus the 20px column gap are 625px against a 617px column.
- Fix (`app/v2/v2.css`, same short-viewport media block): `.v2-deal-nets { gap: 2px 6px; margin: 2px 0; }`. Two chips share
  a row; verdict 520.7 -> 486.7px, bottom 748.7 (19px of slack). No copy changed; test and guards untouched.
- Verified: waterfall test red before, green after (2 tests, 7 subtests); 12 Compare-related v2 render files
  (waterfall, compare, compare_empty_side, deal_read, deal_read_empty_side, phone_trade_rows, phone_tap_targets,
  phone_wide_font, phone_fallback_font, offer, disagree, a11y): 22 passed, 3 skipped. Widths 1440 (bottom 860 of 900),
  1100 and 390 are inside the waterfall test; 1280x720 measured by hand: verdict 548px, still past a 720 fold as before
  (not a guarded viewport).
- Not verified: Playwright 1.49.1 (CI pin) not run locally; the six-chip row fit has ~6px of slack, so a wider font could
  wrap it again and put the verdict back near 520px.
