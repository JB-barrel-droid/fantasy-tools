## 2026-10-08 - Math review agenda (docs/math-review-agenda, documentation only)

Jeremy: "we will need to do a full math and logic review when everything else
is working ... One off questions won't result in the right outcomes."

### What changed
- New `docs/math-review-agenda.md`: 14 items (MR-01 to MR-14). Each item gives
  the question, why it matters (which numbers), current behaviour, options with
  measured effects where any exist (cited to the log or test), and
  dependencies. It also has a suggested order of seven stages and a "How the
  review runs" section: freeze one build, use the math inspector, decide in
  dependency order, record each decision in decisions.md and methodology.md,
  then one implementation pass plus the 12-combo sweep.
- `docs/methodology.md`: linked from "Detailed Rule Owners" and from the
  "Other chart views" paragraph ("the recipe awaits his review").
- `docs/risk-register.md`: new rows GAP-MIGRATION-CBS-BAKES-ORDER and
  GAP-FIXEDPIE-SKIPS-PUBLISHED.
- No code or data changed.

### Sources read
docs/methodology.md, manifesto.md, decisions.md, risk-register.md, every
docs/claude-log/2026-10-0*.md on main; origin/fix/weeks-tidy (its log and
migration); origin/feat/refresh-cadence (methodology diff, no value math);
feat/superflex and feat/math-inspector (merged, logs on main); the local
fix/views-invariants work-in-progress commit 007d07e (not pushed: test
docstring and engine comments only).

### Verified (check named)
- **fixedPieIndexed vs the measured Indexed gaps.** Code read on origin/main:
  - `fixedPieDiagnostics` (curve-widget.js:3883) returns `ok:true` for every
    AS_PUBLISHED_KEYS source without computing a total.
  - `proportional_scaling_vorp_overlap`, the function its comment cites, is
    defined nowhere under `pipelines/` (grep).
  - Published Indexed values are `translate_ranked`'s
    `vorp * our_max[pos] / max_vorp` (unified.py:508), with no total factor.
  - Conclusion: the guard's green and the inspector's -31%..+26% gaps are
    both true. This is the reconciliation the brief asked for (MR-01).
- **CBS ROS health checks.** `python3 -m unittest
  tests.test_jeg68_starter_markup tests.test_jeg69_direction_check` on
  origin/main: 3 failures.
  - Direction: Full PPR 8 share 0.8681 and Standard 10 share 0.8609.
  - Stale pins: knife edge 0.8452 vs pinned 0.8534; fixture n 350 vs 349.
  - These figures are cited in MR-10.
- **Migration blocker.** Read `cbs_bakes_source_urls_20261008.sql` on
  origin/fix/weeks-tidy: it drops `cbs_trade_values_grain_uidx`, adds a
  unique index including `bake_id`, and sets `bake_id` NOT NULL. main's
  `save_espn_cbs_references.py` writes no `bake_id` (grep) and upserts on
  `CBS_UPSERT_CONFLICT`.

### Claimed, not confirmed
- Every other number in the agenda is quoted from the cited logs; I did not
  re-run their sweeps.
- The views-invariants descriptions come from an unpushed WIP commit's
  comments and test docstring. That lane may change them before pushing.
- The exact failure mode of main's CBS upsert after the migration (no
  matching conflict target vs NOT NULL violation) was reasoned from the SQL,
  not executed.
