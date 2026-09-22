# Sleeper weekly projections endpoint — K/DEF validation

Validated 2026-09-16 against `https://api.sleeper.com/projections/nfl/2026/{week}?season_type=regular&position[]={K|DEF}`.
Source: `company: "rotowire"`. Undocumented endpoint — schema assertions required; fail closed if keys disappear.

## 1) Availability / row counts

- Week 2 K: **200 OK, 157 rows** (payload ~99 KB)
- Week 2 DEF: **200 OK, 32 rows** (payload ~31 KB)
- Week 1 K: **200 OK, 157 rows** — returns a week-1 snapshot (date 2026-09-09), NOT empty. Category is still `"proj"` even for the past week, so historical weeks are projection snapshots, not actuals.
- All rows: `category: "proj"`, `season_type: "regular"`, `gp: 1.0`.

**Filler-row trap:** of the 157 K rows, 124 are ADP-only filler (team=null, stats={adp_dd_ppr:999}), and 4 more have a team but stats={adp_dd_ppr} only (Kessman CAR, Krieg GB, Smyth NO, Matsuzawa LV). Usable projection rows = **33**. A pipeline consumer MUST filter: keep rows with a real stats payload (require `pts_std` in stats), not just team non-null.

- K usable: 33 rows, 32 teams covered; **NYJ has 2 projected kickers** (Jason Sanders + Blake Grupe) — presumably a competition/injury split. Decide one-per-team or split handling before use.
- DEF usable: 32/32 teams, each `player_id` = team abbreviation (e.g. `"BUF"`); player name = full team name ("Buffalo Bills").

## 2) Exact field names

### K `stats` keys (verbatim)

```
adp_dd_ppr, fga, fgm, fgm_20_29, fgm_30_39, fgm_40_49, fgm_yds,
fgmiss_30_39, fgmiss_40_49, gp, pos_adp_dd_ppr,
pts_half_ppr, pts_ppr, pts_std, xpa, xpm, xpmiss
```

### DEF `stats` keys (verbatim)

```
adp_dd_ppr, blk_kick, def_fum_td, def_kr_yd, def_pr_yd, def_td, ff,
fum_rec, gp, int, pass_int_td, pos_adp_dd_ppr, pr_yd,
pts_allow, pts_allow_21_27, pts_half_ppr, pts_ppr, pts_std,
sack, tkl_loss, yds_allow, yds_allow_350_399
```

### Row-level keys (both positions, verbatim)

```
category, company, date, game_id, last_modified, opponent, player,
player_id, season, season_type, sport, stats, status, team,
updated_at, week, week_shard
```

## 3) Weekly vs full-season

**Weekly.** `gp: 1.0` on every row; magnitudes are single-game scale (K: fgm ~1.4–1.8, xpm ~2.5–3.0; DEF: pts_allow ~24.5, yds_allow ~390, sack ~2.6). The `pts_*` fields are Rotowire's own weekly fantasy-point rollups, not recomputable from a standard scoring formula — spot check: Bass fgm*3+xpm = 8.25 vs pts_std 6.61; BUF sack+2*int+2*fr+6*def_td = 6.1 vs pts_std 7.02. Do not trust the `pts_*` values under our own K/DST scoring; recompute points from the component fields with the league's weights.

## 4) Schema surprises vs expectations

| Expectation | Reality |
|---|---|
| distance bands incl. 50+ | Only bands present: `fgm_20_29`, `fgm_30_39`, `fgm_40_49`, `fgm_yds` (mean make distance). **No 50+ band, no sub-20 band.** |
| miss stats | Only `fgmiss_30_39`, `fgmiss_40_49`, `xpmiss`. Total fga − fgm ≠ fgmiss_30_39 + fgmiss_40_49 (Bass: fga 2.14, fgm 1.82, counted misses 0.08 — the rest are short/long misses with no band split). |
| safety / bracket points on DEF | **No safeties field.** Bracket expectations are pre-aggregated as indicators: `pts_allow_21_27: 1.0`, `yds_allow_350_399: 1.0` (binary flags, not probabilities across multiple brackets — only the most-likely bracket row appears). |
| return yards | `def_kr_yd` / `def_pr_yd` / `pr_yd` present — relevant only for return-yardage leagues, ignore otherwise. |
| td splits | `def_td` (all defensive TDs) plus sub-splits `def_fum_td`, `pass_int_td`; use `def_td` to avoid double counting. |
| `pts_ppr` vs `pts_std` vs `pts_half_ppr` | **Identical across all three on every row** — Rotowire's one number; PPR-irrelevant positions get no distinction. |
| one kicker per team | NYJ has two (Sanders, Grupe) in week 2. |

