# ESPN roster% — K/DST extension: live verification notes

Draft patch: `espn_kdst_patch.diff` (same directory). **Not applied** — draft only,
no pipeline code was modified. All API calls below were read-only GETs against the
public no-auth endpoint, 2026-09-16 ~18:36 CT.

## What was verified live

Endpoint:
`https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2026/segments/0/leaguedefaults/3?scoringPeriodId=0&view=kona_player_info`
with `X-Fantasy-Filter` players filter, `X-Fantasy-Source: kona` (curl via subprocess,
same as the existing module — python urllib still 403s).

| Test | Filter | Result |
|---|---|---|
| Slot 17 only | `filterSlotIds: [17]` | 10/10 kickers (Brandon Aubrey 99.36, Jason Myers 97.18, Cameron Dicker 97.13, Ka'imi Fairbairn 94.7, Harrison Mevis 88.6, Cam Little 87.99, …), `defaultPositionId: 5`, `eligibleSlots: [17, 20, 21]` |
| Slot 16 only | `filterSlotIds: [16]` | 10/10 D/STs ("Seahawks D/ST" 98.0, "Texans D/ST" 96.03, "Steelers D/ST" 94.07, "Broncos D/ST" 93.88, …), `defaultPositionId: 16`, `eligibleSlots: [16, 20, 21]` |
| Combined | `filterSlotIds: [16, 17]`, limit 1000 | **90 rows: 58 kickers + 32 D/ST**, slot-filter pure (only `defaultPositionId` 5 and 16 present) |
| Position-id filter | `filterPositionIds: [5]` | Same kickers as slot 17 — both filter styles work; slot ids keep the module's existing convention |
| The slot-5 trap | `filterSlotIds: [5]` | **Returns wide receivers** (Amon-Ra St. Brown, Jaxon Smith-Njigba, Puka Nacua, CeeDee Lamb) — slot 5 is a WR lineup slot in this league template. ESPN "position id 5" (kicker) is `defaultPositionId`, not a lineup slot. A naive `+5` to the filter would silently pollute the cache with WRs |

- `player.ownership.percentOwned` present on **all 90 rows** (zero missing).
- `sortPercOwned` sorts kickers and D/STs together globally — they interleave correctly; no position bias, no pagination concern (90 rows ≪ 1000/page).
- D/ST naming is uniform: `"<Mascot> D/ST"` for all 32 teams, including the
  digit-mascot `"49ers D/ST"` — the same mascot-regex lesson the FP DST loader
  already encodes. All 32 match `^[A-Za-z0-9 ]+ D/ST$`.
- Kicker universe is wider than the FP season projections: **58 kickers, of which
  24 are unsigned free agents** (`proTeamId: 0` — Justin Tucker, Younghoe Koo,
  Jake Moody, Brandon McManus, Matt Prater, Greg Zuerlein, …). FP season CSV had
  34 kickers. Downstream matching decides coverage; the cache just carries them.
- `proTeamId` → abbreviation mapping verified live across all 32 D/ST rows
  (name/proTeamId pairs, e.g. 25→"49ers D/ST", 6→"Cowboys D/ST", 21→"Eagles D/ST"):
  1 ATL, 2 BUF, 3 CHI, 4 CIN, 5 CLE, 6 DAL, 7 DEN, 8 DET, 9 GB, 10 TEN, 11 IND,
  12 KC, 13 LV, 14 LAR, 15 MIA, 16 MIN, 17 NE, 18 NO, 19 NYG, 20 NYJ, 21 PHI,
  22 ARI, 23 PIT, 24 LAC, 25 SF, 26 SEA, 27 TB, 28 WAS, 29 CAR, 30 JAX, 33 BAL,
  34 HOU. The patch's `MASCOT_ABBR` uses these abbreviations (consistent with the
  Supabase `teams` table set and the Yahoo loader: LAR/LAC/JAX/WAS/ARI/LV/SF).

## What the patch changes

1. `POS_IDS` gains `"K": 17, "DST": 16` — the only filter change needed. Existing
   QB/RB/WR/TE slot values are untouched (verified: slot 5 ≠ kicker).
2. New `DST_RE` / `MASCOT_ABBR` / `dst_entity_key()`: maps `"Bills D/ST"` →
   canonical lookup key `"dst:buf"` (lowercase). Raises `KeyError` on an unmapped
   mascot (fail-closed against an ESPN rename).
3. `build_lookup()` keys each D/ST under a third canonical key alongside the two
   existing normalizations. Kickers flow through the existing name-normalization
   path unchanged.
4. `load()` gains a fail-closed guard: fewer than 32 D/ST rows → refuse to write
   the cache (mirrors the existing "refusing to write an empty cache" guard).
5. Docstring documents the slot-id vs defaultPositionId trap and the new cache
   keying.

Cache format stays `display name → percentOwned`; the next pull on cache miss
grows the file from 950 rows (2026-09-15 cache, no K/DST) to ~1040 rows. No
pagination, sleep, or curl changes needed.

## Draft validation (throwaway copies only — real file untouched)

- `patch -p2` applies the diff to a pristine copy with zero fuzz/rejects.
- `dst_entity_key` unit checks: `Bills D/ST`→`dst:buf`, `49ers D/ST`→`dst:sf`,
  `Commanders D/ST`→`dst:was`, non-DST name→`None`, renamed mascot→`KeyError`.
- `build_lookup` over the 90 live rows: 32 `dst:` keys, values match the raw
  cache; kicker name norms and all pre-existing lookup keys unchanged.
- `load()` with a simulated 0-D/ST pull raises and writes no cache file.

## Downstream flags for the parent (not part of this patch)

- Coverage resolution (C6: ESPN roster% ≥ 15) must look up D/STs via the new
  `"dst:<abbr>"` keys; FP's entity key is uppercase `"dst:BUF"` — lowercase
  before lookup.
- Kicker matching is by normalized player name (`norm_name`/`score_norm`), same
  as skill positions; FP K entity keys are `k:<player UUID>`, so the name→UUID
  join stays wherever the FP K/DST pipeline resolves identities.
- The 24 unsigned-FA kickers (`proTeamId: 0`) will sit in the cache; harmless
  unless a consumer assumes every cached name is rosterable.
- Suggested follow-up hardening (not in the diff): `coverage_check.py` C6
  extended so all 32 `"dst:<abbr>"` keys resolve, mirroring the skill-position
  coverage check.
