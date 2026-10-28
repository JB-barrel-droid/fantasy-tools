# CBS Week 8: tight ends dropped by a <td> header row

Jeremy asked (2026-10-28) why CBS's Week 8 tight end values came through empty.
The chain held CBS red at fidelity scrape_validity: "stored TE 10->0".

Cause: CBS's Week 8 TE table puts its header in a bold `<td>` row; weeks 5-7
used `<th>`. `ops/watchdog/pull_cbs.py` `parse_tables` read headers only from
`<th>`, so the TE table had none, and the "Player" row was kept as a player.
`pipelines/save_espn_cbs_references.py` `build_cbs_rows` then dropped every TE
for missing non/0.5/PPR columns. `ingest_common.validate_tables` counts parsed
rows (TE=18), not saved rows, so the run wrote QB/RB/WR and no TEs.

Evidence (cbs_trade_values, 1QB): Week 7 TE 13/13/15 (std/half/PPR), Week 8
TE 0 in every scoring. Week 8 review rows 106 = 54 QB dashes (as Week 7) + 17
TEs x 3 missing columns + 1 unmatched "Player" row. The fidelity pulse's own
page parser sees 17 TEs.

Fix: a row whose first cell is "Player" is a header row: it becomes the
headers when the table has no `<th>`, and is never kept as a player.
Tests: `tests.test_cbs_week_coding.ParseTablesHeaderTest` (fails on the old
parser, passes now).

Not done here: a guard that fails the ingest when a position saves 0 rows
(suggested follow-up). The daily ingest (pg_cron, 12:07 UTC) re-reads Week 8
after merge; the TE rows change the content, so it is not an "unchanged" skip.
Couldn't see the raw HTML (proxy refuses cbssports.com); the cause is inferred
from stored rows, review counts and the pulse's read of the page.
