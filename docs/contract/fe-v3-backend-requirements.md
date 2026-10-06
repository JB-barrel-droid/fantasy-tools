# Trade Dashboard v2 (Figma) — what the backend must supply

Source: Figma "Trade Dashboard v2 – Design Review"
(file `fCffo4EdZgUBkoVb7cQdr3`). Jeremy shared it on 2026-10-06; Claude read it
in the layer panel. It is read together with decision **league-settings-001**:
one saved league setup (12 teams, standard roster) per scoring format, with
everything else derived in the browser. The read surfaces are those in
`fe-read-contract-v1.md` (JEG-327).

This file lists what the design needs from the backend. For each need it says
whether contract v1 already covers it. Visual and layout choices belong to the
design and are not repeated here.

## What the design asks the reader to control

| Control (frame) | Values | Where the numbers come from |
|---|---|---|
| Scoring (12 "Your league") | Std / Half / Full | Saved; one 12-team block per scoring |
| Teams (12) | 8 / 10 / 12 / 14 | Derived in the browser from the 12-team inputs |
| Roster steppers (12) | QB, RB, WR, TE, FLEX, SUPERFLEX | Derived in the browser |
| Bench slots (11 "Weights & bench") | Stepper, inside backend-supplied bounds | Derived; bounds from the backend |
| Method per source | "Our Data Driven Adjustments" (default) · Indexed · Pure VORP | See the pair registry below. Copy rule copy-vorp-001: the shipped label must read "VORP vs waivers", not the design's "Pure VORP". |
| Weeks | Current week by default; the movers view also uses the prior week | Saved per week |

## Requirements

### R1. A pair registry that gives a reason when a pair is unavailable

The design says pair availability comes from the registry, and that an
unavailable source × method pair shows a reason.

- Allowed pairs in the design: FantasyCalc, FantasyPros, CBS and USA Today
  offer adjustments or Indexed. ESPN, CBS ROS and Razzball offer adjustments
  or Pure VORP.
- **Need:** one row per (source, method). Each row carries `available`
  (bool), `reason_code` and `reason_text` when it is unavailable, and the
  data vintage the pair would use.
- **Contract v1:** partial. `api.product_options` carries key lists
  (`adjusted_indexed_keys`, `pure_vorp_keys`, `as_published_keys`), but has no
  per-pair availability and no reason. **Gap.**
- **Reason codes to support:** `stale_vintage` (older week, R5),
  `not_offered` (the method doesn't apply to this source), and
  `insufficient_overlap` (fewer than `min_shared_for_pie` shared players).
  `league_setting_unsupported` is no longer needed once derivation (R3)
  ships. Until then the chart shows sources as unavailable at 8/10/14
  teams.

### R2. Feasible bench bounds

The design says the backend supplies feasible bench bounds.

- **Need:** for a given scoring, teams and roster, the minimum and maximum
  bench size (and the bench share) that the value model can price without
  a position going infeasible.
- **Contract v1:** `bench_share` has a global `[0.01, 0.30]` interval. Its
  per-position `feasible_interval` is marked "future". **Gap.** The bounds
  depend on the league the reader chooses, so they must be computable in
  the browser from saved inputs: ship the rule and its inputs, not one
  stored row per setup (league-settings-001).

### R3. Saved inputs that let every league setting be derived

- **Need:** at 12 teams per scoring, the native values per source plus the
  translation parameters. The browser then reproduces every team count,
  roster and bench setting.
- **Contract v1 / inventory:** `docs/league-settings-inventory.md` shows
  every view can be derived from the saved 12-team inputs. The server-only
  translation (`pipelines/vorp_translation/unified.py`) still needs a
  versioned JavaScript port, checked against the JEG-364 test vectors.
  **Gap: JEG-332 steps 2–3.**
- FantasyCalc already saves only 12 teams (#361, JEG-427).

### R4. The prior week's base, for movers

The design says movers recompute both weeks using the current league and
weights.

- **Need:** for each source, the same saved 12-team inputs for the prior
  week, so the browser applies identical settings to both weeks. Stored
  movers computed at a fixed league are not enough.
- **Contract v1:** the snapshot is single-week (`is_active`). History rows
  are kept, but there is no read surface for "previous active". **Gap:**
  expose `api.player_values` (inputs grain) for `week = current - 1`, plus
  that week's snapshot metadata.

### R5. Freshness metadata, with older weeks excluded on first load

The design excludes older-week sources from the first load.

- **Need:** per source, `content_vintage` and `week_designated` against the
  current content week. Use the content calendar (`pipelines/nfl_week.py`,
  which flips on Tuesday), not the watchdog calendar (GAP-WEEK-CALENDARS).
  Also needed: a flag for "older than the current week", so the first load
  leaves those sources out and the registry (R1) gives the reason
  `stale_vintage`.
- **Contract v1:** `api.product_snapshot.sources[*]` has `week_designated`
  and `content_vintage`. It has no derived current/older flag, and no
  statement of which calendar applies. **Small gap.**

### R6. Trades sum per series, with no blended score

- **Need:** none beyond R3. A trade total is computed per source series in
  the browser. The backend must not publish a blended "consensus" value
  for trades.
- **Contract v1:** compatible.

## Order of work

1. R5, then R1, since the registry uses R5's stale flag and can ship
   against current data.
2. R3 (JEG-332 steps 2–3), which unblocks 8/10/14 teams and the roster
   steppers.
3. R2, which needs R3's translation in the browser.
4. R4, which needs R3 so the same derivation runs on both weeks.

Each item adds to the contract as a minor version (`fe-read-contract-v1.md`
§7).
