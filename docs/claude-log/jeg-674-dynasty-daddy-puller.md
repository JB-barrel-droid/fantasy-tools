## 2026-10-16 - JEG-674: Dynasty Daddy puller (puller only)

**Ticket:** JEG-674 (child of JEG-623)

Added `pipelines/pull_dynasty_daddy.py` and `tests/test_pull_dynasty_daddy.py` (fixture `tests/fixtures/dynasty_daddy_sample.json`, 20 real rows).

- Verified: live pull 2026-10-16 returned 468 priced QB/RB/WR/TE rows (vintage 2026-10-15; 144 picks and zero-valued rows dropped); 12 unit tests pass.
- Decision recorded: comparison and id-bridge use only (values aggregate other markets). FantasyPros-derived rank columns (`fantasypros_ros`, `avg_ros`) are not kept, because ECR is excluded repo-wide.
- Staleness: SOURCE_STALE when the newest `most_recent_data_point` is over 3 days old (the 3-day limit is my choice; the feed updates daily).
- Not done by design: no Supabase table, saver, bake leg or schedule (need per-source approval).
