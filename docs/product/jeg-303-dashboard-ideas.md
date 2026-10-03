# JEG-303 — Trade-value dashboard ideas (scoping)

Lane: minimax (M3). Source ticket: JEG-303.
Purpose: scope the fantasy-manager questions the datasets in this repo can
already answer, and a ranked list of scoped enhancement proposals for user
value. This is a **scoping** doc — it does not change methodology, values, or
published copy. Anything that would change the published economics or copy
is flagged as needing Jeremy's call.

Repo evidence was read at `data/fixtures/current/players.json` (meta +
`dataset_status`), `data/fixtures/current/compare_data.json`, and
`data/fixtures/current/source-import-health.json`. The Supabase landing tables
in the import-health file (`public.cbs_trade_values`,
`public.espn_season_projections`, `public.source_trade_values`) confirm the
same legs that feed the fixtures.

---

## Part A — Questions answerable today

Each row names the manager question, the dataset(s) that answer it, where that
data lives in the repo (or in Supabase), and the one-line "how a manager uses
it." "Current model value" throughout means the 100% ECR-sourced
`blend_ros`/`blend_ppg` per `players.json:meta.method_note`.

### A1. "Is this player a buy-low or sell-high candidate?"
**Datasets:** primary value (`blend_ros`), ESPN projection delta
(`delta_espn_ecr` / `delta_espn_ecr_ppg`), prediction-market delta
(`delta_pm_ecr` / `delta_pm_ecr_ppg`), Razzball delta
(`delta_rz_ecr` / `delta_rz_ecr_ppg`).
**Where:** `data/fixtures/current/players.json` (per-player field group),
`data/fixtures/current/compare_data.json` (`players[].{ecr,espn,pm,rz}`).
**Use:** a wide negative delta means sources the books/experts price him lower
than the consensus — sell-high candidate. A wide positive delta means sources
disagree in the player's favor — buy-low candidate. The
`disagree_baseline_note` in `players.json:meta` controls the shading, and
`espn_adj_ppg` puts ESPN on the experts' level so the rank gap is real.

### A2. "Where is the market disagreeing on him — by source?"
**Datasets:** the four source legs (ECR, ESPN, PM, Razzball) plus the
external sources (CBS, CBS ROS, FantasyCalc, FantasyPros, USA Today).
**Where:** `data/fixtures/current/compare_data.json` holds the four in-pipeline
legs; `data/fixtures/current/source-import-health.json` enumerates the seven
external raw legs and their landing Supabase tables
(`public.source_trade_values` for fantasycalc/fantasypros/usatoday,
`public.cbs_trade_values` for cbs, `public.espn_season_projections` for espn).
**Use:** the disagreement view already leads with this; per the AGENTS.md unit
of interest, this is the surface the dashboard is built around. Sources within
~1 point collapse into one line — the chart stays a single clean market number.

