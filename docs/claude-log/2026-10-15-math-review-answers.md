# 2026-10-15: JEG-450 math review answers recorded

Jeremy answered the four JEG-450 questions on 2026-10-15: Q1 label the tier column "ESPN Tier"; Q2 close GAP-ADJ-IDENTITY-FALLBACK-UNLABELLED as moot (fit retired); Q3 retire the CBS ROS / Razzball direction and markup checks; Q4 keep zeros counted in the Indexed factor (OC-8 option A).

Changed: docs/decisions.md (math-review-2026-10-15), docs/math-review-agenda.md, docs/risk-register.md (Q2, Q3 rows closed).

Verified: tests/test_published_league_settings_engine.py and tests/test_view_invariants.py pass (5 tests); grep of app/, pipelines/ and tests/ shows starterMarkupSane and fixedPieDirectionSane already removed by JEG-508/JEG-539, so Q3 needed no code deletion.
Not verified: no headless page run; the unused starter_markup_sane_band constant is left because removing it changes the frozen read contract.
