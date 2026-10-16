## 2026-10-15 - JEG-621 Fantasy Sharks puller (part of JEG-612)

Contract: bring Fantasy Sharks into the pipeline per the source pattern (puller, fail closed), public pages only, without wiring it into published DDF Value. JEG-620 (Draft Sharks puller) was already merged in #573; its saver, bake leg and pulse are still not built (same gate as here).

### Verified (check named)
- Public, no login: `curl` of https://www.fantasysharks.com/apps/bert/forecasts/projections.php (HTML and `csv=1`, Segment=877 rest of year, Position=97 all offense, scoring 1/18/2) returned HTTP 200 on 2026-10-15; live run of `pipelines/pull_fantasysharks.py` wrote 480 QB/RB/WR/TE rows (QB 71, RB 126, WR 174, TE 112 before dedup by id), vintage 2026-10-15 from the page's "Last updated 10-15".
- Published surfaces probed: weekly (Segment 883-900), 2027-2029 seasons and rest of career (99200) exist on the same endpoint; no public trade value chart exists (`/apps/Remora/tradecoach.php` is an interactive tool, `/apps/bert/forecasts/tradevalue.php` is 404). So the ticket's "trade value chart" yields nothing; ROS projections are the usable input.
- `tests/test_pull_fantasysharks.py` (12 tests, added to `make test-core`): nulls not zero, IDP dropped, "Last, First" name swap, non-CSV body = SOURCE_BLOCKED, missing Pts column = SOURCE_LAYOUT, missing position = SOURCE_TRUNCATED, out-of-range / non-numeric Pts = VALUE_RANGE, swapped scoring sets = VALUE_RANGE (non-PPR <= half <= PPR check), stale stamp = SOURCE_STALE, Period/Position/stamp moved on the page = SOURCE_LAYOUT, CLI writes nothing on failure.

### Claimed, not confirmed
- Pts is a rest-of-year TOTAL, not per game (the CSV has no games column). The chart consumes per-game rates, so a saver/bake leg needs games remaining (`pipelines/lib/games_remaining.py`); see GAP-FANTASYSHARKS-ROS-TOTAL in the risk register.
- Identity: the real resolver (`lib/canonical_players.resolve_with_reason` against live `public.players`) was not run. Fantasy Sharks ids are carried for the saver.
- robots.txt asks Crawl-delay 60; the puller makes 4 requests with a 5 s default gap. Legal/ToS review is out of scope (Jeremy 2026-10-12).
- Not done, by design: saver, Supabase table, workflow, source_probe signal, bake leg, fidelity pulse. A new table is a production Supabase schema change Jeremy has not approved (CLAUDE.md standing constraint), and DDF Value must not take the source until its pulse is green.
- `make validate` not run (about 17 agents on the machine); ran the targeted puller suites only. No chart numbers change (nothing reads the new snapshot).
