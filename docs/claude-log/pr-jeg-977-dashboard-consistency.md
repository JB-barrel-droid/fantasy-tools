## 2026-10-25 - JEG-977: dashboard consistency fixes (front end, cloud worker)

From the dashboard consistency audit. Branch `fe/JEG-977`, built on main after #856 and #853.

### Changed

- One minus sign (U+2212) and one zero ("0.0", never "+0.0", "-0.0" or "±0.0") in the Player values
  formatter, Compare, Trade targets, Values auditing (pie and single source), league, finder, waivers
  and opportunities tables.
- One agreement phrase: "N of M charts agree" (Compare headline, Trade targets rows, finder warning).
- Finder "no trade found" note: "the one available chart says" for a single chart, "at least N of M
  charts agree" otherwise (was "1 of 1 available trade charts say").
- Reader words: "Week 7" for "W7", "Free agent" for "FA", "Prior week change" for the "Δ Prior week"
  button and "Change" in the notes. "Arbitrage" is gone (Compare read title and the weight headline).
  The vanity counts "24 of 732 players" and "Show more players (50 of 732)" are gone.
- No external-link arrow on in-app links (Open Compare a trade, How values work, the How page links,
  the player tooltip hint). Links that open another site keep it.
- Trade targets sign convention: the figure beside Market consensus is now market minus ours, the same
  sign as Gap (was "▼ 3.3 below" beside Gap "+3.3"). Chosen as the less invasive option: one display
  string changes and the engine's Gap is untouched. Market consensus is the middle value (median) of
  the compared charts; Trade chart average is their mean; the footnote says so.

### Not changed

- The Δ glyph stays inside the narrow table cells (several render tests pin the cell text); it is
  explained in words wherever prose uses it.
- No engine, bench share, nav or chart code.

### Verified (named checks, run one at a time)

- New `tests.test_v2_consistency_render` (3 tests): passes on the build; each of 6 simulated broken
  builds (hyphen minus, signed zero, "trade charts agree", "W7", arrow on an in-app link, opposite-sign
  market difference) and the old finder wording is caught.
- `tests.test_v2_targets_render` (market difference check and its mutation updated to the new sign).
- Run again after the change, unchanged and green: audit, audit_source, nav, risers, ddf, deal_read,
  expand, finder, finder_paste, league_tables, values_tab_ux, how, a11y_batch1, advanced, waivers, compare, polish, plain_copy, panels,
  phone_layout, contract. Unit: test_v2_finder, deal_read(+chart_avg, split), headlines, audit_pie, compare, movers.
- Assertions changed because Jeremy's brief changed the rule they pin (not loosened): the Arbitrage
  title (deal_read tests), "trade charts agree" (compare render), hyphen minus and "+0.0%" (polish render),
  market difference text (targets render).

### Pre-existing failures, same on a clean origin/main worktree

- `test_v2_targets_render`: 1024x768 horizontal overflow 28px.
- `test_v2_waterfall_render` mutation "no wide verdict column on short viewports" is not caught.
- `test_v2_names_render` patch "definition changed" is not caught.
(panels_render is green on main and on this branch after its "FA" anchor was updated to "Free agent".)

### Assumed, not run

- The Compare fit at 1366x768 was not re-measured beyond test_v2_waterfall_render, which fails only in the
  mutation guard above, as on main. Remaining render tests outside the list above were not run.
