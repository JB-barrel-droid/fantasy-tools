## 2026-10-12 - CLAUDE.md trim (usage discipline, JEG-524 style)

Contract: cut what loads into every session from this repo's `CLAUDE.md`. Jeremy asked to drop the "Copy rules" section and tighten wording.

### Verified (check named)
- `wc -c CLAUDE.md`: 10244 -> 9352 bytes. `git diff --stat`: only `CLAUDE.md` changed in the code tree.
- `grep -rln CLAUDE.md tests pipelines Makefile .github`: 4 hits (3 tests, `pipelines/build_values_explainer.py`), all docstring or comment mentions of "CLAUDE.md"; none opens the file, so nothing depends on the removed section.
- Copy rules were removed at Jeremy's request. They live on in the auto-memory note `trade-dashboard-purpose` and in the enforcing tests (`tests/test_public_copy_no_vorp.py`, `tests/test_v2_contract_render.py`), which are unchanged.
- Worked in a clean worktree off `origin/main` (d1a5d28f). `~/code/fantasy-tools` itself is on a detached HEAD at 296acd62 with uncommitted generated files; those were not touched.

### Claimed, not confirmed
- Wording changes in "Pre-launch" and "Linear" paragraphs keep the same rules; checked by reading, not by a test.
- `make validate` not run: docs-only change.
