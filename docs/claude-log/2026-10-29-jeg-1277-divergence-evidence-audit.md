## 2026-10-29 - JEG-1277 divergence evidence audit (part of JEG-952), PR #1140

Contract: build an offline audit of the committed source-divergence reports
and say whether JEG-952's prerequisite (four dated weekly reports) is met,
with an availability matrix and a gaps memo. New files only; no reporter,
config, resolutions, data, Makefile or workflow change.

Result: not sufficient. Weeks 5, 6 and 7 qualify for all seven sources; the
week 8 report served week 7 for every source. No threshold recommendation.
Memo: `docs/research/divergence-evidence-audit/README.md`.

### Verified (check named)
- 55 committed versions of `dist/modules/source-divergence.json` on main
  (`f29e6e29` to `e2c191c2`) extracted from `origin/main` at `430791c4` by
  `tools/research/divergence-evidence-audit/extract_receipts.py`; two runs
  give the same file.
- The audit counts weeks 5, 6 and 7 for every source and rejects week 8 for
  `served_week_mismatch` (`RealCommittedReceipts` in
  `tests/test_divergence_evidence.py`).
- 0/1/3/4-week, repeated-capture, repeated-served-data, missing-date,
  missing-count, mixed-scoring and synthetic cases (the other classes in that
  file); `python3 -m unittest tests.test_divergence_evidence` 43 OK.
- After Codex's P2 on #1140: the frozen receipts carry the per-position
  statistics and the five largest deviations, and the value-impact check reads
  that content (`ValueImpact`,
  `test_frozen_receipts_carry_the_summaries_they_are_credited_with`; these
  fail at `7ad1890`: 4 failures, 1 error).
- Rule mutations each fail tests: no served-week check, synthetic counted as
  real, no repeat-data dedup, no identity grouping, strict float rate check.
- The committed matrix and summary equal a fresh run (`CommittedOutputsMatch`).
- PR #1140 CI at `7ad1890`: preview-build, v2-render and the four
  preview-shard jobs passed.

### Claimed, not confirmed
- That the index and fixture matched by build stamp (and content week) are the
  copies each report was built from.
- That committed reports match what was deployed; CI artifacts and the live
  site were not read.
- Per-player value impact; it needs an offline recompute from the counted
  builds' fixtures, not done.
