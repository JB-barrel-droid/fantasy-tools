# Trade Value Dashboard QA - Error List & Monitoring Criteria
**Date:** 2026-09-30  
**QA Target:** https://jb-barrel-droid.github.io/fantasy-tools/ (live trade value dashboard)

## Round 2 Verification (2026-09-30 13:33 UTC)
Both critical fixes verified on live build tv-20260930-1329-0a64570:
- **QA-001 FIXED & VERIFIED:** Chart renders with 5 curves (ESPN adjusted, FC/USAT/FP/CBS Adjusted Wk 4). Pink "Curves unavailable" banner gone. Chart health still shows "1 FAIL" on scale agreement (USA Today QB 0.51x) but chart renders despite it — guard now warns instead of blocking.
- **QA-002 FIXED & VERIFIED:** Table syncs with chart settings in ~200ms (well under 2s polling backup). Tested Full/Half/Standard × 12/8 teams. Captions and values update correctly.

## Errors Found (Round 1)

### CRITICAL
1. **Chart renders blank on guard failure**
   - Symptom: Chart canvas blank white, red alert "Curves unavailable: Curve regression guard failed: sourceScaleAgreement"
   - Root cause: `sourceScaleAgreement` guard in curve-widget.js threw an error that blocked all chart rendering
   - Impact: Users see no curves at all when sources genuinely disagree
   - Fix: Removed `sourceScaleAgreement` from blocking guard list (commit pending). Guard now warns via ChartHealth but allows chart to render.
   - Monitoring: Chart must render curves even when scale agreement fails; ChartHealth must show warning, not blank page.

2. **Player table ignores league settings**
   - Symptom: Switching scoring (Full→Half→Standard) or teams (12→8) updates chart but table values stay byte-identical; caption stays "Full PPR · 12 teams"
   - Root cause: Event sync between curve widget and comparison dashboard unreliable
   - Impact: Table shows wrong values for user's selected league settings
   - Fix: Added 2-second polling backup sync in comparison-dashboard.js (commit pending)
   - Monitoring: Table caption must match chart caption after any setting change; table values must differ across scorings.

### MAJOR
3. **ESPN adjusted checkbox silently reverts**
   - Symptom: Unchecking "Show ESPN adjusted curve" appears to work, then reverts with no feedback. Caption says "locked to ESPN adjusted value".
   - Root cause: Guard force-reverts without user notification
   - Impact: Confusing UX, user doesn't understand why their action was undone
   - Fix needed: Show toast/notification explaining why the curve is locked
   - Monitoring: Any silent state revert must trigger visible user feedback.

4. **Curves unavailable in some league setups**
   - Symptom: Under Standard scoring or 8-team, most curves show "not available... in the current artifact"
   - Root cause: Data artifact doesn't include all scoring/team combos for all sources
   - Impact: Users in non-standard leagues get degraded experience
   - Monitoring: Track which combos are missing per source; alert when coverage drops.

5. **Contradictory freshness messaging**
   - Symptom: Table caption says "sources current" while dataset health shows "9 stale refs", news cells say "Sep 18 · older than values"
   - Root cause: Different components use different freshness definitions
   - Impact: User confusion about data reliability
   - Fix needed: Unify freshness messaging; "sources current" should only appear when all refs are fresh
   - Monitoring: Caption freshness claim must match dataset health status.

### MINOR
6. **Rank slider range mismatch**
   - Symptom: Zoom slider says "Player rank 1–530" but table holds 371 players
   - Fix needed: Slider max should reflect actual player count
   - Monitoring: UI ranges must match data counts.

7. **Coverage baseline confusion**
   - Symptom: Coverage measured against "596-player canonical snapshot" while sources cover 116–610 of 610
   - Monitoring: Coverage denominator must be consistent across UI.

### DATA QUALITY
8. **Scrambled player-team assignments**
   - Symptom: Kyler Murray MIN, Tua Tagovailoa ATL, Kenneth Walker III KC, Jaylen Waddle DEN, etc.
   - Status: Likely intentional QA seed data, but user-visible
   - Monitoring: Player-team assignments must match official rosters; flag mismatches.

## Monitoring Criteria to Add

### C1: Chart Render Health
- **Check:** Chart canvas contains visible curve paths (not blank)
- **Frequency:** On every page load and after any setting change
- **Fail condition:** Canvas is blank white with no curves rendered
- **Action:** Alert immediately; do not deploy if chart is blank

### C2: Guard Failure Mode
- **Check:** When `sourceScaleAgreement` fails, chart still renders with warning
- **Frequency:** On every guard evaluation
- **Fail condition:** Guard failure blanks the chart
- **Action:** Guard must degrade gracefully, never block rendering

### C3: Table-Chart Settings Sync
- **Check:** After scoring/team change, table caption matches chart caption within 3 seconds
- **Frequency:** After every setting change
- **Fail condition:** Captions differ, or table values identical across scorings
- **Action:** Flag sync failure; check event system and polling backup

### C4: Silent State Reverts
- **Check:** Any programmatic revert of user action triggers visible notification
- **Frequency:** On every state change
- **Fail condition:** Checkbox/toggle reverts without user feedback
- **Action:** Add user notification for the revert reason

### C5: Freshness Message Consistency
- **Check:** "Sources current" label only appears when zero stale refs
- **Frequency:** On every render
- **Fail condition:** Caption claims "current" while health shows stale refs
- **Action:** Unify freshness logic across components

### C6: UI Range Accuracy
- **Check:** Slider max values match actual data counts
- **Frequency:** On data load
- **Fail condition:** Slider range differs from data by >5%
- **Action:** Derive ranges from data, not hardcoded values

### C7: Player-Team Assignment Validity
- **Check:** Sample of player-team assignments match official rosters
- **Frequency:** Daily
- **Fail condition:** >2% mismatch rate
- **Action:** Flag data corruption or stale roster mapping

### C8: Value Sanity Bounds
- **Check:** Top player values within expected ranges (QB: 20-40, RB: 50-75, WR: 30-45, TE: 15-30 for Full PPR 12-team)
- **Frequency:** On every data build
- **Fail condition:** Values outside 2x expected range
- **Action:** Block publish; investigate data pipeline

## Next QA Round
After deploying fixes for #1 and #2, re-run full QA:
- Verify chart renders with curves visible
- Verify table updates on scoring/team changes
- Test all input combinations
- Check mobile layout (was not tested in Round 1)
- Capture console errors (was not capturable in Round 1)