### A3. "What's his actual vs expected split this week?"
**Datasets:** weekly actuals files (`actuals_2026-09-16.json`,
`actuals_2026-09-17.json`, `actuals_2026-09-22.json`) plus the Monday-form
`monday_note` field in `compare_data.json:players[].monday_note` and the
`actuals_note`/`ppg_note` in `players.json:meta`.
**Where:** `data/fixtures/current/actuals_*.json`, `compare_data.json` per
player.
**Use:** the `monday_note` strings call out role vs projection splits ("role
underneath is thinner than the points", "scored 4.1 under expected"), which
is the readable summary of the underlying actuals-vs-expected ratio.

### A4. "What's my fair return in this trade?"
**Datasets:** the 12-combo matrix in `sources_data.json` (`combos.standard_8`,
`combos.standard_10`, `combos.standard_12`, `combos.standard_14`,
`half_*`, `full_*`).
**Where:** `data/fixtures/current/sources_data.json`.
**Use:** the Trade Calculator already reads this — three scorings × four
roster sizes, each giving a current-model value on the team's chosen number
of teams. Per `sources_data.json:value_weeks`, only the Monday, ECR, ESPN, and
PM legs carry per-week values in this slice (Razzball is null here).

### A5. "Has his value actually moved since the last bake?"
**Datasets:** `prior_blend_ros` and the `prior` block of `dataset_status`
entries in `players.json`. The `our_value` entry reports a prior-vs-current
delta summary at the player level.
**Where:** `players.json:meta.dataset_status[our_value].prior` plus per-player
`prior_blend_ros` field.
**Use:** a small median move means the chart is steady; a 5+ point move on
a starter-tier player is worth a tweet or a Trade Designer nudge. The
`expert_leg_note` separates the ECR-only move (279/532 moved vs 2026-09-21 in
the snapshot read) from the full-bake move.

### A6. "What's his risk profile across sources?"
**Datasets:** same as A2 — the spread across ECR/ESPN/PM/RZ is the
per-player disagreement, and `cross_method.daily_*` and `cross_source_agreement`
artifacts capture it in baked form.
**Where:** `pipelines/build_cross_source_agreement.py` (source leg);
`data/fixtures/current/players.json` carries the per-player disagreement
columns already.
**Use:** a player whose sources agree within ~1 point has a tight market; one
with a 10+ point spread is a volatile name worth flagging.

### A7. "Is the data under this chart healthy today?"
**Datasets:** `dataset_status` summary block (`live`, `stale`, `pending`,
`hidden_in_ui`) and the per-dataset `status` / `stale` / `freshness` /
`completeness` entries.
**Where:** `players.json:meta.dataset_status` (six live, zero stale, six
pending, seven hidden in the as-of-2026-09-23 read).
**Use:** the existing "Data health: what's under this chart" UI panel pulls
from this. A `stale: true` row would suppress the relevant view, per the
ECR entry's `ui_note` ("Hidden while stale: pricing-model picker, curve ECR
model, side-by-side view, value/PPG disagreement lenses and the Trade
Designer's perceived-value column").

### A8. "What is Vegas pricing for him?"
**Datasets:** prediction-market ROS/PPG columns (`pm_ros`, `pm_ppg`,
`pm_filled_ros`, `pm_filled_ppg`) and the `pm_covered` list of priced
components.
**Where:** `data/fixtures/current/players.json` (`pm_*` per-player fields,
`pm_snapshot` in meta), `compare_data.json:players[].pm`.
**Use:** the AGENTS.md standing constraint is "the market side is always
Vegas" — the PM leg is the read of where the books (Kalshi/Polymarket season
ladders, with the local liquidity gate) sit. The `pm_note` documents why
pass-catchers' pure PM reads exclude reception points by construction
(no liquid two-sided season receptions market).

### A9. "What's the freshest week we're charting?"
**Datasets:** `as_of`, `ecr_snapshot`, `ecr_content_date`,
`prior_ecr_snapshot`, `espn_snapshot`, `pm_snapshot`, `rz_snapshot` and the
`nfl_week` derived in the cron path.
**Where:** `players.json:meta` snapshots; `compare_data.json:meta` (older
set: `ecr_snapshot`, `espn_snapshot`, `pm_snapshot`, `rz_covered`); the
import-health `nfl_week` (`4` in the 2026-10-01 read).
**Use:** "as of 2026-09-23 (chart), experts from 2026-09-22" is the kind of
one-liner the dashboard's freshness strip surfaces.

### A10. "Has there been news about him this week?"
**Datasets:** `player-news.json`.
**Where:** `data/fixtures/current/player-news.json` (289 KB).
**Use:** news-driven role changes feed into the Monday-form adjustment
path; an injury flag the manager would want to see before a trade offer.

---

## Part B — Suggested enhancements (ranked by value-per-effort)

Each row: user question answered, data it needs (exists today vs needs
building), rough build shape (which repo areas it touches), why it matters in
Jeremy's product terms (unit of interest = disagreement, chart = one clean
market number, sources within ~1 pt collapse into one). Proposals that would
need a methodology or copy call are flagged.

