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

### Claimed, not confirmed
- Integration render checks and independent review pending.
- Preview CI, parent serial merge, Pages deployment and live verification pending. JEG-1213 remains open until parent verifies live.
