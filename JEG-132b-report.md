# JEG-132b (R5b) report — input lineage mismatch checker

Lane: minimax (M3)
Branch: `minimax/jeg-132-lineage-checker`
Brief: `JEG-132b-brief.md`

## Files changed

- `pipelines/check_input_lineage.py` (new, 350 lines)
- `tests/test_input_lineage.py` (new, ~430 lines)
- `docs/claude-log.md` (appended a session entry)

`output/input-lineage.json` is written by the script at runtime; not
committed. No other files touched (sibling R5a builders and
`build_pipeline_checkpoints.py` / `promote_comparison_section.py` left
alone, as instructed).

## What the checker does

The sibling R5a writers stamp an immutable `lineage` block
(`raw_vintage`, `raw_content_sha256`, `raw_built_at`, `vintage_source`)
on every derived section at build time. R5b is the detector: for each
derived section it recomputes what the current raw input looks like and
compares field-by-field. Every R5a-helper is reused from
`pipelines/lib/lineage_block.py` — the triple definition, the SHA-256
over `(player_key, native, reindexed)` triples, and the
`resolve_raw_vintage` fallback chain are not reimplemented.

Derived-section coverage:

| Derived key                          | Raw input                              | Collector                          |
|-------------------------------------|----------------------------------------|------------------------------------|
| `{fantasycalc,usatoday,fantasypros,cbs}_adjusted` | the parent raw fixture section (`fantasycalc`, `usatoday`, etc.) | `collect_fixture_section_triples` |
| `espn`                              | freshest `data/ddf-two-tier/*-espn-/ddf_leg_espn.json`     | `collect_leg_triples`              |
| `cbsros`                            | freshest `data/ddf-two-tier/*-cbsros-/ddf_leg_cbsros.json` | `collect_leg_triples`              |
| `razzball`                          | freshest `data/ddf-two-tier/*-razzball-/ddf_leg_razzball.json` | `collect_leg_triples`         |
| `output/comparison-candidates/*.json` (candidate sections) | the reference artifact(s) recorded in `input_reference` | `collect_reference_triples` |

Raw sections (`fantasycalc`, `usatoday`, `fantasypros`, `cbs`) MUST NOT
carry a lineage block — they are inputs, not derivations. The checker
does not look at raw sections. A derived section WITHOUT a `lineage`
block is a mismatch (missing provenance is not a pass, per the brief).

Mismatch reasons emitted:

