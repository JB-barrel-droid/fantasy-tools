# Player identity model (JEG-438)

Jeremy, 2026-10-07: "All player name concepts should tie back to the player name
table. The player name table should be built (if not already) to capture the
extensive NFL universe. All partial solves for player name should be replaced
with a tie to the player name table. Mapping for how different sources name
players should be maintained. Fuzzy logic should be used for temporary
mismatches with a job running each night to get true matches. Though this should
be extreme edge cases."

## The model

| Piece | Where | What |
|---|---|---|
| Canonical table | `public.players` (Supabase) | One row per NFL player. `player_key` (bigint, unique) is the identity everything joins on. 4,646 rows on 2026-10-07: every position, active and recent inactive (seeded from nflverse, extended by hand and now by the nightly job). |
| Cross-ids | `public.external_id_map` | Source ids to `players.id`: sleeper 3,969, nflverse/gsis 4,613, espn 1,196, yahoo 1,201. The nightly job adds missing ones. |
| Name mappings | `public.player_name_aliases` (new) | How each source spells a player: `source` (`*` = any source), `source_player_name`, `position` (`''` = any), optional `source_player_id`, `player_key`, `status`, `method`, `confidence`, timestamps. Grain `(source, norm_name, position)`. |
| Run log | `public.player_identity_reconcile_runs` (new) | Per-source counts from each nightly run. |
| Open names | `public.player_identity_unresolved_v` (new view) | Provisional / unmatched / review counts per source. |
| Snapshot | `data/inputs/player_registry.json` | The three tables above, exported by `pipelines/export_player_registry.py`. What the resolver reads in CI and locally. Refreshed by the nightly job. |
| Resolver | `pipelines/lib/player_resolver.py` | The only code that turns a name or source id into a `player_key`. |

Alias `status`:

- `verified`: safe to use (a hand-checked mapping, a backfilled one, or a nightly promotion with independent evidence).
- `provisional`: a fuzzy temporary match. Used, flagged, and re-checked every night. Never becomes verified without independent evidence.
- `unmatched`: no candidate at all. Key is null.
- `review`: ambiguous, a position conflict, or still unconfirmed after 3 days. Human queue.
- `rejected`: a provisional match the nightly job disproved. The resolver will not propose that key for that name again.

The old manual identity table (`public.player_identities` + `player_identity_aliases`, exported as `data/inputs/player_identity_map.json`) and the Sleeper base (`data/inputs/sleeper_identity_base.json`) were backfilled into `player_name_aliases` / `external_id_map`. They remain in place, read-only and no longer authoritative, until every reader is migrated (see the inventory).

## Resolver API

```python
from lib.player_resolver import get_resolver, name_label
r = get_resolver()                       # cached; reads data/inputs/player_registry.json
res = r.resolve("Kenny Gainwell", source="fantasycalc", pos="RB", team="PIT",
                source_id=None, id_type=None, allow_provisional=True)
res.player_key   # 785
res.status       # verified | exact | provisional | unmatched | ambiguous | position_conflict
res.method       # source_id | xref:sleeper | alias:fantasycalc | alias:* | canonical:exact|nickname|compact | fuzzy | dst
r.resolve_dst("Seahawks D/ST")           # team defenses
r.canonical_name(785)                    # display name: always players.full_name
r.write_pending("output/identity/pending-<source>.json")
r.flush_pending(sbclient)                # provisional/unmatched -> player_name_aliases
```

Order (first step with exactly one player wins):

1. **Source id**: an alias row for `(source, source_player_id)`, else a cross-id (`sleeper`, `espn`, `yahoo`, `gsis`).
2. **Alias**: a verified alias for this source, then for `*`. A provisional alias resolves as provisional.
3. **Canonical**: `players.full_name` at three spellings, in order: exact key, nickname-expanded first name (`kenny` to `kenneth`), and space-free (`smith njigba` = `smithnjigba`). Within a spelling: position filter, then active over inactive, then team. Two players left means ambiguous: stop, never guess.
4. **Fuzzy**: only when step 3 found no candidate at any spelling. It needs the same last name, a compatible first name (equal, nickname, prefix of 3 or more letters, or the same initial plus similarity), the position the caller gave, a score of at least 0.90, and a 0.05 lead over the next candidate. The result is `provisional`. It is recorded in `pending`, and savers send it to `player_name_aliases`.

Normalization (`norm_key`) is the single rule: ASCII-fold, lowercase, drop apostrophes and periods, other punctuation to spaces, drop a trailing generational suffix. `name_label()` (= `norm_key`) is the stored `player_norm` label written next to a key. It is a label only and must never be used as a join key.

## Nightly reconcile

`.github/workflows/player-identity-reconcile.yml` is dispatched by pg_cron `player-identity-reconcile-nightly` (08:23 UTC). It runs `pipelines/reconcile_player_identity.py --mode write` and then `export_player_registry.py`, and commits the snapshot to main if it changed.

