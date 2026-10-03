# JEG-239: explicit deterministic Option C roster contract

The producer previously used only12teams/1QB2RB3WR1TE/12flex/72bench. Stable
sorting made tied role assignments depend on input order, and Cut players were
omitted. This slice makes those assumptions explicit, configurable and testable.
It is stacked on precision PR48 and validation PR47.

`RosterConfig` validates positive integer teams, nonnegative integer slots for
exactly QB/RB/WR/TE, per-team flex count/eligibility, an explicit **league-total**
bench count and scoring. Dedicated→flex→bench uses descending native price then
ascending numeric supplied canonical key. Key aliases and unresolved/non-numeric
formats reject; this does not certify actual fixture membership. CLI requires a
versioned config and complete requested pools. Missing dedicated/flex/bench
capacity fails rather than silently filling a smaller roster. Pure-function
compatibility retains a labeled12-team default and partial arithmetic mode;
production callers must pass explicit config/require_complete.

Cut rows carry `POS|Cut`, factor0/U0 and unchanged native value. Reweight's two
role consumers skip these rows and preserve0; they never acquire a group budget.
This compatibility change does not repair per-source70 or player-clipping defects
(JEG240/241), nor producer/view wiring (JEG242).

CLI config example for the existing publisher Sheet:

```json
{"schema":"option-c-publisher-roster-v1","teams":12,
 "slots":{"QB":1,"RB":2,"WR":3,"TE":1},"flex_count":1,
 "flex_eligible":["RB","WR","TE"],"bench_total":72,"scoring":"half_ppr"}
```

Call `build_imputed_vorps.py --values <values.json> --group-vorps <groups.json>
--roster-config <config.json> --out <output.json>`. Config must match the target's
teams/scoring/dedicated/flex metadata. Explicit target bench_mix counts are
recorded separately from publisher bench_total: approved publisher72 and granular
reference80 are neither silently equated nor rescaled. Existing group target
numbers remain unchanged. Incompatible/absent metadata rejects before output.
The sidecar `<output-path>.manifest.json` records method, publisher and target
rosters/counts, units (unknown when absent), exact input hashes and output hash.
Consumers must verify the hash pair before use/promotion; no freshness, identity
coverage, approved unit migration or deployment verdict is implied. JEG242/243
still own complete source/vintage/coverage/units integration.

```bash
python3 -m unittest tests.test_imputed_roster_config tests.test_imputed_vorps_precision tests.test_imputed_vorps_validation -v
python3 tests/test_imputed_vorps_clean.py
git diff --check
```

18 targeted tests pass (6roster+4precision+8validation). Old count script still
passes after replacing toy name keys with numeric fixture identifiers; its
placeholder proportional test is not treated as evidence. Matrix/custom/ties,
incomplete pools, malformed configs/key aliases, Cut/reweight compatibility,
explicit72/80 counts, metadata mismatch/sentinel preservation and output hash
are tested. Negative baseline: old producer changes ties under reversed input;
new producer is identical. Old full340-row arithmetic pool returns168rows;
new retains340 including172Cut zeros. Synthetic IDs are arithmetic fixtures,
not a canonical source-coverage approval. Makefile includes all three real modules.

Independent read-only Claude Code MCP review reran all18 tests and the old
count script, found no bug, and confirmed production wiring/coverage remain
pending. `make validate` exits0 on isolated composite main5792ba5 plus
PR47/48/this slice and pending PR43. Current main/production are not claimed green.
No fixture, granular-reference roster, allocation/economics default, promotion
or rendered behavior is changed. Roman independently reviews/integrates/deploys;
JEG183 remains open until all pipeline/Sheet/config/source/rendered prerequisites.
