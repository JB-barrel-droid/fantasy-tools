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
| Held at `review` with a failing coverage check | Candidate prices fewer players than the fixture, or a combo is missing. | Read the failing check text in the status file. Fix the producer or match, or have Jeremy decide it is genuine source change. The chain never overrides a review hold. |
| Pulse names a stage (publisher, stored, chart) | The publisher moved, or our save or match is wrong. Tolerances: `docs/fidelity-tolerances.md`. | Fix the save or match and re-run the producer ([weekly-refresh.md](weekly-refresh.md) step 4). Do not loosen a tolerance to clear a red. |
| Value check lists mismatches | Engine and `pipelines/value_reference.py` disagree. | Treat as a code bug; reproduce with [sweep-and-rank-guard.md](sweep-and-rank-guard.md). |
| Import health `stale` | A producer did not write. | Re-dispatch it. |
| One Razzball row far below ESPN and CBS | The missed-games guard (`razzball_outlier_reason`, JEG-555) holds that row, not the source. | See `rz_held` in `review_rows` and `docs/risk-register.md` GAP-RZ-MISSED-GAMES-DISCOUNT. |

## 3. Release

Nothing is released by hand. A fidelity hold lasts while the latest pulse lists it; the next chain run drops it when the pulse is clear (`pipelines/fidelity_hold.py`). A value-check hold is released by the next agreeing `value_check` (`release_holds`). A review or snapshot hold clears when the next chain run's candidate passes. So: fix the cause, re-run the producer, dispatch the chain ([run-the-chain.md](run-the-chain.md)), then repeat step 1.

If a source stays held more than a week, the red `rebuild_chain_source_held_stale` fires. Whether to keep waiting or drop the source is Jeremy's decision, not a bypass.
