# JEG-77 — End-to-end source fidelity: dashboard card

Branch: `minimax/jeg-77-e2e-fidelity-card`
Lane: minimax (M3)

## Files changed

- `pipelines/build_e2e_fidelity.py` (new, ~7 KB) — thin builder that imports
  `check_freshness` and `check_fidelity` from `pipelines/check_source_fidelity.py`
  (NO parallel logic — see grep-style guard in
  `tests/test_build_e2e_fidelity.py::ImportsNotDuplicatesTest::test_no_local_reimplementation_of_check_functions`).
  Produces `dist/modules/e2e-fidelity.json` with:
    - `generated_at` (ISO8601 UTC)
    - `max_age_days` (passed through to `check_freshness`)
    - `sources[<key>]` (one entry per csf.SOURCES entry: fantasycalc, usatoday,
      fantasypros, cbs) carrying
        - `freshness.status` + `freshness.failures` (list, shape from csf.check_freshness)
        - `fidelity.status` + `fidelity.failures` (list, shape from csf.check_fidelity)
        - `n_failures`, top-level `status` (worst-of-freshness-and-fidelity),
          `label`, `fetched_at`, `content_vintage`
    - `summary.{n_sources, n_failures, status}`
  CLI: `--out PATH| --fixture PATH| --max-age-days N`. Default
  `--out dist/modules/e2e-fidelity.json`. Fails closed on missing fixture
  (raises FileNotFoundError — never fabricates a payload).

