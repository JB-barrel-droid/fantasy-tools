## 2026-10-16 - JEG-669: KeepTradeCut puller (puller only)

**Ticket:** JEG-669 (child of JEG-623)

Added `pipelines/pull_keeptradecut.py` and `tests/test_pull_keeptradecut.py` (fixture `tests/fixtures/keeptradecut_sample.html`, a 20-row slice of the real page).

- Verified: live run 2026-10-16 returned 464 priced QB/RB/WR/TE rows (36 rookie picks dropped); 9 unit tests pass.
- Fetch uses curl (`--tlsv1.2`), because urllib fails TLS on this host.
- Formats kept: 1QB and superflex, each with base and three TE-premium blocks (value, rank, positional rank, tier). 0 or missing is null.
- Not done by design: no Supabase table, saver, bake leg or schedule. Values are dynasty-framed, so a methods decision is needed before DDF use.