Notes: `date` on week-2 rows is the week's game date (2026-09-17); `last_modified` epoch-ms is the actual refresh timestamp (1789601425295 ≈ this week). `opponent` and `game_id` (`202610204` format) are present for matchup mapping. `week_shard: "2_5"` appears to be an internal shard label — ignore.

## 5) Week parameter behavior

- `week=2` → current week projection snapshot (200).
- `week=1` → 200 with 157 rows (32 projected + 125 filler), dated 2026-09-09, category still `"proj"`. **Past weeks return the projection snapshot, not empty and not actuals.** Useful as a projection-history archive; do NOT treat as actuals.
- No other week values tested (task said a handful of requests). Safe assumption: integer 1–18 accepted, returns that week's projection snapshot.

## Recommendation for the K/DST build

Usable as a **secondary weekly projection check and demand signal**, as planned — NOT primary. Consume:
- K: `fga`, `fgm`, band makes, `fgm_yds`, `xpa`, `xpm`, `opponent`, `game_id`, `last_modified`.
- DEF: `sack`, `int`, `ff`, `fum_rec`, `blk_kick`, `def_td`, `pts_allow`, `yds_allow` + bracket indicator flags, `opponent`, `game_id`, `last_modified`.
- Ignore `pts_*` (opaque, non-recomputable); apply our own scoring weights to components.
- Filter rows on `"pts_std" in stats` (kills 128 filler rows).
- Guard on: `company == "rotowire"` (source could change), presence of `fgm`/`sack` keys, row counts ≥32 DEFs / ≥33 Ks — fail closed otherwise.
- Handle the NYJ-style double-kicker week explicitly (prefer the higher-fgm row or flag for review).
- Combine with the known FP DST lesson: season baseline already exists in `v_fp_season_kdst_latest`; Sleeper gives the weekly check.

## Example rows (verbatim, week 2)

K — Tyler Bass (BUF), opponent DET:
```json
"stats": {"adp_dd_ppr": 999.0, "fga": 2.14, "fgm": 1.82, "fgm_20_29": 0.32,
 "fgm_30_39": 0.43, "fgm_40_49": 0.43, "fgm_yds": 46.88,
 "fgmiss_30_39": 0.04, "fgmiss_40_49": 0.04, "gp": 1.0,
 "pos_adp_dd_ppr": 999.0, "pts_half_ppr": 6.61, "pts_ppr": 6.61,
 "pts_std": 6.61, "xpa": 2.92, "xpm": 2.79, "xpmiss": 0.13}
```

DEF — Buffalo Bills (BUF), opponent DET:
```json
"stats": {"adp_dd_ppr": 999.0, "blk_kick": 0.06, "def_fum_td": 0.06,
 "def_kr_yd": 105.62, "def_pr_yd": 122.91, "def_td": 0.13, "ff": 0.78,
 "fum_rec": 0.58, "gp": 1.0, "int": 0.78, "pass_int_td": 0.06,
 "pos_adp_dd_ppr": 999.0, "pr_yd": 17.29, "pts_allow": 24.5,
 "pts_allow_21_27": 1.0, "pts_half_ppr": 7.02, "pts_ppr": 7.02,
 "pts_std": 7.02, "sack": 2.6, "tkl_loss": 4.87, "yds_allow": 392.8,
 "yds_allow_350_399": 1.0}
```