### B1. Disagreement Watchlist (top movers on spread)
**Question:** "Which players is the market most disagreed on this week?"
**Data:** already exists — the four-leg spread from `compare_data.json` plus
the cross-source agreement artifact
(`pipelines/build_cross_source_agreement.py`).
**Build shape:** a thin new view on top of the existing
`players.json`/`compare_data.json` disagreement columns; UI hook under the
disagreement lens (no new pipeline). Pulls the top-N by |spread|.
**Why it matters:** the disagreement is the unit of interest per AGENTS.md;
a one-click "today's widest disagreements" panel is the most natural way for
a manager to find buy-low/sell-high candidates without scrolling the full
chart. Stays within the existing economics — no new methodology.
**Value-per-effort:** HIGH (data exists, view-only, fits existing UI slot).

### B2. Source-by-source explainer popover
**Question:** "What does each source's number actually mean, and why does
mine differ?"
**Data:** the per-source `method_description` blocks already in
`players.json:meta.dataset_status` — ECR, ESPN, PM, Razzball each carry a
one-line role and method description. The external sources (cbs, cbsros,
fantasycalc, fantasypros, usatoday) need short blurbs in a sibling
document but the underlying numbers already exist in
`source-import-health.json` and the landing Supabase tables.
**Build shape:** `docs/dashboard-copy/` or a small JSON block; UI renders it
on hover of each source label in the disagreement view. Pure copy + view
work — no pipeline change.
**Why it matters:** the brief calls out that disagreement is the unit of
interest; a manager who doesn't know what "PM" means can't act on a wide PM
spread. Stays in the established frame — no methodology change.
**Value-per-effort:** HIGH (mostly copy; needs a methodology/copy call for
the exact source blurbs — Jeremy's call, flagged).

### B3. Roster-size sensitivity on trade values (already baked, needs surfacing)
**Question:** "What's my fair return in a 14-team vs 8-team league?"
**Data:** exists today in `sources_data.json:combos.standard_8/10/12/14` and
the half/full siblings — twelve combos already computed.
**Build shape:** the Trade Calculator already reads this for the
calculator's chosen roster; surfacing the four roster sizes side-by-side in
the comparison lens (no new bake — just a view on the existing matrix) gives
managers the "what if my league is bigger" read.
**Why it matters:** the source `meta.vector` is "12-team, 1QB/2RB/3WR/1TE/1FLEX,
6 bench" — managers in 10- or 14-team leagues already ask "does this
still hold for me?" It's a view change, not an economics change.
**Value-per-effort:** HIGH (data already computed, view-only).

### B4. Freshness strip on the chart top
**Question:** "How stale is what I'm looking at?"
**Data:** already exists — `players.json:meta.{as_of,ecr_snapshot,espn_snapshot,
pm_snapshot,rz_snapshot}` plus the `dataset_status` summary
(`live`/`stale`/`pending` counts) and the per-dataset `stale` flags.
**Build shape:** small UI strip reading from the existing meta block; same
content as today's data-health panel but pinned to the top so the freshness
age is visible without a click.
**Why it matters:** per `dataset_status.ui_hint.start_collapsed: true`, the
existing panel is collapsed by default; the age of the chart is a question
asked first. View-only — no methodology.
**Value-per-effort:** MEDIUM-HIGH (data exists, view-only).

### B5. Player-level actuals trend (weekly line)
**Question:** "How has his actual production trended week-over-week?"
**Data:** `data/fixtures/current/actuals_2026-09-16.json`,
`actuals_2026-09-17.json`, `actuals_2026-09-22.json` already hold three
weeks of game logs. The `actuals_note` documents the 288-player actuals
subtraction scope (ECR leg only).
**Build shape:** a view that joins the three actuals files by player_key and
plots a small sparkline. No new pipeline — the joins are already done by
`build_values.py` for the bake. The actuals files themselves could grow
weekly as the season progresses; a thin incremental append is the only
pipeline work.
**Why it matters:** actuals-vs-expected is the existing driver of the
Monday-form `monday_note` strings; surfacing the trend at the player row
makes that signal legible without a hover. Stays in the existing frame.
**Value-per-effort:** MEDIUM (data exists; light pipeline work for the
weekly append; view is straightforward).

### B6. Cross-source agreement index at the row level
**Question:** "For this player, where do the sources line up and where do
they split?"
**Data:** the per-source columns and `delta_*` columns already exist in
`players.json`; the `cross_source_agreement` build
(`pipelines/build_cross_source_agreement.py`) already aggregates.
**Build shape:** a row-level "agreement badge" in the existing chart — a
visual cue when all four in-pipeline sources collapse within ~1 point (the
AGENTS.md "sources within ~1 point collapse into one" rule already does
this implicitly for the chart's headline number; surfacing the badge
explicitly makes the collapse legible).
**Why it matters:** the AGENTS.md rule that "sources within ~1 point
collapse into one" is implicit today; a visible badge operationalises it.
View-only — no methodology change.
**Value-per-effort:** MEDIUM (data exists, view-only, but needs a small
"what does the badge mean" copy line — copy call flagged).

### B7. Per-source disagreement lens side-by-side
**Question:** "Show me all four sources' value at once, not just the
collapsed one."
**Data:** already exists — `players.json` per-player ECR/ESPN/PM/RZ
columns plus the `monday` column from `compare_data.json`.
**Build shape:** the side-by-side view is referenced in the ECR
`ui_note` ("Hidden while stale: ... side-by-side view") — it's a
documented UI surface; the gating issue today is the staleness rule, not
the data. Once the data is healthy, surfacing it is view-only.
**Why it matters:** the AGENTS.md frame says "the chart stays one clean
market number" but the disagreement lens already pulls from these same
columns; making the four-side view first-class (when data is healthy) is
the natural reading for power users. No methodology change.
**Value-per-effort:** MEDIUM (gated on data health; view-only).

### B8. Prediction-market signal panel (read-only)
**Question:** "What is Vegas pricing this player at, and how does that move
with news?"
**Data:** already exists — `pm_ros`/`pm_ppg`/`pm_filled_*` and `pm_covered`
in `players.json`; `pm_snapshot` in meta. The `pm_note` documents the
liquidity gate and the receptions exclusion.
**Build shape:** a small "Vegas read" panel on the player row. The brand
is "Data Driven Football" and the market side is "Vegas" — the panel name
already exists in user-facing copy.
**Why it matters:** the standing AGENTS.md constraint is "the market side
is always Vegas" — making the Vegas leg first-class at the player row is
the natural reading of that rule. View-only — no methodology.
**Value-per-effort:** MEDIUM (data exists, view-only; needs copy framing).

### B9. Source-import health widget on the dashboard
**Question:** "Is one of the source feeds broken today?"
**Data:** `data/fixtures/current/source-import-health.json` already
enumerates seven sources (cbs, cbsros, espn, fantasycalc, fantasypros,
usatoday, plus the in-pipeline Razzball/PM/ECR) with status, row counts,
snapshot paths, and landing Supabase tables.
**Build shape:** a small status widget reading from the existing
`source-import-health.json` baked file. View-only.
**Why it matters:** the `dataset_status` panel surfaces our own data
freshness; the source-import health widget surfaces upstream feed
freshness. Stays in the existing "data health" frame.
**Value-per-effort:** MEDIUM (data exists, view-only).

### B10. Waiver priority calculator (live game-state dependent) — FLAGGED
**Question:** "Who should I prioritise on waivers this week given my
league's needs?"
**Data:** does NOT exist. The current datasets price rest-of-season value
(per `players.json:meta.ppg_note`: "Per-game points = ROS fantasy points /
team games remaining"). They do not price a specific week's game-state,
injury report, or team need.
**Build shape:** would require either (a) live NFL-week injury/lineup
feeds that are not in the current source list, or (b) a derived weekly
matchup signal that is not a current dataset. Either is a new pipeline,
not a view change.
**Why it matters:** real waiver decisions need a live game-state view the
rest-of-season dataset doesn't carry. This is **flagged as a Jeremy
methodology/copy call** — it would either introduce a new "this week"
value (changing the chart's economics) or stay strictly advisory (which
means the chart's one-clean-market-number frame is preserved but the
advisory's authority is unclear). Not a view-only change.
**Value-per-effort:** LOW for this repo's frame (would require new
economics or a new advisory lane — needs Jeremy's call).

### B11. Trade acceptance probability (counterparty model) — FLAGGED
**Question:** "Is my trade partner likely to accept this offer?"
**Data:** does NOT exist. The current datasets price what the player is
worth on our methodology; they do not model the counterparty's roster
state, team needs, or risk tolerance. The Trade Calculator recomputes
values for any league's rules but does not model acceptance.
**Build shape:** would need a counterparty-state model — a new dataset
or a derived signal over league season data we don't currently ingest.
**Why it matters:** "is this trade going to happen" is a different
question from "is this trade fair." The current frame (one clean
market number, the chart) answers the fair question well but does not
answer the accept question at all. **Flagged as a Jeremy methodology /
copy call** — adding it would either sit in a clearly separate advisory
lane (safe) or change the chart's voice (not safe without a call).
**Value-per-effort:** LOW for this repo's frame (new data needed;
advisory-lane framing needs Jeremy's call).

### B12. Positional scarcity view — FLAGGED
**Question:** "How deep is this position right now?"
**Data:** partially exists. The `shade_baseline_ppg` block in
`players.json:meta` already carries positional baselines; positional
waiver lines are part of the methodology.
**Build shape:** would be a view on existing positional waiver-line
math, but surfacing it as a "scarcity" widget would change the
user-facing interpretation of what those lines mean.
**Why it matters:** the methodology's positional waiver lines are
internal inputs today; the "scarcity" label is a user-facing
re-interpretation that needs Jeremy's copy call.
**Value-per-effort:** LOW (data exists, but the user-facing framing
changes — needs Jeremy's call).

---

## Counts

- Part A questions answerable today: **10** (A1–A10)
- Part B suggestions: **12** total
  - ranked top 3 by value-per-effort: **B1 (Disagreement Watchlist)**, **B2
   (Source explainer popover)**, **B3 (Roster-size sensitivity)**
  - flagged as needing Jeremy's methodology/copy call: **B2 (blurbs)**,
   **B6 (badge copy)**, **B10 (waiver calculator)**, **B11 (acceptance
   probability)**, **B12 (scarcity label)** — 5 items

## Items I could not ground in the repo

- **Player-level per-week actuals aggregation across all weeks.** The baked
  `actuals_2026-09-16.json`, `actuals_2026-09-17.json`, `actuals_2026-09-22.json`
  files exist and are referenced in `players.json:meta.actuals_note` ("YTD
  actuals subtracted from the ECR leg only — 288 players with banked
  stats"). A full per-player weekly sparkline view would join these three
  files; a fourth-week append is implied by the naming but not yet present
  in `data/fixtures/current/`. Flagged as **scope-dependent** — the
  pipeline support exists; whether the sparkline ships weekly or on-bake
  only is an editorial choice (not a methodology change), but I did not
  read a design doc that decides it.
- **Player-news structure.** `player-news.json` exists (289 KB) and is
  used as an upstream signal in the Monday-form adjustment path (per
  the `monday_note` strings in `compare_data.json`). I did not enumerate
  its schema in this scoping pass; a news-driven dashboard view would
  need a separate inventory pass.
- **Live waiver/injury feeds.** The seven external sources in
  `source-import-health.json` (cbs, cbsros, espn, fantasycalc,
  fantasypros, usatoday, plus Razzball/PM/ECR in-pipeline) are
  **projection** feeds. None of them is a live game-state feed. B10
  (waiver calculator) and B11 (acceptance probability) both depend on
  data the repo does not currently ingest.

## Files in this commit

- `docs/product/jeg-303-dashboard-ideas.md` (this file)

No other files changed. `git status` after commit shows ONLY this new doc.