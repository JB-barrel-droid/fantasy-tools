## 2026-10-19 - JEG-721 QA: header "all sources current" misleading when sources held

- **Finding:** The header chip says "all sources current" based solely on pipeline freshness data (reference-freshness.json). It does not account for fidelity holds. With 5 of 7 sources held (CBS, CBS ROS, ESPN, FantasyCalc, Razzball) and only 2 shown (USA Today, FantasyPros), the claim is false.
- **Root cause:** `rootFreshness()` in v2.js checks pipeline freshness (weeks_behind, freshness_ok) but not the engine's hold state (excludedReason). A held source with green freshness data is reported as "current".
- **Fix:** Added a "held" status to `rootFreshness()` that fires when all of a publisher's series are unavailable and have a hold-related excludedReason. The header chip now says "N sources held" instead of "all sources current" when sources are held. The freshness panel shows a pause icon for held sources.
- **Shown sources verified correct:** USA Today 894/894 publisher-vs-stored and stored-vs-chart exact match; FantasyPros 630/630 exact match (fidelity pulse stages 1+2, all combos). The "2 rescaled trade charts" count is correct.
- **2 charts is expected:** CBS is review-held, FantasyCalc is fidelity-held; both correctly excluded from display. ESPN/CBS-ROS/Razzball also held. Only USA Today + FantasyPros are available.
- **Tests updated:** GL-05 in test_v2_contract_render.py now expects CBS as "held" (was "unknown") and the reload chip to mention "held" (was "all sources current"). test_v2_panels_render.py updated to track held status in ROOTS_JS and expectations.
- **Verified:** test_v2_contract_render.py 6/6 pass including mutation test (removing the held check → chip claims "all sources current" → GL-05 catches it). Build succeeds. JS syntax validated.
- **Not run:** Full make validate (running in background, not waited for). 12-combo sweep not run (no chart value changes).
