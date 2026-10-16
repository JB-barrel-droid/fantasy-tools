# A source is held

A held source keeps its last promoted section and is kept out of DDF Value; the other sources publish (decision `per-source-promotion-001`). Three things hold a source: the chain's review of a candidate section, the value check (engine against the Python reference, JEG-479) and the fidelity pulse (publisher site, stored values and live chart, JEG-520).

## 1. Which source, and why

```
python3 -c "import json;d=json.load(open('dist/modules/comparison-chain-status.json'));print(d['outcome']);[print(k,'->',v[:160]) for k,v in d['sources'].items() if 'HELD' in v]"
python3 -c "import json;d=json.load(open('dist/modules/value-check.json'));print(d['verdict'],d['disagreeing_sources'])"
python3 -c "import json;d=json.load(open('dist/modules/fidelity-pulse.json'));print({k:v['reason'] for k,v in d['holds'].items()})"
```

Expected on a clean site: `published`, no HELD lines, value check `agree []`, pulse `{}`. On 2026-10-12 the committed state was `published_with_holds` with three sources held:

- FantasyCalc: held at stage `review` (coverage: TE priced 26 < fixture 28; a human must review).
- CBS rest of season and Razzball: held at stage `snapshot` ("awaiting players bake": the snapshot differs from the one `players.json` was baked from; the section waits for a bake from the same snapshot).
- Pulse: Razzball held at `stored_vs_chart`.

A held section in the fixture carries `validationHold: {reason, ...}`; a reason starting `fidelity: ` is a pulse hold, anything else is a value-check hold. Monitored signals: `rebuild_chain_source_held` (amber: any source held this run) and `rebuild_chain_source_held_stale` (red: a held section is two or more content weeks behind).

## 2. Cause and action

| Evidence | Cause | Action |
|---|---|---|
| Held at `snapshot`, "awaiting players bake" | Projection sources are baked into `players.json` with the ESPN anchor and the section must match that bake. | Dispatch the chain with a bake: `gh workflow run rebuild-chain.yml -f bake_players=true`. |
| Held at `review` with a failing coverage check | Candidate prices fewer players than the fixture, or a combo is missing. | Run `make coverage-triage SOURCE=<source>` (section 3a): it lists the dropped players and the decision commands. The chain never overrides a review hold. |
| Pulse names a stage (publisher, stored, chart) | The publisher moved, or our save or match is wrong. Tolerances: `docs/fidelity-tolerances.md`. | Fix the save or match and re-run the producer ([weekly-refresh.md](weekly-refresh.md) step 4). Do not loosen a tolerance to clear a red. |
| Value check lists mismatches | Engine and `pipelines/value_reference.py` disagree. | Treat as a code bug; reproduce with [sweep-and-rank-guard.md](sweep-and-rank-guard.md). |
| Import health `stale` | A producer did not write. | Re-dispatch it. |
| One Razzball row far below ESPN and CBS | The missed-games guard (`razzball_outlier_reason`, JEG-555) holds that row, not the source. | See `rz_held` in `review_rows` and `docs/risk-register.md` GAP-RZ-MISSED-GAMES-DISCOUNT. |

## 3. Release

Nothing is released by hand. A fidelity hold lasts while the latest pulse lists it; the next chain run drops it when the pulse is clear (`pipelines/fidelity_hold.py`). A value-check hold is released by the next agreeing `value_check` (`release_holds`). A review or snapshot hold clears when the next chain run's candidate passes. So: fix the cause, re-run the producer, dispatch the chain ([run-the-chain.md](run-the-chain.md)), then repeat step 1.

If a source stays held more than a week, the red `rebuild_chain_source_held_stale` fires. Whether to keep waiting or drop the source is Jeremy's decision, not a bypass.

## 3b. A shorter or longer list is filled in, not held (JEG-667)

Jeremy, 2026-10-16: "When lists get longer or shorter we need to follow the conventions we've set, filling in where needed from other charts to get to full rosters in leagues."

The fill-in rule (OC-5, `docs/methodology.md` VP-2.4) fills every chart to the league's rosterable set (`N_p`, starters plus bench, plus the waiver player) from the other charts, or from the chart's own curve. So the review (`review_comparison_candidate.py`) does not hold a chart because its list got shorter:

- **Passes as a warning** when the Python reference, run on the candidate in all four league sizes, fills the position to `N_p + 1`. The check `coverage:<combo>/<POS>` is `warn` and names every dropped and added player; a same-length or longer list with new names gets `coverage_list:<combo>/<POS>` (warn). The chain status names them (`list_changes`, the source's detail line) and the status page marks the row "List changed".
- **Still holds** when fill-in cannot reach `N_p` (the chart lists nobody at the position, the week has no projection, or a rosterable player has no source to estimate him from), when the source is a projection (not filled in), or when a dropped player is a pipeline loss: still priced live, still listed but unpriced, or in the candidate's identity review rows. Those go to 3a.

## 3a. Coverage hold: decide in one look (JEG-667)

```
make coverage-triage SOURCE=cbs                    # latest chain status, or output/reviewed/ artifacts if present
make coverage-triage SOURCE=fantasycalc REV=<sha>  # status + fixture as of an earlier commit
```

The brief prints coverage vs the fixture floor per combo and position; each dropped player with team, last value, rank and a call (ROTATION: IR, PUP, practice squad, free agent, inactive or no team; SCRAPE: active mid-list player; TAIL: active but at the list's tail, publisher trimming plausible; UNCLEAR); a recommendation among:

- **A. Accept the rotation** (names all listed, none still on the source): `python3 pipelines/coverage_triage.py accept <source> --names --approve "Jeremy <YYYY-MM-DD> <reason>"`
- **B. Refresh the floor** to the candidate's count (list resized, names do not tell the story): `python3 pipelines/coverage_triage.py accept <source> --floor --approve "Jeremy <YYYY-MM-DD> <reason>"`
- **C. Neither**: a scrape or pipeline loss. Fix the producer or match, re-run it, dispatch the chain.

A and B write `data/triage/coverage-accepted.json` (source, combo, position, content week, approver, reason). Commit it to main and dispatch `gh workflow run rebuild-chain.yml`; `review_comparison_candidate.py` then passes exactly that drop as a warn, the verdict can be `ready`, and the chain's own promote step refreshes the floor. An entry expires with its content week, never covers a different position or an unnamed player, and is ignored when the reviewer found the dropped player still priced live or still listed. Nothing is released by the triage script itself.