1. **Universe sync** (Sleeper `/players/nfl`): every rostered, Active, fantasy-position Sleeper player that `players` already holds gets its missing sleeper/espn/gsis/yahoo ids. A held player is one matched by an existing cross-id or by an exact name at the same position, never by fuzzy. Nothing is inserted by this step, so Sleeper's stale "active" ghosts (retired players still listed with a team) stay out.
2. **Re-resolve** every provisional, unmatched and review alias, using independent evidence only (fuzzy off):
   - Found: the alias becomes `verified`. A provisional that disagrees is replaced, and the old key is noted.
   - Sleeper has exactly one active player of that name at that position: the alias becomes `verified` to that player. If `players` does not hold the player yet, the player is inserted with the next `player_key` plus cross-ids. This is how the universe grows, and only for names a source actually uses.
   - Otherwise, after 3 days, the alias moves to `review`.
3. **Monitoring**: one row per source in `player_identity_reconcile_runs`, and check `player_identity_reconcile` via `monitoring_record_observation`. `ok` means the job ran green. `content_ok` means open names (provisional + unmatched + review, seen in the last 14 days) are at or below 5 per source and 15 in total. A breach is recorded as `IDENTITY_OPEN_NAMES`.

The schedule and check row are in `supabase/migrations/jeg438_identity_reconcile_cron.sql`. Apply that file right after the workflow merges: a dispatch before then would 404.

## Inventory of partial solves (2026-10-07)

The guard `tests/test_single_player_resolver.py` scans `pipelines/` and `producers/`. Its `LEGACY` ratchet holds whatever is not yet migrated. A new offender fails the guard, and so does a LEGACY entry that no longer offends.

Identity resolution (source name to key):

| File | Partial solve | Stage |
|---|---|---|
| `pipelines/lib/canonical_players.py` | `norm_plain`, `norm_player_name`, its own Registry, alias overrides from `player_identity_map.json` | 3: delegates to the resolver |
| `pipelines/lib/layered_identity.py` | manual map + Sleeper base layers | 3: retired |
| `pipelines/lib/identity_map_guard.py` | guards writes to `player_identity_map.json` | 3: retired with the map |
| `pipelines/match_source_snapshot.py` | `normalize_name`, `identity_keys`, `resolve_identity`, Sleeper layer, roster name join | 3 |
| `pipelines/save_{espn_cbs,cbsros,razzball,fantasycalc,usatoday,fantasypros}_references.py` | per-saver `resolve_name` / name index / `ALIASES` / razzball `compact` | 3 |
| `pipelines/pull_espn_projections.py` | `resolve_identity` over the identity map | 3 |
| `pipelines/refresh_fantasycalc_supabase.py` | `normalize_name` = `lower().strip()` label | 3 |
| `pipelines/bake_players.py` | `canonical_players.resolve` + `norm_plain` labels | 3 (via canonical_players) |
| `pipelines/build_ddf_two_tier_leg.py`, `build_cbsros_ddf_leg.py`, `build_razzball_ddf_leg.py` | fixture `player_keys` name map + `ALIASES` | 3 |
| `pipelines/pull_cbs_ros_projections.py`, `pull_razzball_ros.py`, `load_ddf_leg_to_supabase.py` | `norm_plain` labels written as `player_norm` | 3 |
| `pipelines/ingest_player_news.py` | `normalize_phrase` name index | 3 |
| `pipelines/refresh_players_espn_fields.py` | local `norm` | 3 |
| `producers/build_staged_bundle_espn.py` | `_norm` + identity map | 3 |
| `pipelines/rebuild_fp_fixture_section.py`, `rebuild_fp_natives_from_snapshot.py` | local `normalize` | 3 |
| `pipelines/translate_via_vorp.py` | `resolve_key` slug/name map | 3 |
| `pipelines/build_player_trace.py` | `norm_name` | 3 |

QA and diagnostic joins (two name-keyed sets compared with each other) are also replaced by resolving both sides to keys: `build_espn_input_comparison.py`, `build_source_value_lineage.py`, `review_comparison_candidate.py`, `scrape_live_source_pages.py`, `vorp_translation/unified.py`, and the inline `.lower()` slug compares in `check_source_fidelity.py`.

Out of scope: `waiver_wire/` and `weekly_vegas/` (separate products, Weekly Signals paused) carry their own `canonical_players.py` copies and `identity.py`. Risk register: GAP-IDENTITY-LEGACY.

## Known unmatched names (JEG-438) and how they resolve now

| Name | Key | How |
|---|---|---|
| Kenny Gainwell | 785 Kenneth Gainwell | nickname spelling; verified `*` alias |
| Joshua Palmer | 822 Josh Palmer | nickname spelling; verified `*` alias |
| Chigoziem Okonkwo | 4247 Chig Okonkwo | verified `*` alias |
| Jalen Cropper | 1268 Jalen Moreno-Cropper | verified `*` alias |
| J. Sturdivant | 2201 J. Michael Sturdivant | verified `*` alias |
| Mitch Trubisky | 4214 Mitchell Trubisky | verified `*` alias |
| Audric Estime | 4642 | `players` has exactly one; Sleeper's two records were the ambiguity |
| Tyreek Hill / Joe Mixon | 3081 / 3735 | resolve by name. "No ESPN anchor" means ESPN publishes no projection for them, which is a data gap and not an identity gap. |

Two backfilled aliases stay in `review`: Riley Nowakowski (the old table said RB, `players` says TE) and Jackson Meeks (old table TE, `players` WR). They are real position disagreements for a human to settle.
