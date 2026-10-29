## 2026-10-28 - "Market supported" never appears on the real page (JEG-1187, session:be)

Contract: name why the Market supported fit label is 0 on the real Find a trade page while the synthetic league gives
about 46%, re-measured on main after JEG-1129 (#960), and fix it with a test that fails without the fix.

### Root cause
- `tradeFit` (`app/v2/finder.js`) labelled a trade Market supported only when the other team's Trade chart average
  change cleared its **noise floor**: `theirNet > theirTau`, where `theirTau = max(0.05, 1 x sqrt(sum over moving
  players of the standard error of the compared charts))`.
- On real charts that floor is out of reach. The three compared charts (CBS is held in the pinned build) disagree by
  around 10 points on one player (a top RB at 40 / 70 / 50 Indexed), so `theirTau` is 2.7 to 12 points per trade
  (median about 3.7). The finder only lists trades you win on DDF Value (the Adjusted chart average) and that every
  compared chart prices as a break-even or better for them, so what is left for the other team on the Indexed average,
  after starters and bench weight, is under 4.5 points. Across every fixture team measured, the best ratio of their
  gain to their floor was 0.99; no trade cleared it.
- The synthetic rows in `tests/node/fit_diagnostic.cjs` give each chart only plus or minus 10% around one market value
  per player, so the floor there is small and Market supported shows up (86 of 189).
- Jeremy's words (JEG-1108, 2026-10-25): market supported means "the indexed (non adj) trade charts are telling the
  opposing manager this is favorable". The noise floor was his answer to a different question, how much loss is
  "within reason" on their side of Natural fit. Using it as the bar for "favorable" was an implementation choice,
  and the same choice on your side was reversed on 2026-10-26 for the same reason (6 of 89 trades cleared it).
- The old Force text showed the contradiction: "The trade charts do not favor them (+0.6)".

### Fix
- `marketSupported = theirNet > NET_FLOOR` (0.05, the smallest change the page shows as non-zero). Natural's
  their-side tolerance (`theirOk = theirNet >= -theirTau`) and every other threshold are unchanged. The connector
  (#966, `supabase/functions/mcp/fit.ts`) calls the page's `tradeFit`, so it picks the rule up without an edit.

### Verified (check named)
- `python3 -m unittest tests.test_v2_finder_fit`: new test 14 (their gain +0.6 inside a noise floor of 8.2, your
  total down: Market supported, text "favor them (+0.6)") and test 15 (their gain +0.03: Force). Test 14 fails on
  origin/main's `finder.js` (label force; checked by running `check()` on the main file). New mutants "market needs the
  noise floor" (caught by 14) and "market needs no gain" (caught by 15) fail the checks.
- `python3 -m unittest tests.test_v2_finder_trifit tests.test_v2_finder_balance tests.test_v2_finder_import
  tests.test_v2_league_units tests.test_v2_copy_names`: pass.
- `node tests/node/fit_diagnostic.cjs --assert` (synthetic, 189 opportunities): Natural 61 -> 61, Market supported
  86 -> 94, Force 42 -> 34; assertions pass.
- Real engine values without a browser (Chromium is not available in this sandbox): `value-model.js`
  `runValuePipeline` on the committed dist (PPR, 12 teams, clock pinned to week 7, `tests/_holds.with_pinned_holds`
  so CBS is held as in the render build), then the real `opportunities.runAll` / `tradeFit` on the league fixtures.
  Before reproduces the page's 0 Market supported; opportunities and Natural are close to the 10-27 page read
  (4team: 8 / 4 here, 7 / 4 on the page):

  | League | You | Opportunities | Natural | Market supported before -> after | Force before -> after |
  |---|---|---|---|---|---|
  | 20team | 0 | 84 | 6 | 0 -> 23 | 78 -> 55 |
  | 20team | 3 | 108 | 21 | 0 -> 20 | 87 -> 67 |
  | 20team | 7 | 8 | 0 | 0 -> 4 | 8 -> 4 |
  | 4team | fixture | 8 | 4 | 0 -> 1 | 4 -> 3 |

### Claimed, not confirmed
- The real-page numbers through `tools/fit_distribution_page.py` after the fix: needs Chromium; the PR's preview
  render shards run the fit render tests, not this tool.
- `tests.test_v2_finder_groups` and `tests.test_v2_finder_search_unchanged` fail on origin/main as well as on this
  branch (search golden mismatch, unrelated to the fit label); not touched here.
