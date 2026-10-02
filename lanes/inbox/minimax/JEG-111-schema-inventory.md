# JEG-111-schema-inventory — result report (dispatcher-written; worker's evidence bundle was missing)

Branch: `minimax/jeg-111-schema-inventory` (base `5df093c9b199`, origin/main)
Worktree: /tmp/wt-jeg111-schema-inventory
Worker: M3 via mmcode exec (20m timeout, 120 max steps) — run SUCCEEDED, but the
final message was truncated to a single `<think>` block and the worker wrote NO
evidence bundle. This file is the dispatcher's reconstruction.

## Files changed (new)
- `pipelines/inventory_supabase_schema.py` (440 lines) — read-only parser:
  sql/migrations/*.sql -> CREATE TABLE / VIEW / MATERIALIZED VIEW / FUNCTION /
  PROCEDURE / TRIGGER, grouped by subproject (trade-value, waiver-wire,
  lottery/fds, razzball, cbs-ros, shared/reference, unclassified). Stdlib only
  (argparse/json/re/sys/datetime/pathlib); no network, no DB client. Outputs
  JSON to stdout + optional `--out`. Grouping heuristic documented in the
  docstring; anything unclassifiable -> "unclassified", never guessed.
- `tests/test_inventory_supabase_schema.py` (422 lines) — unittest suite, 36
  tests: comment/string stripping, per-kind extraction, classification needles,
  fixture-tree end-to-end (7 fixture files incl. an "unclassified" case).

Removed before commit: `test_write.txt` (worker sandbox probe artifact, not
part of the brief).

## Dispatcher repairs (the worker shipped broken code)
The worker's version failed 16/36 tests (9 failures + 7 errors) and crashed
the parser on any VIEW/FUNCTION/PROCEDURE/TRIGGER input:
1. `_extract_objects` called `m.group("s1")..("n5")` on every match, but each
   regex only defines its own group names -> `IndexError: no such group` on
   all non-TABLE kinds. Fixed to use `m.groupdict().get(...)`.
2. `build_inventory` used `root.glob("*.sql")` but the fixture tree nests SQL
   under `sql/migrations/` -> empty inventory. Fixed to `rglob("*.sql")`
   (identical behavior on the real flat dir).
3. Two fixture expectation bugs: expected TABLE count 5->6 (comment even said
   "Adjust"); true count is 7. `test_trade_value_subproject` expected a
   `source_trade_values` TABLE that the fixture never creates (only an INDEX
   on it, which is out of scope); the fixture's actual object is the VIEW
   `source_value_adjustments_v`. Fixed expectations to the fixture's truth.

## Acceptance evidence (dispatcher-run)
```
$ python3 pipelines/inventory_supabase_schema.py --out ~/workspace/jeg111-schema-inventory-check.json
exit 0
totals: {'TABLE': 2, 'files': 6, 'subprojects': 2}
groups: {'cbs-ros': 1, 'razzball': 1}
```
On the real `sql/migrations/` at this base: 6 files, 2 CREATE TABLEs found
(`cbs_ros_projections` -> cbs-ros, `razzball_projections` -> razzball). The
other 4 files are ALTER/index migrations with zero CREATEs.

```
$ python3 -m unittest tests.test_inventory_supabase_schema -v
Ran 36 tests in 0.157s — OK
```
```
$ python3 -m py_compile pipelines/inventory_supabase_schema.py tests/test_inventory_supabase_schema.py
OK
```

Discrimination: the pre-repair worker code failed 16/36 (incl. every
VIEW/FUNCTION/TRIGGER extraction test) — the suite catches the real bugs.

## VERIFIED (executed by dispatcher, outputs pasted above)
- py_compile on both files
- script exit 0 + valid JSON on the real migrations dir
- 36/36 unittest green post-repair

## UNVERIFIED / open items
- `make validate` (reviewer gate; brief marks it reviewer-run) — not run here.
- **Scope gap for the reviewer:** at base 5df093c, `sql/migrations/*.sql`
  holds only 6 files and the live project tables (source_trade_values,
  publisher_vorp, publisher_roster_assumptions, players, ...) have NO create
  statements in this dir. The script fulfills the brief ("parse
  sql/migrations/*.sql ... the local schema source of truth"), but the
  inventory is NOT the full project schema. Step 2 (naming convention)
  needs a decision on the source of truth for the complete object list
  (live-DB introspection vs. earlier migration history elsewhere).
- `--out /tmp/schema-inventory.json` FAILED with `OSError: [Errno 28] No
  space left on device` — /tmp (512M tmpfs) is 100% full (other lanes'
  artifacts: logs, zips, result JSONs). Wrote to ~/workspace instead.
  Flagging: /tmp needs a cleanup pass before more workers land.
- Unclassifiable names on the real dir: none — both found objects
  classified cleanly. (Fixture covers the "unclassified" path: mystery_table.)

## Recommendation
Code + tests are now sound and read-only by construction (no network, no DB
client, sql/* untouched — input dir was never modified). Ready for reviewer
merge decision; note the scope gap above for JEG-111 step 2.
