# DynastyProcess player values (JEG-1565 snapshot)

- Source: https://github.com/dynastyprocess/data, file `files/values-players.csv`, by DynastyProcess.
- License: GPL-3.0 (copy in `LICENSE`, retrieved 2026-11-07 from the repository's `LICENSE`). The repository README states no further data terms.
- Retrieved: 2026-11-07, from raw.githubusercontent.com at the five weekly commits listed in `snapshots.json` (one unauthenticated GitHub API call listed the commits). No credentials.
- Stored: only the columns the audit uses (`player, pos, team, age, value_1qb, value_2qb, scrape_date`); values unchanged.
- Method (DynastyProcess's own page, https://dynastyprocess.com/values, read 2026-11-07): Value = 10500 x e^(-0.0235 x FantasyPros dynasty ECR); 12-team PPR; `value_2qb` from a 2QB conversion.
- Used by `pipelines/research_trade_value_audit.py`.
