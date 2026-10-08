# K/DST VORP group contract (DRAFT for Jeremy's design decision)

> **Superseded 2026-10-08 (GAP-029).** Jeremy reconfirmed JEG-211 and chose to stop carrying K/DST anywhere in the pipeline. Kept as the historical record; the code it describes was removed (revival point: commit dac0ff2).

JEG-211. This records the group definitions, units, source availability and
role/cutoff rules that any K/DST work must follow. Nothing here approves a
build or a render change — the three-view chart ships without K/DST until the
separate inclusion design is decided. Source audit: `docs/kdst-source-audit.md`.

## Standing constraints this contract honors

- The 8 skill groups (QB/RB/WR/TE x starter/bench) are a closed contract. K/DST
  never enter skill-group arithmetic: skill totals, group maps and the
  shared-batch70 anchor are byte-identical whether K/DST data is present or
  absent. No division by an absent group can ever throw.
- `build_imputed_vorps.py` admits exactly QB/RB/WR/TE and raises on any other
  position. K/DST must stay that way until a separate reviewed producer exists.
- ESPN-purity: anywhere the pipeline labels data ESPN, the numbers come from
  ESPN projections only. ECR K/DST is hard-excluded (matches
  `docs/supabase-source-mapping.md`). No modeled or inferred publisher values.
- Method note on units: raw VORP units are surplus PPG above the waiver line
  (`reweight_reference.py` contract). K/DST use the same units only where they
  exist.

## Group definitions (proposed, not approved)

K and DST are each a single-tier two-group structure: `(K, starter)`,
`(K, bench)`, `(DST, starter)`, `(DST, bench)`. Rationale: leagues start
exactly one K and one DST, so the dedicated/bench split mirrors the skill
positions; flex never applies. This keeps the proportional allocation code
shape unchanged (group = (position, role)) if a producer is ever wired.

Roster-shape rule: a K/DST roster config is a separate manifest, never a
variant of the publisher 12-team shape. Example default: teams=12, K slots=1,
DST slots=1, bench_total = league-measured bench K/DST count, scoring=
"scoring_invariant" (K/DST projections do not move with PPR).

## Source availability (verified 2026-10-01, see audit)

- ESPN projections: the ONLY publisher with K/DST numbers (45 K, 32 DST ROS in
  `players.json`, `pricing: espn_only`). Pull dated 2026-09-21 — stale. Fresh
  pull needed before anything is surfaced.
- FantasyCalc, USA Today, FantasyPros trade values, CBS, CBS ROS, Razzball,
  prediction markets, ECR: zero K/DST rows in our pulls. There is no peer to
  compare against, so an "adjusted" or "agreement" view is meaningless for K/DST.
- Measured economics: K+DST are ~2% of the ESPN pie; kicker top-over-replacement
  1.15x, defense 1.26x — a value-above-waivers curve is nearly flat. One
  scoring-invariant number each, so all three scoring views would be identical.

## Role/cutoff rules

- Publisher K/DST: dedicated K = top `teams` kickers by native ROS; dedicated
  DST = top `teams` defenses; bench = next `bench_total` by native ROS; the
  rest are Cut with explicit 0 and native preserved (same contract as skill Cut).
- Granular (ESPN) K/DST: same tier/waiver-line surplus method as the skill
  groups (`raw_surplus_ppg`): group pools are surplus above the ESPN K/DST
  waiver line, nothing blended or modeled.
- Unavailable computation is never numeric zero: rows with no publisher price
  are absent with an explicit reason, not 0.
- Vintage rule: content date recorded from the source pull; stale data blocks
  surfacing the same way the injury gate blocks Sat/Sun builds.

## Display contract (when enabled — gray by default, approval required)

- Gray/de-emphasized rows with a footnote: "K/DST shown from ESPN projections
  only (pulled <date>); no peer source to compare." The approved label copy for
  the reason is Jeremy's call.
- K/DST are excluded from the `fixedPieIndexed` guard (`sourceScaleAgreement` was
  retired 2026-10-08, GAP-026) —
  the skill pie never moves because of them.

## Options (no silent choice — see audit for full reasoning)

1. Gray-only ESPN rows (audit option 2). 2. Separate K/DST section with own axis
   (audit option 2 variant). 3. Honest exclusion with plain explanation next to
   the existing toggle (audit option 1, smallest). Rejected: joining the skill
   pie (would move every skill value for 2% uncalibrated share); modeled values.

## Open for Jeremy

1. Gray rows vs honest exclusion vs separate section.
2. Approve a fresh ESPN K/DST pull + recorded `meta.kdst_snapshot` before any surfacing.
3. Whether a K/DST producer contract (`option-c-kdst-manifest-v1`) should be
   built now or parked with the three-view release.
