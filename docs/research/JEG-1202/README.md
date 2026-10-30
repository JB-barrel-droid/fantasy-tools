# JEG-1202 audit: ESPN, Sleeper and Yahoo player spellings

Ready bounded phase only (Linear JEG-1202, 2026-10-29). Read-only: no canonical
table, alias list, resolver, parser, MCP runtime, Supabase or production data
was changed. This is evidence for the later mapping work, not that work.

## Answer first

- Committed evidence covers platform spellings for very few players. Of 1,614
  canonical QB/RB/WR/TE/K/DST keys: Sleeper 929 (from the Sleeper players pull,
  tied to keys by id), ESPN 80, Yahoo 24 (both only from a few scrubbed page
  pastes). Every other cell is `missing`, and missing is not coverage.
- The shared resolver (`canonical_players.resolve_with_reason`) gets every
  grounded spelling right except 4, all pinned in the tests as known gaps
  (12 when the audit was built; the 8 ESPN `"<Team> D/ST"` spellings resolve
  since JEG-1350, below):
  - ~~8 ESPN `"<Team> D/ST"` spellings resolve to nothing.~~ Fixed in
    JEG-1350: `norm_player_name` keeps the `/`, so the DST path now accepts
    `d/st` beside `dst|defense|def` in both its detection and suffix rules.
    The 8 resolve to their DST keys; an unknown team's `D/ST` stays unmatched.
  - 3 Sleeper spellings resolve to a different player_key:
    `Nyheim Miller-Hines` (id-linked to 2785 Nyheim Hines, resolver gives 4653),
    `Jody Fortson` (437 Joseph Fortson, resolver 4655), `Mitch Tinsley`
    (4363 Mitchell Tinsley, resolver 4660). 4653/4655/4660 are gsis-less
    public.players rows whose full_name is exactly the Sleeper spelling: likely
    second rows for one person. Needs a decision before any mapping write.
  - 1 Sleeper spelling fails closed: `Tyron Billy-Johnson` (id-linked to 423
    Tyron Johnson) is unmatched.
- 3 paste spellings have no independent ground and are not counted:
  `Aaron Jones Sr.` (ESPN and Yahoo, MIN RB) and `Kyle Pitts Sr.` (ESPN, ATL TE).
  The resolver gives 164 and 1970, but nothing outside the resolver confirms it.

## Files

| File | What it is |
| -- | -- |
| `coverage_matrix.csv` | One row per canonical player_key (QB/RB/WR/TE/K/DST): canonical name, per-platform status, spelling, ground, evidence (file:line or sleeper_id), resolver result. |
| `summary.json` | Counts, status by position, ungrounded observations, refused id links, suspected duplicate rows. |
| `build_matrix.py` | Rebuilds every file here and in `tests/fixtures/JEG-1202/`; `--check` fails on drift. |
| `tests/fixtures/JEG-1202/platform_observations.json` | Every ESPN and Yahoo spelling extracted from the pastes, with file, line, raw line, ground and resolver result. |
| `tests/fixtures/JEG-1202/resolver_cases.json` | 695 cases with a grounded expectation, tagged punctuation, suffix, nickname, collision, unknown, source_disagreement. |
| `tests/test_jeg1202_platform_spellings.py` | Offline unittest (7 tests, about 0.3 s). |

Statuses: `same` (platform text equals the canonical full_name byte for byte),
`differs` (grounded to this key, different text), `multiple` (more than one
grounded text for the key), `link_conflict` (id layers disagree), `missing`
(no committed evidence). Resolver cells: `ok`, a fail-closed reason
(`unmatched`, `ambiguous`, ...), or `other_key:<key>`.

## Evidence used

