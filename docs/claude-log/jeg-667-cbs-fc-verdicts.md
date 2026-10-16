# JEG-667: CBS and FantasyCalc coverage-hold verdicts (2026-10-16)

Investigation only. No hold released, no `data/triage/coverage-accepted.json` edit, no floor change, no code change.

## CBS (source `cbs` = Dave Richard's trade-chart article, not `cbsros`)

Note: `pipelines/pull_cbs_ros_projections.py` is the `cbsros` projections puller, a different source. The `cbs` hold comes from `ops/watchdog/pull_cbs.py` + `pipelines/save_espn_cbs_references.py::build_cbs_rows`.

Verified (live fetch of the published pages, parsed with the repo's own `parse_tables`):

- Week 6 article (`dave-richards-2026-week-6-trade-chart`, published 2026-10-14T12:39Z, modified 13:14Z) vs week 5, raw table rows: QB 36 vs 35, RB 47 vs 44, WR 44 vs 45, TE 15 vs 15. List length is NOT trimmed.
- What changed is the half-PPR column. Raw HTML has `<td>--</td>` in the `non` and `0.5` columns (PPR still a number) for: WR Josh Downs, Devaughn Vele, Keenan Allen (3); TE Colston Loveland, Harold Fannin Jr., Brenton Strange, Pat Freiermuth, Mark Andrews (5). Week 5 had 2 WR and 1 TE such rows.
- `build_cbs_rows` turns a non-numeric cell into a `missing_or_non_numeric_value` review row and prices no half_ppr value for that player. Arithmetic matches the candidate exactly: WR 44 - 3 = 41, TE 15 - 5 = 10.
- The other 4 of the 8 names are absent from the week 6 article entirely (0 matches in the raw page): Deebo Samuel Sr., Romeo Doubs (WR), Dalton Kincaid, Kenyon Sadiq (TE). Added in week 6: Jordyn Tyson, Marvin Harrison Jr. (WR), Brenton Strange, Pat Freiermuth (TE).
- Live Sleeper (2026-10-16): Samuel is Out (hamstring), Sadiq Questionable (concussion), Doubs/Kincaid/Downs/Loveland/Fannin/Vele healthy and Active. The 2026-10-09 base used by the triage tool is stale for Samuel and Sadiq.
- The parser is not at fault: no unparseable rows, all 4 tables parse, the 4 present names are parsed and then correctly skipped for a blank published value.

Verdict: (a) CBS changed its published list. Not a scrape/parse loss. Mixed: 4 players removed from the article, 4 kept but published with no half-PPR value. Nothing here is fixable in our code; CBS's published half column is blank for them.

## FantasyCalc (Malachi Fields)

Verified (Supabase read-only SQL on `public.source_trade_values`, bakes `fcwk6_*`, full / 1 QB / 12 teams; live API; identity files):

- Fields resolves fine (`player_identity_map`, `sleeper_identity_base`, FC id 13475 / Sleeper 13285; importer log: 0 review rows). Not an identity, key or position problem.
- FantasyCalc itself flips him in and out of its published list between pulls. Present in the 2026-10-13 05:05Z bake; absent from every bake 2026-10-13 13:07Z through 2026-10-15 20:05Z; present again from 2026-10-16 03:05Z on (native 6, 11, 8). Live API now: WR 74 of 76, value 7.
- The 2026-10-16 01:03Z review compared a candidate built from the absent-era bake against a live fetch made at review time, which already listed him. `verify_coverage_drop_live` calls a still-live dropped player a pipeline loss unless his live position rank is greater than the candidate's priced depth. Live WR list = 76 = candidate depth, so no live rank can exceed depth and a last-place tail player (value 7 against a top near 10,000) is always a "contradiction". Same mechanism as the JEG-436 Freiermuth case, which was fixed for a list that grew by one, not for a list whose membership swapped at constant size.
- The other 5 dropped players (Caleb Douglas, Chris Bell, De'Zhaun Stribling, Dohnte Meyers, Isaac TeSlaa) are absent from the live API too; Jaylin Noel is gone from live as well.
- The newest bakes have WR 77 (13:07Z), 76 (10:05Z), 75 (03:05Z) priced vs fixture floor 79, so a fresh candidate would not carry Fields as a drop.

Verdict: not a pipeline loss and not a matching bug; the reviewer's rank-vs-depth tail proxy cannot fire when the live list is no longer than the candidate. This is a gate-design gap, not a clear code bug, and fixing it loosens a hold gate (Jeremy's rule), so no PR was opened. FantasyCalc is no longer coverage-held (now a `publisher_vs_stored` fidelity hold).

## Claimed, not verified
- Why CBS blanked those half-PPR cells (CBS editorial choice assumed).
- Whether the FantasyCalc reviewer would pass with a fresh candidate (not run).
