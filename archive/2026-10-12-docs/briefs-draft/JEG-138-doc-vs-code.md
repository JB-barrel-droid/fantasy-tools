# JEG-138 — Implementation Brief: normative doc vs code test (R11)

**Lane:** minimax (M3) draft
**Parent:** JEG-138 (child of JEG-78 health program; audits JEG-83 section 6 R11; standard PH-11 in `docs/health/best-practices.md:70`)
**Risks:** GAP-014, GAP-038 (`docs/risk-register.md:31`, `docs/risk-register.md:53`)
**Format reference:** JEG-178 (Linear) — 7-section implementation BRIEF.
**Worker scope:** draft only. No code, no Linear writes, no merge/push.

---

## 1. Problem

`docs/import-health-schema.md` is marked **NORMATIVE** (line 3: *"Status: normative. The pull watchdog codes against this document; do not change field names, types, the status enum, or the failure codes without coordinating with the watchdog builder."*) yet its source list is stale: it lists **five** active dashboard sources — `espn`, `usatoday`, `fantasycalc`, `fantasypros`, `cbs` (`docs/import-health-schema.md:18-19`, repeated at line 53 and line 99) — while `pipelines/verify_import_health.py`'s `DASHBOARD_SOURCES` covers **seven** (`cbsros` is the sixth, `razzball` the seventh; see `pipelines/verify_import_health.py:60`, `:63`, `:64`). A watchdog coded against the doc will silently mis-handle `cbsros` and `razzball`. Because the doc's normative status means the discrepancy is not a typo — it is a contract — the fix is a doc-vs-code test that locks the two together, followed by the doc update the test forces.

## 2. Background

**Normative doc — what exists today.**
- `docs/import-health-schema.md:3` — *"Status: normative. The pull watchdog codes against this document; do not change field names, types, the status enum, or the failure codes without coordinating with the watchdog builder."*
- `docs/import-health-schema.md:11-13` — Writer: `make import-health NFL_WEEK=<n>` runs `pipelines/verify_import_health.py --nfl-week <n>`, which **"verifies all five active dashboard trade-value sources"** and writes this file. (Doc text is stale.)
- `docs/import-health-schema.md:18-19` — *"Sources covered (exactly these five, never others): `espn`, `usatoday`, `fantasycalc`, `fantasypros`, `cbs`. ECR, Vegas, and Razzball are hard exclusions — an unknown source name is a hard error in the verifier."* (Razzball is named as a hard exclusion, yet the verifier now health-checks Razzball too — see code refs below.)
- `docs/import-health-schema.md:53` — Per-source table says *"Exactly the five source keys above."*
- `docs/import-health-schema.md:99` — *"all five sources are DB-backed — no special file-cache handling remains."* (Line 64 of the same doc lists CBS as `public.cbs_trade_values`; the verifier's `SOURCE_CONFIGS` now also has `cbsros → public.cbs_ros_projections` and `razzball → public.razzball_projections`, which the doc's per-source table does not mention.)

**Code — what exists today.**
- `pipelines/verify_import_health.py:60` —
  `DB_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "espn", "cbs", "cbsros", "razzball")` — **seven** sources, ordered.
- `pipelines/verify_import_health.py:63` — `SNAPSHOT_ONLY_SOURCES: tuple[str, ...] = ()` — empty (cbsros moved from SNAPSHOT_ONLY to DB-backed on 2026-10-01 per `AGENTS.md:193`).
- `pipelines/verify_import_health.py:64` — `DASHBOARD_SOURCES = DB_SOURCES + SNAPSHOT_ONLY_SOURCES` — the runtime iterable the watchdog cares about; in this build it equals the seven-tuple above.
- `pipelines/verify_import_health.py:118` — `HARD_EXCLUSIONS = ("ecr", "vegas", "prediction_markets", "prediction-markets")` — Razzball is **not** in the hard-exclusion tuple (it was removed in JEG-18; see `AGENTS.md:199`).
- `pipelines/verify_import_health.py:621` — The success message literal still reads *"GATE: GREEN -- all six import sources verified fresh"* — a string staleness that this brief does **not** fix, but is in-scope to record for a follow-up.
- `pipelines/verify_import_health.py:65` — `WEEK_DESIGNATED_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "cbs", "cbsros")` — five week-designated sources; razzball and espn are dated. The doc does not list this split either.
- `Makefile:42-44` — `make import-health` target invokes the verifier with `NFL_WEEK`. Help text on line 18 still reads *"all five import sources are fresh"* — also stale.
- `Makefile:194` — `validate: naming naming-convention reference sync guard-harness test-unit` — the unit-test list the new test will be added to.