- `missing_lineage_block`
- `lineage_{raw_vintage,raw_content_sha256,raw_built_at,vintage_source}_mismatch`
- `raw_parent_missing` (the raw input the derived section should match)
- `leg_raw_missing` (no leg file found under `data/ddf-two-tier/`)
- `reference_raw_missing` (candidate's `input_reference` path missing)
- `fixture_missing` (the `--fixture` path itself not found)

## CLI

```
python3 pipelines/check_input_lineage.py [--fixture PATH] [--output PATH]
```

Defaults: `--fixture data/fixtures/current/comparison-sources-data.json`,
`--output output/input-lineage.json`.

Exit codes:
- `0` — every derived section's lineage matches the current raw input.
- `1` — at least one named mismatch (never silent; printed to stderr AND
  recorded in the artifact).

## Artifact shape (`output/input-lineage.json`)

The exact contract the sequenced render brief will consume:

```json
{
  "generated_at": "2026-10-02T12:00:00Z",
  "mismatches": [
    {
      "section": "cbsros",
      "reason": "lineage_raw_vintage_mismatch",
      "claimed": "Week 3",
      "actual": "Week 4"
    }
  ],
  "checked": 7
}
```

`claimed` / `actual` are present for per-field drift; absent for the
"missing whole thing" cases (so the JSON stays tidy: a single key when
only one is informative).

## Commands run + outputs

Sandbox restrictions: cannot execute the test runner (`python3 -m
unittest`), no `pytest`, no Linear CLI. `python3 -m py_compile` was
attempted on both new files (output below) — this is the only executable
check available in this sandbox.

VERIFIED:
- `python3 -m py_compile pipelines/check_input_lineage.py` → exit 0
  (syntax-only; checked structure parses).
- `python3 -m py_compile tests/test_input_lineage.py` → exit 0
  (syntax-only).

UNVERIFIED (require a runner outside this sandbox):
- `python3 -m unittest tests.test_input_lineage -v` — the 9 tests
  across 6 classes (TestCheckerModule, TestStateA_MissingLineageBlock,
  TestStateB_AdjustedVintageMismatch, TestStateC_CbsrosRealWorldCase,
  TestStateD_ShaMismatch, TestInvariants) were written but not executed
  here.
- `python3 pipelines/check_input_lineage.py --fixture <CBS-ROS 4h-lag fixture>`
  — the acceptance case the brief names, not executed here.
- `make validate` — out of scope per the brief (reviewer runs it).

The earlier session entries' standing reason applies: the runtime here
cannot prompt for permission to run the test runner, and the
unittest/pytest imports + runner execution are not exposed. The
reviewer runs the suite.

## Regression guards (states A–D)

Each guard constructs its own fixture (the brief warned the R5a
integration may not yet be live; the tests must stand alone). The
fixtures shape raw fixture sections exactly like the live
`comparison-sources-data.json` so the checker's existing
derived→raw mapping works without changes.

- **A** — `_adjusted` section with `lineage` removed → exit 1;
  `mismatches` names that section with `reason: "missing_lineage_block"`.
  Companion test strips lineage only on `fantasycalc_adjusted` and
  asserts the other three are not named, so the test discriminates
  between "all four flagged" and "the actually-broken one named".
- **B** — Raws carry `content_vintage: "Week 4"`; the four `_adjusted`
  sections carry `lineage.raw_vintage: "Week 3"`. Expected: exit 1,
  all four named with `reason: "lineage_raw_vintage_mismatch"`.
- **C** — Real CBS-ROS lag case (the 2026-10-02 incident): the leg is
  fresh (`content_vintage: "Week 4"`, current `generated_at`); the
  `cbsros` section's lineage claims `raw_vintage: "Week 3"` but its SHA
  is recomputable from the leg (so the SHA passes; the test discriminates
  that this is specifically the vintage mismatch). Expected: exit 1,
  exactly one `cbsros` mismatch with `reason: "lineage_raw_vintage_mismatch"`,
  `claimed: "Week 3"`, `actual: "Week 4"`.
- **D** — All four `_adjusted` sections carry the right `raw_vintage` and
  `vintage_source` but a sabotaged SHA (`"0" * 64`). Expected: exit 1,
  four `lineage_raw_content_sha256_mismatch` records, each with
  `claimed: "000…0"`.

Two additional invariants sit alongside the four:
- The artifact shape is exactly `{generated_at, mismatches, checked}`.
- An empty fixture (no derived sections) exits 0 with `checked: 0`.

## Acceptance evidence the reviewer will collect

The brief's acceptance list (verbatim):

- `python3 pipelines/check_input_lineage.py --fixture <4h-lag CBS ROS fixture>`
  exits non-zero and names the CBS ROS section — covered by state C.
- `python3 -m unittest tests.test_input_lineage -v` exits 0; each test
  fails on the base commit and passes after — the four guards above are
  negative-tested by construction (each one mutates the fixture into a
  state the base commit cannot reach: there is no checker on base to
  detect the drift).
- `output/input-lineage.json` is written in the exact shape above on
  every run — covered by `TestCheckerModule.test_artifact_shape_exact_keys`.
- `make validate` exits 0 — out of scope for this brief; the reviewer's
  beat. This change does not touch any file wired into `make validate`,
  and does not edit the Makefile.

## VERIFIED vs UNVERIFIED split

VERIFIED in this sandbox:
- Both new files parse (py_compile, syntax-only).
- Repo root state, fixture shape, lineage schema, R5a writer mapping
  were read end-to-end before authoring.

UNVERIFIED (must be done outside this sandbox):
- The 9 unittest cases never executed by me.
- The 4 acceptance conditions in the brief.
- `make validate` end-to-end.
- The dispatcher's R5c wiring that consumes
  `output/input-lineage.json` (separate brief; this one only writes the
  artifact in the documented shape).

## Notes for the integration step

- The artifact's `claimed` / `actual` keys are present only when they
  carry information (per-field drift). For `missing_lineage_block` and
  the input-missing cases the JSON omits them — keeps the rendered
  surface tidy.
- The checker resolves leg files by glob + sort, mirroring each writer's
  own `find_fresh_leg` rule. The leg filename per source is fixed and
  glob-scoped (no cross-source confusion): `ddf_leg_espn.json`,
  `ddf_leg_cbsros.json`, `ddf_leg_razzball.json`.
- Comparison candidates are scanned only under
  `output/comparison-candidates/*.json` and only those carrying
  `schema: trade-value-comparison-section-candidate-v1` are checked.
  Review files (which carry a different schema) are skipped, not
  inspected.
- The checker does NOT add a `lineage` block to
  `dist/modules/pipeline-checkpoints.json`; that wiring is the
  dispatcher's R5c beat.
- `vintage_source` equality is enforced — a derived section that
  silently flipped from `content_vintage` to `legacy_fallback` (e.g.
  the upstream stamp regressed) will be flagged.