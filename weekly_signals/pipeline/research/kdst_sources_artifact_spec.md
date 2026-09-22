# K/DST Integration Spec for trade-value-sources Web Artifact

## Background
The chart universe now includes 34 kickers (K) and 32 team defenses (DST) alongside 529 QB/RB/WR/TE (595 total). The data pipeline (`build_compare_dashboard_data.py` and `build_sources_dashboard.py`) has been updated to include K/DST. The `sources_data.json` now contains:
- 595 players in our/ecr/vegas legs (was 529)
- `position_coverage` metadata on each source (see below)
- K/DST have ECR values (DDF numbers) but null Monday values (not yet seeded in Monday legs)

## Data File
Updated `sources_data.json` is at:
`~/workspace/goals/football-signal-database-and-app/lottery/results/sources_data.json`
Copy to `~/workspace/ts-spaces/trade-value-sources/assets/sources_data.json`

## Source Position Coverage (from JSON metadata)
- **fantasycalc**: "QB/RB/WR/TE only — no K/DST coverage (not covered)"
- **usatoday**: "QB/RB/WR/TE only — no K/DST coverage (not covered)"
- **cbs**: "QB/RB/WR/TE only — no K/DST coverage (not covered)"
- **ecr**: "QB/RB/WR/TE/K/DST — full coverage. K: FantasyPros season ECR. DST: FantasyPros season ECR."
- **vegas**: "QB/RB/WR/TE: direct season-long fantasy lines where books price them. K: no season-long market; weekly kicker props (Odds API) available when quota permits. DST: NO direct market exists — DST Vegas leg is DERIVED from opponent implied points (spread/total), never a direct DST market read."

## Required HTML Changes

### 1. Source Cards: Display Position Coverage
In the source card template (line ~302), add a new detail row after the "Cadence" row:
```html
<div class="detail-row"><dt>Coverage</dt><dd>${esc(s.position_coverage || "—")}</dd></div>
```
This uses the `position_coverage` field from the JSON source metadata.

### 2. Table: "Not Covered" for K/DST in FC/USAT/CBS Columns
Currently `formatSourceValue` (line 227) renders null/undefined as "—" (em dash).
For K/DST rows in the fantasycalc, usatoday, and cbs columns, display **"not covered"** instead of "—".

Implementation: In the table cell rendering for source columns, check if the player position is K or DST AND the source is one of fantasycalc/usatoday/cbs AND the value is null. If so, render `<span class="not-covered">not covered</span>` instead of "—".

Add CSS:
```css
.not-covered{color:var(--muted);font-style:italic;font-size:11px}
```

### 3. DST Vegas Label: Mark as Derived
Wherever the Vegas column header or source card mentions DST, ensure the "derived" nature is clear. The `position_coverage` text already states this. No additional label needed beyond the coverage row, but verify the Vegas source card displays the full coverage text.

### 4. Position Filter: Include K/DST
If the dashboard has a position filter, ensure K and DST are included as filter options alongside QB/RB/WR/TE.

## Verification
- K/DST rows appear in the table with DDF (our) values
- FantasyCalc/USA Today/CBS columns show "not covered" (not "—", not blank, not 0) for K/DST
- Source cards display the position coverage text
- No K/DST values are fabricated or synthesized for uncovered sources

## Do NOT Publish
Leave as draft. The parent agent will handle publishing after verification.
