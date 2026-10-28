## 2026-10-28 - JEG-620 Draft Sharks chart parser contract

Contract: keep the existing public chart puller fail-closed when the embedded JSON spacing changes or a later player row loses required data or stable identity. The source remains outside published chart averages.

### Verified (check named)
- `python3 -m unittest tests.test_pull_draftsharks -v`: parser accepts the saved small embedded-array fixture with JSON whitespace; rejects a missing required value column on a later row and duplicate or missing player identity. Existing zero/null, scale, position floor, and no-write-on-failure tests also pass.
- `curl -L https://www.draftsharks.com/trade-value-chart` from this execution environment failed before an HTTP response: CONNECT tunnel returned 403 (curl 56). This is an environment access blocker, not evidence that the site itself denied the page.
- Public web reader opened `https://www.draftsharks.com/ros-rankings` and `https://www.draftsharks.com/weekly-rankings` on 2026-10-28: both display DS projections and scoring controls. Its chart fetch rejected `https://www.draftsharks.com/trade-value-chart` because the page exceeds the reader's 4 MB limit.

### Claimed, not confirmed
- The current 2026-10-28 trade chart still has the same embedded JSON keys as the 2026-10-12 capture. A direct current raw page capture was unavailable here, so no live parser assertion is made.
- A weekly or ROS projection adapter needs an inspectable raw public page/export and a stable player identifier. The web reader omits player names from its extracted table, so these projections were not added from incomplete data.