**Why the doc matters.** The doc carries the **Status** enum (`ok` / `stale` / `missing` / `failed`), the **failure_reason** codes (`MISSING_SNAPSHOT`, `STALE_VINTAGE`, `BYTE_MISMATCH`, `TABLE_DRIFT`, `NO_VINTAGE`, `IMPORT_FAILED` — see `docs/import-health-schema.md:67` and `pipelines/verify_import_health.py:120-127`), and the per-source table mapping. The watchdog reads `output/source-import-health.json` (`docs/import-health-schema.md:9-10`) and acts on it; if the watchdog's mental model omits `cbsros` (or `razzball`), it will skip them silently. PH-11 (line 70 of `docs/health/best-practices.md`) is the standing practice that requires this test to exist.

**Provenance.** `docs/risk-register.md:31` (GAP-014, opened 2026-10-01, *"Update the doc to six"*) and `docs/risk-register.md:53` (GAP-038, opened 2026-10-02, *"doc-vs-code test"*). `AGENTS.md:193-194` records that cbsros moved DB-backed on 2026-10-01; `AGENTS.md:196-201` records that razzball was wired through Supabase on 2026-10-02 and the doc has not caught up.

## 3. Scope

**In scope.**
- A new `tests/test_doc_vs_code.py` that parses `docs/import-health-schema.md`'s active-source list and asserts equality (set membership, ignoring order) with `pipelines/verify_import_health.DASHBOARD_SOURCES`. The test exits non-zero on mismatch.
- The doc update: revise `docs/import-health-schema.md:11-13`, `:18-19`, `:53`, `:64`, `:99` (and any prose that says "five" / "Razzball exclusion") to match the seven-source reality. The version string `trade-value-import-health-v1` (`docs/import-health-schema.md:50`) stays — a schema-version bump is its own ticket.
- A short `docs/health/doc-vs-code-tests.md` recording the pattern (parser regex, set-equal assertion, simulated-broken-state negative-test recipe) so future normative docs (e.g. `docs/supabase-source-mapping.md`; future `import-health-schema.md` version bumps) get the same treatment.
- Wiring `tests/test_doc_vs_code.py` into `make validate` via `Makefile:194` (`test-unit` list).

**Out of scope.**
- A general doc-vs-code linter that walks every doc under `docs/`.
- Updating non-normative docs (READMEs, lane docs, `AGENTS.md` aside from the existing rule reference, design notes).
- Adding new normative docs (R12 may).
- Bumping the schema version: `trade-value-import-health-v1` stays.
- The stale "all six import sources verified fresh" string at `pipelines/verify_import_health.py:621` and the stale help text at `Makefile:18`. Recorded as a follow-up, **not** fixed in this ticket — this brief's lock is *doc source list vs `DASHBOARD_SOURCES`*, not every stale literal in the codebase.

## 4. Acceptance criteria

Each item below is verifiable by running the named command or reading the named file/line.

