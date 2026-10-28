## 2026-10-28 - League-wide finder improvements / JEG-1213

Contract: implement the ten requirements in the live Linear issue, read on 2026-10-28 (no comments). Preserve #1043 phone fixes, reuse #969 sharing, and leave #1044 value methodology alone. Integration branch `fe/jeg-1213-league-finder`; no merge, deployment, Supabase mutation, or ticket closure authorized in this lane.

### Verified (check named)
- Intake: read HANDOFF and AGENTS, live JEG-1213 description/comments, and live PR metadata for #1043/#1044/#969. Linear get_agent_context returned tool-not-found, so repository instructions and source code supplied area context.
- Dependencies: branch starts at #1043 live head `d886fc9f` and merges `origin/main` (`e931b84a`) and #969 head `391308ed` normally. The branch does not edit either dependency PR.
- `python3 -m unittest tests.test_jeg1213_summary_fields tests.test_v2_league_units`: 3 tests, exit 0. The new helper preserves missing market values and filters on displayed precision and current summary ranking basis.

### Judgment choices
- Summary columns and filters can refer to Our team or Their team. They use the current summary before a trade; this is stated in the controls. All original summary columns, strengths, weaknesses, position allocation, and projection totals are available. Filters combine with AND and missing data requires Missing explicitly.
- Best opportunity keeps ordinal #1 and existing fit-tier/edge ranking. No value methodology change.
- Existing engine supports exactly 8/10/12/14 teams. Warn once at least eight teams are present; exact quick fix is offered only for supported counts. Other counts are explained rather than silently changing league value math.
- Existing bounded workspace and finder share codecs are reused, with league settings included. No privacy text choice reopened.

### Integration verification
- Combined targeted suite: `RENDER_TESTS_REQUIRED=1 CHROMIUM_PATH=/usr/bin/chromium python3 -m unittest tests.test_jeg1213_import tests.test_jeg1213_logic tests.test_jeg1213_summary_fields tests.test_jeg1213_acceptance_render` — 20 tests, exit 0 in 52.387 seconds, no skips.
- Independent source review found two defects: a fit info click selected its row and closed the explanation; expanded core groups could break rank ordering. Both fixed; browser regression asserts the explanation stays open without row selection and revealed ranks remain sorted.
- First rendered pass also exposed K/DST key changes on share roundtrip; bounded codec now retains exact identity and NFL team, with legacy decoding retained. Removing the new encoder fails the identity regression. Yahoo navigation mutation also fails its regression.
- Mismatch shortcut now retains the complete current settings query and changes only `teams`; rendered regression pins advanced options and season settings. Malformed links keep existing saved teams.
- Useful package checks use controlled named-player prices through the real finder, computePairing and runAll, with and without a balancing bench player. These are behavior tests, not claims about current Bijan/Kyren/Warren prices.
- Finder agent observed the existing `test_v2_finder_search_unchanged` golden is stale on both baseline and patch (identical signatures: 2-for-2 10 trades/7 groups; 3-for-3 69/23). Golden unchanged.

- Existing team-list and expanded-core regression methods pass. Existing table test found a test-helper error: for 11–20 total results it clicked only the absent All button, so the complete-rank assertion read a capped first page. Added the More fallback while retaining the exact `1..N` assertion. Targeted table rerun pending.

### Claimed, not confirmed
- Preview CI, parent serial merge, Pages deployment and live verification pending. JEG-1213 remains open until parent verifies live.
