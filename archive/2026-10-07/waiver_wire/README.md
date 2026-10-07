# waiver_wire — Waiver Dashboard + pipeline

The "pick them up off the waiver wire" product: a weekly waiver board
(add / don't-add / drop) built from the lottery-ticket option-value model.

## Segmentation

This tree is **segmented off from the trade-value chart**. It is a sibling
tree, not a subdirectory of any trade-value code, and it is self-contained:

- Every module the build chain imports ships inside `pipeline/` (`bin/` +
  `engine/`). Nothing is imported from the trade-value chart's source dirs.
- The single cross-tree relationship is a **read-only input**: the board
  prices players through the chart's frozen blend, read from the published
  fixture `data/fixtures/current/players.json` (resolved via
  `pipeline/bin/chart_paths.py`, overridable with `CHART_PLAYERS_JSON`).
  The waiver tree never writes into trade-value directories.
- `weekly_vegas/` (the Vegas-vs-ECR weekly signals tree) is likewise a
  separate sibling. Shared concepts (canonical player identity) are copied,
  not referenced, so each tree stands alone.

## Layout

- `dashboard/index.html` — self-contained export of the Waiver Dashboard
  page (Hatch artifact `waiver-dashboard`; renders "Week 2 Waiver Board").
- `pipeline/bin/` — the build chain:
  - `build_waiver_dashboard_data.py` — assembles the dashboard data file.
    One value-change re-ranking drives the whole board: adds (waiver-available,
    roster < 70%), don't-adds (hype, model-grounded rejection), drops
    (bottom of the same re-ranking, paired with the adds).
  - `impute_monday_tv.py` — Monday leg imputation (`results/imputed_proj_<scoring>.json`).
  - `waiver_boundary.py` — the real waiver-pool logic (roster% boundary).
  - `waiver_delta.py` — week-over-week viability-tier movement (Monday-safe:
    no fresh ECR required).
  - `board_week.py` — board week label/stems, never hardcoded.
  - `coverage_check.py` — fail-closed player-universe coverage audit (C1–C9).
  - `render_board.py` — regenerates the markdown/JSON board from the DB view.
  - `audit_waiver.py`, `audit_waiver_bake.py` — waiver audits.
  - `build_kdst_streamers.py` — K/DST streamer section.
  - `starter_model.py`, `leg_files.py`, `identity.py`, `chart_paths.py` —
    shared pipeline helpers (copied, not referenced).
- `pipeline/engine/` — `espn_roster.py` (ESPN roster%), `sb_rest.py`
  (Supabase REST), `canonical_players.py` (numeric player-key identity).
- `pipeline/sql/` — lottery/waiver table DDL.
- `cron/weekly-refresh.md` — refresh runbook.

## Runtime inputs (not in the repo)

- Chart fixture `players.json` (read-only, see above).
- `WAIVER_SIGNALS_JSON` — weekly Vegas signals file (defaults to the legacy
  absolute path; override per checkout).
- `IDENTITY_SNAPSHOT` — curated identity snapshot for alias overrides.
- Supabase credentials via the `supabase-mgmt` / `supabase-football-signal`
  skills (resolved from `~/workspace/skills`, override per environment).
- ESPN/Sleeper APIs (free, keyless).

## Copy rules (inherited)

- Public side is "Vegas", never "the market". Say "ECR", never the provider
  brand. Never publish on a known flaw. Free sources first.
