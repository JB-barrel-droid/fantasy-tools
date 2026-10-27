## 2026-10-27 - JEG-1161 preseason ECR unit tests

Contract: add `tests/test_preseason_ecr.py` covering
`pipelines/lib/preseason_ecr.py` (load, annotate, provenance) with a stub
registry and a temp draft JSON. Tests only; the module is not modified.

Note: this entry was written by an OpenRouter `deepseek/deepseek-v4.1-flash`
run. Its output is **untrusted until a Claude review** (T1 merge gate).

### Verified (check named)
- `python -m unittest tests.test_preseason_ecr` -> 15 tests, OK, after
  merging `origin/main`.
- Mutation check: flipping `min` -> `max` on the collision branch of
  `load_preseason_ecr_ranks` (line 81) makes `test_collision_keeps_lowest_rank`
  (plus two count assertions) fail — 3 failures; `git checkout --
  pipelines/lib/preseason_ecr.py` restored the file and the suite is green
  again. No mutation is committed.
- `git status --short` after commit shows only the two new files.

### Claimed, not confirmed
- The K/DST, bad-rank (`0`, negative, `True`, `"3"`, missing), unmatched,
  collision and report-count expectations are read from the module source and
  match the stub's behaviour; they are not cross-checked against a live
  `data/inputs/ecr_draft.json` (the tests never read it).
- `annotate_rows` null-never-zero and `provenance_note` key pins reflect the
  current source; no review by a second model yet.
