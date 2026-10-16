# 2026-10-16 JEG-579 review polish (part of JEG-588)

Audit of the four items on live v2:
- P3-rank-alignment: already done (.v2-vtable td.rank is table-cell). Verified in a browser.
- N461 fold: the per-card module chevron already folds each side. Missing piece was the breakpoint: two-column layout moved 1280 -> 1024 px (css + test thresholds in test_v2_targets_render), expanded list capped at 60vh with internal scroll.
- N477 tier lines: lines were always dashed; now solid on one position ranked by DDF Value, dashed across positions ("approx"); label "Starters" (zones and contract tests updated for the label).
- P3-source-ranks: new. "N overall · POS#" under each value cell, position rank under # in the Player values table, 1200 px and wider.
- Chips from JEG-571 now sit on the player sub-line (compact) to limit row height.

Verified: tests.test_v2_review_polish_render (3 css + label negative patches caught), test_v2_chart_zones_render, test_v2_player_tags_render, test_build_v2_page.
Not verified: test_v2_targets_render full pass (red on main for week 6; its 1440x900 above-the-fold check for Sell/Buy top 5 already failed without chips, 983 px vs 900, and chips add about 24-44 px), test_v2_contract_render (red on main).
Contract Doc lines for the four IDs not added (the Doc lives outside the repo).
