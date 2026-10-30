## 2026-10-27 - JEG-925 research post 9: rules refresh, numbers held for week-8 charts

Contract: refresh post 9 (how position weights are derived) to today's rules and recompute its numbers, per Jeremy's 2026-10-26 decision ("refresh to today's rules ... and publish without his review"). Session `session:cma`, branch `cma/JEG-925` (continues `research/position-weights`, PR #837).

Done:
- Text follows today's rules: league-wide bench seats by projected points times a usage discount (JEG-1121, #957) replace D'Hondt over draft ratios (inputs, alternatives item 8, limits 2 and 3); the abstract names DDF Charted Value and DDF Projected Value and the fit labels; Step 3 says a source that has not published for the current week drops out of the weights.
- New `tools/research_post9_numbers.py` regenerates every table in the post from the Python reference. It exits 2 when any of the seven sources is excluded at PPR/12.
- A status note at the top of the post says the tables are the 2026-10-25 numbers and must not be quoted until they are rerun.

Not done, and why: the numbers were not replaced. On today's fixture the four trade charts are "not yet published for week 8" (JEG-1175), so `included` at PPR/12 is espn, cbsros and razzball only and the weights are projections-only. Publishing those would present an outage as the method (AGENTS.md: no number in a research post until the ticket that fixes its inputs is live).

### Verified (check named)
- `python3 tools/research_post9_numbers.py` exits 2 on this fixture, naming usatoday, fantasycalc, fantasypros and cbs as "not yet published for week 8"; `--allow-partial` writes the JSON (exit 0).
- Partial run (diagnostic only, not quoted in the post): PPR/12 `slot_fill` QB bench 8, RB 33, WR 33, TE 10; `starter_mix_mean` QB 6.7 equals the mean of the three projections' 7.1, 8.0 and 5.0, confirming the weights are projection-only today.
- Partial run: turning the promotion model off (JEG-1142 open) moves PPR/12 position totals by at most 0.8 points (RB 43.9 to 43.1).

### Claimed, not confirmed
- That the post's other qualitative claims (superflex roughly triples the quarterback share; bench size barely moves the position split) still hold under the new bench rule. They are rechecked when the tables are regenerated.
- `docs/methodology.md` VP-2 still describes bench seats as D'Hondt; it was not updated with JEG-1121. Not changed here (method doc, separate ticket).
