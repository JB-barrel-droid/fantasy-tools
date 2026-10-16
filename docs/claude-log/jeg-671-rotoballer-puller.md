## 2026-10-16 - JEG-671: RotoBaller trade value puller (puller only)

**Ticket:** JEG-671 (child of JEG-623)

Added `pipelines/pull_rotoballer.py` and `tests/test_pull_rotoballer.py` (fixtures `tests/fixtures/rotoballer_week5_sample.html`, the real Week 5 table and title, and `rotoballer_search_sample.html`, the real search-result links).

- Verified: 16 unit tests pass; live run 2026-10-16 fails closed `[SOURCE_STALE] article is Week 5, NFL week is 6` (correct: the Week 6 article is not out yet); replay with `--today 2026-10-09` parses 200 QB/RB/WR/TE rows.
- Finding: the stable URL `/fantasy-football-trade-value-chart` still redirects to the Week 1 article (Sept 13), five weeks old. The puller finds the newest week-N article for the season on the site search page and falls back to the stable URL (which then fails stale).
- Claimed, not confirmed: scoring format and league size are not stated in the table or article text, so the snapshot has `scoring: null`; needs a methods decision before any use. Week 5 has 200 rows and no K/DST; Week 1 had 400 with K/DST, so row floors are set from Week 5 (about 40%).
- Not done by design: no Supabase table, saver, bake leg or schedule (need per-source approval).