1. **`tests/test_doc_vs_code.py` exists** at `tests/test_doc_vs_code.py`, defines at least one `unittest.TestCase` whose setUp loads `pipelines/verify_import_health.py` via `importlib.util.spec_from_file_location` (the same pattern used in `tests/test_import_health.py:18-25` and `tests/test_lineage_snapshot_guard.py:11-19`).
2. **The test parses the doc** by reading `docs/import-health-schema.md` as text, extracting the back-tick-quoted source names from the active-source list (the line at `docs/import-health-schema.md:18-19` and any other "Sources covered" / "active dashboard sources" prose), normalising to a `set[str]`.
3. **The test compares to `DASHBOARD_SOURCES`** loaded from the module: the parsed set must equal `set(mod.DASHBOARD_SOURCES)`. On mismatch, the test calls `self.fail(...)` with the symmetric difference spelled out (`only-in-doc`, `only-in-code`); `unittest` then exits non-zero.
4. **The test fails on `main` today.** Verifiable by: revert nothing, just run `python3 -m unittest tests.test_doc_vs_code` against `minimax/jeg-138-brief`'s current HEAD — exit code 1, with `only-in-code` listing `cbsros` and `razzball` (the seven-vs-five gap, plus the razzball-hard-exclusion prose at `docs/import-health-schema.md:20-21` if the regex catches it).
5. **Negative test A — reverted doc fails.** Simulate broken state A: temporarily edit `docs/import-health-schema.md` so the active-source list reads *"exactly these five"* with `espn, usatoday, fantasycalc, fantasypros, cbs` (drop `cbsros`, `razzball`). Run `python3 -m unittest tests.test_doc_vs_code` — exit code 1, with `only-in-doc` listing the missing two. Revert the edit before merge.
6. **Negative test B — shrunk code fails.** Simulate broken state B: in a throwaway branch, edit `pipelines/verify_import_health.py:60` to remove `cbsros` (and only `cbsros`) from `DB_SOURCES`. Run `python3 -m unittest tests.test_doc_vs_code` against the same throwaway branch — exit code 1, with `only-in-code` listing `cbsros`. Revert before merge.
7. **Both negative tests must be shown to fail against the simulated broken states before this ticket merges** (AGENTS.md rule: a guard that does not prove it catches the bug it names is worse than no guard). The proof is two captured `unittest` output lines, recorded in `docs/claude-log.md` with the simulated commit SHA, by the worker who runs validation outside the worktree.
8. **Doc is updated** so the active-source list, the "Sources covered" line, the per-source table header, the CBS line at `docs/import-health-schema.md:64`, and the "all five" prose at `:99` reflect all seven sources and remove the Razzball hard-exclusion claim. The version string at `:50` is unchanged.
9. **`make validate` is green after the doc update and the test's addition to the unit list.** Verifiable by running `make validate` locally or in CI.
10. **`docs/health/doc-vs-code-tests.md` exists** with: (a) the pattern (which docs are normative, parser regex, set-equal assertion), (b) the negative-test recipe (revert doc, shrink code, both must fail), (c) a reference list of future normative docs that should get the same test (`docs/supabase-source-mapping.md`, future `import-health-schema.md` version bumps).

## 5. Relevant files

- `docs/import-health-schema.md` — the normative doc under audit. Lines 11-13, 18-21, 53, 64, 99 carry the "five sources" claim and the now-wrong "Razzball hard exclusion" claim.
- `pipelines/verify_import_health.py` — the runtime source of truth. Line 60 (`DB_SOURCES`), line 63 (`SNAPSHOT_ONLY_SOURCES`), line 64 (`DASHBOARD_SOURCES`), line 118 (`HARD_EXCLUSIONS`). The test imports this module via `importlib.util` (pattern: `tests/test_import_health.py:18-25`, `tests/test_lineage_snapshot_guard.py:11-19`).
- `tests/test_doc_vs_code.py` — **new**. The doc-vs-code test that R12's merge-checklist rule will point to.
- `docs/health/doc-vs-code-tests.md` — **new**. Pattern note for future normative docs.
- `Makefile` — `Makefile:194` (`validate: ... test-unit`) is where `tests/test_doc_vs_code.py` is registered.
- `docs/risk-register.md` — GAP-014 (`:31`) and GAP-038 (`:53`) are the standing risks this brief closes.
- `docs/health/best-practices.md:70` — PH-11, the practice this ticket implements.
- `docs/claude-log.md` — append a session entry per the AGENTS.md working agreement once validation runs.

## 6. Test plan

**New test.**
- `tests/test_doc_vs_code.py::TestImportHealthSchemaDocVsCode::test_active_source_list_matches_dashboard_sources` — the set-equal assertion between the parsed doc source list and `verify_import_health.DASHBOARD_SOURCES`.
- `tests/test_doc_vs_code.py::TestImportHealthSchemaDocVsCode::test_razzball_not_listed_as_hard_exclusion` — a targeted check that the doc's "Razzball hard exclusion" claim at `docs/import-health-schema.md:20-21` is gone after the doc update (this is the prose-only fix that the set-equal test cannot reach).
- The test is registered in `Makefile:194`'s `test-unit` list with one new line: `python3 -m unittest tests.test_doc_vs_code`.

