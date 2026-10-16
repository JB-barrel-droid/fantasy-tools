## 2026-10-16 - JEG-684: NumberFire ROS projections puller (puller only; from probe JEG-673)

**Ticket:** JEG-684 (child of JEG-623), probe JEG-673

Added `pipelines/pull_numberfire_ros.py` and `tests/test_pull_numberfire_ros.py` (fixture `tests/fixtures/numberfire_ros_sample.json`, 19 real rows from the live response).

- Finding: the FanDuel Research page calls a public anonymous GraphQL endpoint (`POST /research/api/graphql`, query `GetProjections`, `type: REMAINING`, `position: NFL_SKILL`, `sport: NFL`). Found by reading the page's JS chunks, not a browser.
- Verified: live pull 2026-10-16 returned 616 rows, 439 priced (QB 57, RB 112, WR 169, TE 101); 13 unit tests pass.
- Claimed, not confirmed: `fantasy` scoring is unstated (Gibbs 282.2 vs 284.2 recomputed half-PPR); the response carries no date (vintage is the run date); no fumbles or 2-point columns.
- Not done by design: no Supabase table, saver, bake leg or schedule (need per-source approval).
