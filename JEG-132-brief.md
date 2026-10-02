Issue: JEG-132 (R5a) — lineage block writers on derived sections
Lane: minimax (M3)
Branch: minimax/jeg-132-lineage-writers

Setup:
- Base commit: 5df093c9b199. Create the worktree with:
  `git worktree add ~/workspace/worktrees/wt-jeg132-lineage-write 5df093c9b199`
  then `git -C ~/workspace/worktrees/wt-jeg132-lineage-write checkout -b minimax/jeg-132-lineage-writers`.
- NOTE for dispatcher: origin/main has moved since 5df093c9b199 (now 03eff120);
  confirm the base before dispatch.

Task:
JEG-132 (health-program R5, High) part A — the writers. A derived compute can
lag its input without detection (live case 2026-10-02: CBS ROS table vintage
2026-10-02, promoted CBS ROS section vintage 2026-09-30 — invisible because no
derived section records which raw input it was built from). Per DH-3:
"Staleness is computed, not asserted."

In each of these five builders, when a DERIVED section is written, record an
immutable `lineage` block on the section:
- `pipelines/build_adjusted_fixture_sections.py` (adjusted sections)
- `pipelines/build_cbsros_section_from_ddf_leg.py` (CBS ROS leg)
- `pipelines/build_espn_section_from_ddf_leg.py` (ESPN adjusted)
- `pipelines/build_razzball_section_from_ddf_leg.py` (Razzball adjusted)
- `pipelines/build_comparison_source_section.py` (value-above-waivers translated)

The block:
```
lineage: {
  raw_vintage:      <content_vintage of the raw section built from>,
  raw_content_sha256: <SHA-256 over that raw section's (player_key, native, reindexed) triples>,
  raw_built_at:     <built_at of the raw section>
}
```
Rules:
- Raw sections do NOT get a lineage block (they are inputs).
- The block is written at build time and must survive promotion untouched — do
  NOT edit `pipelines/promote_comparison_section.py` (sibling R4a brief's file).
  If promotion currently drops unknown keys, note it in your report instead of
  editing promote.
- Read the raw section's `content_vintage` if present (R4a stamps it); if absent,
  fall back to the existing vintage field and mark the fallback explicitly in the
  block (`vintage_source: "content_vintage" | "legacy_fallback"`) so the
  dependence is visible, never silent.
- Do not change any values, math, or section contents — only ADD the block.

Add `tests/test_lineage_writers.py` (new): builds a small fixture through the
writers (temp dirs only) and asserts every derived section carries the three
lineage fields with the sha matching a recomputation over the raw triples; raw
sections carry no lineage block. Must FAIL on the base commit, PASS after.

The checker that consumes these blocks (`pipelines/check_input_lineage.py`) is
a sibling brief (JEG-132 lineage-checker); the page render of the lineage line
is a sequenced follow-up. Do NOT build either here.

Context:
- JEG-132's real-life case is your test fixture model: a CBS ROS leg rebuilt
  from the `Week 4` raw table whose section lineage still claims `Week 3` must be
  detectable (the sibling checker asserts it; your writers must make the honest
  block that makes detection possible).
- Standing rules (apply to everything you do):
  - Model: minimax M3 only (Jeremy 2026-10-02: M3 is the only minimax model).
  - One worker per worktree/branch. Never touch a file another active brief owns
    (see File boundaries — they are exclusive). In particular
    `pipelines/promote_comparison_section.py` (R4a) and
    `pipelines/lib/publication_windows.py` (R4a) are off-limits.
  - Your sandbox blocks test execution and the Linear CLI. Write code + tests; you
    may run `python3 -m py_compile` on new files. Split your result into VERIFIED
    (actually executed, paste output) vs UNVERIFIED (written but not run — the
    reviewer runs them). Never assert "tests pass" for tests you did not execute.
  - This repo uses unittest, not pytest.
  - Do NOT edit the Makefile. New tests are wired into `make validate`'s test-unit
    target by the dispatcher at integration.
  - Never merge, push, or deploy. Commit on your branch only.
  - Two-failure rule: if the same approach fails twice, stop and report — never a
    third blind retry.
  - Capability blocklist: no OCR/vision, live browser, credentials, Mac-only
    files, methodology/values/copy. Lineage fields are internal data, not copy.

Acceptance (runnable — the reviewer runs these):
- `python3 -m unittest tests.test_lineage_writers -v` exits 0; fails on the base
  commit (no lineage blocks), passes after.
- Every derived section emitted by the five builders carries
  `lineage.raw_vintage`, `lineage.raw_content_sha256`, `lineage.raw_built_at`;
  recomputing the sha over the raw triples reproduces it exactly.
- No values, math, or existing fields change (diff a before/after section build
  with lineage stripped — must be identical).
- `make validate` exits 0 (reviewer; your change must not break existing targets).

File boundaries:
- May touch: `pipelines/build_adjusted_fixture_sections.py`,
  `pipelines/build_cbsros_section_from_ddf_leg.py`,
  `pipelines/build_espn_section_from_ddf_leg.py`,
  `pipelines/build_razzball_section_from_ddf_leg.py`,
  `pipelines/build_comparison_source_section.py`,
  `tests/test_lineage_writers.py` (new).
- Must not touch: `pipelines/promote_comparison_section.py` (sibling R4a brief),
  `pipelines/lib/publication_windows.py` (sibling R4a brief),
  `pipelines/check_input_lineage.py` (does not exist yet — sibling R5b brief),
  `app/`, `modules/`, `dist/`, `Makefile`, the Linear CLI/issues.

Result contract:
- Work on branch minimax/jeg-132-lineage-writers; commit your changes.
- Write lanes/inbox/minimax/JEG-132-lineage-writers.md with: files changed,
  commands run + outputs, acceptance evidence (paste outputs), VERIFIED vs
  UNVERIFIED split, and the exact `lineage` schema the sibling checker brief
  consumes (including the `vintage_source` fallback marker).
- Never merge, push, or deploy. Never claim done without the evidence bundle.