**Negative-test recipe (executed by the worker that runs validation outside the sandbox; the brief author does not run it).**
- Broken state A — revert `docs/import-health-schema.md:18-19` to *"exactly these five: espn, usatoday, fantasycalc, fantasypros, cbs"*. Run `python3 -m unittest tests.test_doc_vs_code`. Capture exit 1 and the `only-in-code` line.
- Broken state B — in a throwaway branch, edit `pipelines/verify_import_health.py:60` to drop `cbsros` from `DB_SOURCES`. Run `python3 -m unittest tests.test_doc_vs_code`. Capture exit 1 and the `only-in-code` line.
- Both captures go in `docs/claude-log.md` with the simulated SHA, per the AGENTS.md "every guard ships with its negative test" rule.

**Existing tests that must still pass.** The test is additive to the unit list; it must not regress any of the following. Run `make validate` after the doc update + test addition:
- `make validate` runs `naming`, `naming-convention`, `reference`, `sync`, `guard-harness`, `test-unit` (Makefile:194).
- `test-unit` list is the Makefile:114-169 block. Specifically relevant neighbours: `tests/test_import_health.py` (which already imports `verify_import_health.py` and reads `DASHBOARD_SOURCES`-adjacent state) and `tests/test_razzball_supabase.py` (which asserts the razzball wiring at `AGENTS.md:196-201`).
- `tests/test_sync_health_freshest.py` — the freshest-payload guard added on 2026-10-01 (Makefile:157) — must stay green so the doc vs health-file drift stays bounded.

**Doc-vs-code test ordering (test first).**
1. Land the test against the current `import-health-schema.md` — it fails (exit 1) because the doc says five and the code has seven.
2. Update the doc — `docs/import-health-schema.md:11-13, :18-19, :53, :64, :99` and the razzball-hard-exclusion line at `:20-21` — so the doc matches the seven-source reality.
3. Re-run `python3 -m unittest tests.test_doc_vs_code` — exit 0.
4. Run `make validate` — exit 0; the test now lives in `Makefile:194`'s unit list and the doc is in sync.
5. (Out-of-sandbox) Run the two simulated broken states — both must fail — and log the captures in `docs/claude-log.md`.

## 7. Constraints

The worker blocklist — what the implementer of this brief **must not** do. Any of these voids the slice and is not a soft "skip":

- **No credentials.** No `.env`, no Supabase service-role key, no GitHub PAT, no `sbclient` writes. The test reads a doc and imports a module; it touches no network.
- **No browser.** No Playwright, no headless Chromium, no `npm ci` + `playwright-core install`. The doc-vs-code test is unit-pure.
- **No vision or OCR.** No screenshots, no image diffs.
- **No macOS-only files.** No edits under `~/Projects/"fantasy tools"` beyond `Claude outputs/`. The repo worktree is the only write target.
- **No merge, push, or deploy.** The brief is draft only. The worker who runs validation outside the sandbox owns the commit, push, and any deploy-related actions.
- **Linear CLI is unavailable in the sandbox.** No Linear writes from this branch; JEG-138 stays a draft ticket reference, not a created entry.
- **Workers cannot run tests.** The brief author writes the test file and stops. Validation (`make validate`, the two simulated broken states, `docs/claude-log.md` capture) happens outside the sandbox.
- **No methodology / values / copy decisions.** The doc change is factual: five sources → seven sources; "Razzball hard exclusion" → "Razzball is DB-backed, dated daily". No copy or methodology is at stake.
- **No adjusting the test to go green.** If the test fails after the doc update, the doc is wrong (or the test is); do not edit the test to silence it. If the test passes before the doc update, the doc was already updated and the lock is no proof — surface that, do not pretend it is the lock.
- **Every new guard ships with its negative test.** The two simulated broken states (Acceptance 5 and 6) are part of this slice's deliverable, not a follow-up.
- **Never publish on a known flaw.** This ticket publishes nothing; merge is gated on `make validate` green and the two negative-test captures in `docs/claude-log.md`.