| Platform | Source | Date |
| -- | -- | -- |
| canonical | `data/inputs/players_identity_snapshot.json` (SELECT of public.players: player_key, full_name, position, gsis_id; 4,702 rows) | no date in the file; last commit 730ceb0, 2026-10-23 |
| canonical active | `data/inputs/players_active_snapshot.json` (SELECT player_key, active; JEG-1313) | `pulled_at` 2026-10-29T20:19:29Z |
| Sleeper | `data/inputs/sleeper_identity_base.json` (Sleeper `/players/nfl`, 4,234 QB/RB/WR/TE/K players) | `meta.pulled_at` 2026-10-09T18:46:05Z |
| Sleeper ids | `data/inputs/sleeper_projection_idmap.csv` (sleeper_id -> gsis -> player_key, exact ids only, JEG-949) | commit 730ceb0, 2026-10-23 |
| ESPN | `tests/fixtures/roster_paste/espn-team.txt`, `espn-matchup.txt` (scrubbed real page pastes) | commit c754026, 2026-10-22 |
| ESPN | `tests/fixtures/league_paste/espn-league-rosters.txt` and `-split-record.txt` (a real league's rosters, team names scrubbed; same rosters twice) | commit ad8a08b, 2026-10-25 |
| Yahoo | `tests/fixtures/roster_paste/yahoo-team.txt`, `yahoo-matchup.txt` (scrubbed real page pastes) | commit c754026, 2026-10-22 |
| aliases | `data/inputs/player_aliases.json` (read for the verified_alias ground and by the resolver) | per-entry `verified` dates |

## Evidence excluded, and why

- `data/inputs/espn_projections.csv`: its `player` column is the identity
  snapshot's display name written by `pull_espn_projections.py`, not ESPN's
  `fullName`. ESPN's raw spellings are not committed anywhere.
- `tests/fixtures/league_paste/yahoo-league-rosters.txt` and
  `sleeper-league-rosters.txt`: built by hand to mimic each site's layout from
  the ESPN rosters (`tests/test_v2_league_paste.js` header), so not platform text.
- `tests/fixtures/noisy_paste/*` (synthetic chrome, per `test_v2_extract_players.js`),
  `tests/fixtures/waivers_paste/*-SYNTHETIC.txt`, `tests/fixtures/league/*.json`
  (canonical names from `data/fixtures/current/players.json`).
- Sleeper's `espn_id` and `yahoo_id` fields: platform ids, not spellings.

## How a spelling is tied to a player_key

Never by the resolver under test and never by similarity. A paste spelling
needs one of: `exact_canonical` (equals one snapshot full_name at the pasted
position), `sleeper_exact` (equals one id-linked Sleeper name at the same
position and team), `verified_alias` (equals an alias text, same position),
`dst_mascot` (one snapshot DST whose last word is the mascot). A Sleeper
spelling needs `sleeper_idmap` (status matched) or `sleeper_gsis` (Sleeper's
own gsis_id equals exactly one snapshot gsis_id). The idmap's own rules win: a
sleeper_id it marks `conflict` or `name_review` is not linked, and a gsis-only
link must keep the last name. That refused one link: Sleeper 5094 `Ryan Izzo`
carries Tyler Conklin's gsis_id (idmap status conflict).

Yahoo name lines carry page chrome (`Player Note`, `Video Forecast`, ...) and
sometimes an injury code glued to the name (`Jeremiyah LoveQ`). The extractor
strips the known chrome and a trailing Q/O/D/IR/PUP/NA/SUSP/NFI after a
lowercase letter or period, and records `status_stripped:<code>` on the
observation (4 rows) so a reviewer can check each one against its raw line.

## Gap inventory for the later mapping work

1. ESPN raw spellings: none committed beyond about 80 players in pastes. A
   later phase needs ESPN `fullName` with ESPN ids saved by a puller (owner
   to name; `pull_espn_projections.py` currently drops the raw name).
2. Yahoo spellings: about 24 players, pastes only. No Yahoo pull exists.
3. Sleeper: 653 of 1,582 QB/RB/WR/TE/K keys have no Sleeper link; 596 of them
   have a gsis_id, but the Sleeper base carries gsis for only 1,322 players
   and the idmap covers only players with Sleeper projections. DST has no
   Sleeper evidence (the base pulls QB/RB/WR/TE/K).
4. ~~ESPN `D/ST` suffix fails closed in the shared resolver (8 teams here).~~
   Done in JEG-1350 (691 pass, 4 known gaps).
5. Suspected duplicate public.players rows (gsis-less, Sleeper spelling):
   4653 vs 2785, 4655 vs 437, 4660 vs 4363, and 4661 vs 1155 (Ben VanSumeren,
   same text, different snapshot positions). Production write: Jeremy's yes.
6. `Tyron Billy-Johnson` (Sleeper) needs a verified alias or stays unmatched.
7. `Aaron Jones Sr.` and `Kyle Pitts Sr.` need a ground (an id-bearing ESPN or
   Yahoo source) before they count.
8. ~~The snapshot has no `active` column, so offline every row is inactive and
   cross-position namesakes without a position read `ambiguous` (18 cases).~~
   Done in JEG-1313: `data/inputs/players_active_snapshot.json` saves
   public.players `active` (read-only SELECT, 2026-10-29T20:19:29Z, 2,126 of
   4,702 active) with a digest of the identity snapshot's rows; the build
   refuses it if the identity snapshot changes. With it, 8 of the 18 resolve
   to their one active row (Ben VanSumeren 4661, DeVonta Smith 764, Joshua
   Williams 1070, Leroy Watson IV 4658, Marvin Jones Jr. 4648, Michael Carter
   II 777, Spencer Brown 4032, Tyler Davis 4127); 10 stay `ambiguous`. Pass
   and known-gap counts are unchanged (683 pass, 12 known gaps).
9. Separate name matchers outside the shared resolver, read but untouched:
   `app/v2/roster-paste.js` (own `NICK_MAP`, own D/ST stripping) and
   `supabase/functions/mcp/names.ts` (own key/suffix rules). The feature's
   "route parsers/MCP through the shared resolver" step is still open.
10. ~~The new test is not in a Makefile target.~~ JEG-1313 runs it in
    `test-unit-modules` (the full suite in preview CI), not `test-core`: it is
    an audit, and AGENTS.md keeps the deploy gate to the data math. The drift
    check skips with a rebuild note when the workflow-refreshed Sleeper base
    moves past the matrix.

## Refresh ownership (as committed today)

| Input | Refreshed by | Owner |
| -- | -- | -- |
| `sleeper_identity_base.json` | `.github/workflows/sleeper-identity-refresh.yml`, pg_cron `sleeper-identity-refresh-live` Tue/Thu 09:17 UTC | automated, commits to main |
| `players_identity_snapshot.json` | by hand (`sleeper_projection_idmap.py` docstring: "SELECT of public.players") | none named |
| `players_active_snapshot.json` | by hand, re-pulled with the identity snapshot (the build refuses a mismatched pair) | none named |
| `sleeper_projection_idmap.csv` | `python3 pipelines/sleeper_projection_idmap.py --fetch`, by hand | none named (JEG-949) |
| `player_aliases.json` / public.player_name_aliases curated rows | curated by hand; nightly `player-identity-reconcile` only proposes | Jeremy's yes for production writes |
| ESPN / Yahoo paste fixtures | by hand, scrubbed | none named |

## Commands

```
python3 docs/research/JEG-1202/build_matrix.py --check
python3 -m unittest tests.test_jeg1202_platform_spellings -v
python3 -m unittest tests.test_player_aliases
```

`build_matrix.py` forces `PLAYER_ALIASES_SOURCE=json` and builds the registry
from the snapshot rows, so neither command reads Supabase or the network. The
test also replaces the Supabase readers with guards for its run.
