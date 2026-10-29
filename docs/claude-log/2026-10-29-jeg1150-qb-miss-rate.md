## 2026-10-29 - JEG-1150 QB miss_rate research

Contract: research only. Compare QB miss_rate alternatives in the bench allocation (`pipelines/lib/roster_convention.py`, JS twin in `value-model.js`) and show bench seats and absolute values; no model change.

### Verified (check named)
- Live rate reproduces the ticket's std/12 seats QB8/RB42/WR27/TE7: `python3 tools/research/jeg1150_qb_miss_rate.py` on `data/fixtures/current` (as of 2026-10-29), main `5c07ad6`.
- Seats and values for 0.06/0.09/0.12/0.15 across 3 scorings x 4 team counts: same script, output `docs/research/data/jeg1150_qb_miss_rate.json`.
- 0.09 gives identical std/12 values to live: `players_moved` in that file lists no difference between 0.09 and 0.12 at std/12.
- No file under `pipelines/`, `app/` or `config/` changed: `git diff --stat main`.

### Claimed, not confirmed
- JS twin would give the same seats: same constants and formula by reading `value-model.js`; not run under node.
- Jeremy's league figures (7 of 66 QB, 30 RB, 23 WR, 6 TE) are from the ticket text, not re-pulled.
