# Merge sweep for #578 and #654 (2026-10-16)

- #578 is a duplicate of merged #595 (same files identical on main). Close was denied by the classifier; left open.
- #654: merged origin/main cleanly, make sync ran, build_values_explainer reports no logic change since review. Pushed a95b9113. tests.test_v2_rescaled_copy has 1 failure in app/v2 v2.js (the "(indexed)" dot label), not in this diff, from main. Not merged: the PR body says Jeremy is to review the wording first.
- Verified: sync, explainer build line, rescaled_copy run. Claimed: v2.js failure is on main too (not run on origin/main).
