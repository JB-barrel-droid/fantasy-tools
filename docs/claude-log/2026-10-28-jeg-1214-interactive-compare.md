## 2026-10-28 - JEG-1214 interactive Compare

Contract: Select players from two loaded league rosters and edit a trade in Compare. Show both teams' before/after construction through the JEG-1216 shared lineup component; keep stored rosters and value settings intact.

### Verified (check named)
- `node --check app/v2/v2.js` passed.
- `CHROMIUM_PATH=/usr/bin/chromium JEG1216_HELPER_PATH=/tmp/jeg1216-lineup-comparison.js python -m unittest tests.test_v2_compare_rosters_render -q` passed with the JEG-1216 helper from `fe/jeg-1216-lineup-stability` injected. It checks 2-for-1 editing, values against engine rows, lineup tables and spot changes, bench expansion, repeated selection, Cancel/Back, Swap, tab round trip, missing rosters and preservation of a custom basis/override.
- `CHROMIUM_PATH=/usr/bin/chromium python -m unittest tests.test_v2_compare_empty_side_render -q` passed.

### Claimed, not confirmed
- This branch requires JEG-1216's `lineup-comparison.js` to be loaded before `v2.js`. The released page integration is pending that branch's merge and full CI.
- No live site change has been made.