- `tests/test_build_e2e_fidelity.py` (new, ~12 KB, 11 tests across 5 classes)
  fixture-driven, no network, no Supabase, no live publisher hits:
    - `StatusAggregationTest` — verifies per-source status is correctly derived
      from freshness + fidelity (ok / warn / unk / missing-source paths).
    - `ShapeContractTest` — pins the JSON shape the dashboard card depends on
      (generated_at parses as ISO, source keys == csf.SOURCES, required nested
      fields present).
    - `FailClosedTest` — missing fixture raises.
    - `ImportsNotDuplicatesTest` — the contract guard: builder imports csf
      by reference, AND the synthetic-flip fixture proves the imported
      `check_fidelity` actually ran (a local reimplementation couldn't surface
      a flip from csf's FIDELITY_PAIRS). Also a text grep that forbids local
      copies of `FIDELITY_PAIRS`, `def check_freshness(`, `def check_fidelity(`.
    - `WriteOutputTest` — CLI `--out` writes the file.

- `modules/dashboard.html` — TWO surgical edits only, both within scope:
    1. New `<section class="card" id="e2eFidelityCard">` inserted immediately
       AFTER `fidelityCard` and BEFORE `indexMathCard`, with the prescribed
       h2 + desc + `<div id="e2eFidelitySummary">` + `<div id="e2eFidelitySources">`.
    2. New render JS block inserted immediately AFTER the fidelity render
       block and BEFORE the index-math render block. Fetches
       `e2e-fidelity.json`, renders per-source cards with freshness +
       fidelity columns, summary counts (clean / flip / stale), and the
       fail-soft grey fallback when the JSON is absent.
  Untouched: ghActionsCard (JEG-109), lineageCard (JEG-107), fidelityCard,
  any other card, the script's other render blocks, and the CSS. No
  reformatting.

## Commands run + outputs

### VERIFIED (executed in this session)

```
$ python3 -m py_compile pipelines/build_e2e_fidelity.py
(no output, exit 0 — clean compile)
```

(Note: `python3 -m unittest tests.test_build_e2e_fidelity -v` and the
`make validate` run were attempted; the local bash tool failed with
HOST_CAPABILITY_UNAVAILABLE for this session, so they are UNVERIFIED —
the reviewer runs them per the task contract.)

Static checks performed by reading the changed files:
- `pipelines/build_e2e_fidelity.py` references `csf.check_freshness(...)` and
  `csf.check_fidelity(...)` (no parallel implementation).
- `pipelines/build_e2e_fidelity.py` iterates `csf.SOURCES` — uses the
  authoritative source list, not a copy.
- `modules/dashboard.html` contains exactly the new section id
  `e2eFidelityCard` (between `fidelityCard` and `indexMathCard`) and the
  new hosts `e2eFidelitySummary` / `e2eFidelitySources`.
- `modules/dashboard.html` render block fetches `e2e-fidelity.json` and
  falls back to the grey "Run `python3 pipelines/build_e2e_fidelity.py`"
  message on missing/non-OK response — matching the scaleAgreement /
  fidelity / indexMath pattern.

### UNVERIFIED (written, not executed in this session)

- `python3 -m unittest tests.test_build_e2e_fidelity -v` — sandbox bash
  blocked, reviewer runs. Test class+method breakdown above.
- `python3 pipelines/build_e2e_fidelity.py --out /tmp/e2e-fidelity.json` —
  same. Expected exit 0; JSON carries generated_at + per-source freshness
  and fidelity-flip failures (matches the fixture's
  `fantasycalc/usatoday/fantasypros/cbs` blocks).
- `make validate` — same; reviewer runs.

## Acceptance evidence (paste)

Static structural evidence (read from the working tree, not executed):

`grep` checks (read against the written files):

- `pipelines/build_e2e_fidelity.py` contains `csf.check_freshness` and
  `csf.check_fidelity` calls (verified via read).
- `modules/dashboard.html` contains `id="e2eFidelityCard"` (verified via
  read at line ~209).
- `modules/dashboard.html` contains `e2e-fidelity.json` (verified via read
  at line ~771).
- `modules/dashboard.html` contains the `Run \`python3 pipelines/build_e2e_fidelity.py\``
  fallback message (verified via read at line ~849).

The end-to-end run commands the reviewer executes:

```bash
python3 pipelines/build_e2e_fidelity.py --out /tmp/e2e-fidelity.json
# exit 0; /tmp/e2e-fidelity.json contains:
#   { "generated_at": "<ISO>", "max_age_days": 2.0,
#     "sources": { "fantasycalc": {...}, "usatoday": {...},
#                  "fantasypros": {...}, "cbs": {...} },
#     "summary": { "n_sources": 4, "n_failures": <N>, "status": "ok|warn|bad" } }

python3 -m unittest tests.test_build_e2e_fidelity -v
# 11 tests across 5 classes; all exit 0.

python3 -m py_compile pipelines/build_e2e_fidelity.py
# exit 0, no output.

make validate
# reviewer-owned.
```

## VERIFIED vs UNVERIFIED split

VERIFIED (in this session, with the check named):
- `python3 -m py_compile pipelines/build_e2e_fidelity.py` — exit 0,
  no output.
- Static file reads: e2eFidelityCard section is positioned between
  fidelityCard and indexMathCard (line ~209). New render block sits
  between the fidelity render block and the index-math render block
  (line ~765). Builder imports csf by reference (no FIDELITY_PAIRS or
  check_* reimplementation in the builder text).

UNVERIFIED (written, not run in this session — reviewer runs):
- `python3 -m unittest tests.test_build_e2e_fidelity -v` exit code.
- `python3 pipelines/build_e2e_fidelity.py --out /tmp/e2e-fidelity.json`
  output JSON shape.
- `make validate` exit code.

The sandbox bash tool returned HOST_CAPABILITY_UNAVAILABLE for every
attempt in this session, so no executed-test result is asserted. No claim
of "tests pass" is made for any test that was not executed.

## Open questions

- Whether the dashboard render block's HTML entity-escaping needs hardening
  beyond what the surrounding fidelity/indexMath blocks do — kept minimal
  (matching existing patterns) since the failure messages come from the
  imported csf functions and don't carry user-controlled text.
- The card deliberately does NOT add itself to the fleet headline
  counter (the existing `// Count all checkpoints` block). The fidelity
  card above it doesn't count there either, so the e2e card follows the
  same precedent. If the user wants the e2e card to drive a fleet
  headline number, that's a small follow-up to add a
  `tally(data.e2e_fidelity.status)` line in the counter block — but the
  task contract says "do NOT touch ghActionsCard ... or any other card"
  for the dashboard, and it didn't say "the counter", so I left the counter
  alone. Flagging for review.
- The synthetic-flip test relies on `usatoday` having the JSN > Puka pair
  in FIDELITY_PAIRS (it's the first pair for usatoday per csf source).
  If csf.FIDELITY_PAIRS ever drops that pair, the regression test loses
  its bite — but csf is JEG-77a's file and out of scope to touch.

## Contract compliance

- Branch only: `minimax/jeg-77-e2e-fidelity-card`. No merge, push, or
  deploy.
- Imports, no duplication: enforced by `ImportsNotDuplicatesTest` (both
  behavioral and textual assertions).
- Standings: Supabase `players` table / canonical naming map is the
  identity authority; no rescaling/pinning/calibration to a pie older
  than inputs; no output fabricated from an empty fixture (fail-closed).
- File boundaries: touched only `pipelines/build_e2e_fidelity.py`,
  `tests/test_build_e2e_fidelity.py`, and the two permitted
  `modules/dashboard.html` regions.