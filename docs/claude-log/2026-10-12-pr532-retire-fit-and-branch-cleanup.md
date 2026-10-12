## 2026-10-12 - PR 532 (JEG-539) landed, PR 530 (JEG-569 part 2) held at the sweep, branch cleanups

### PR 532 (JEG-539 retire the fit and *_adjusted sections)
- Branch conflicted with main (main's automated comparison rebuilds still carried
  `*_adjusted` sections and the fit's adjustment-inputs files). Merged origin/main,
  kept the deletions, stripped the four `*_adjusted` sections from
  `sources` and `source_validation` in `data/fixtures/current/comparison-sources-data.json`,
  regenerated dist with `make sync`.
- Squash-merged at 4850b383 on Jeremy's go-fast direction without waiting for the
  merge of its own Preview run to be required (the Preview check on the final push
  later finished green, 37m38s).

### Verified (check named)
- `make validate` exit 0 (py3.12 venv first on PATH) on the merged branch before the merge.
- Preview check on the pushed head: pass.

### Claimed, not confirmed
- Main's automated rebuild may re-add `*_adjusted` sections until it runs the new code;
  not observed after the merge.

### PR 530 (JEG-569 part 2, strip held sources) - NOT merged
- Merged origin/main (twice; main moved under it), resolved test conflicts, `make validate`
  exit 0. Three tests needed expectations changed because the repo's own fixture now
  holds `cbsros` and `razzball`, which PR 530 makes absent from the output (before, they
  were shown from the last good build): `tests/test_view_invariants.py` (expected
  measured count skips held sources), `tests/test_week_history.py` (no served/prior week
  check for held sources), `tests/test_missing_section_render.py` (asserts `fantasypros`
  renders instead of the held `cbsros`). The assertions were wrong for a held source,
  not the code.
- 12-combo sweep (tools/engine_dump.py engine, built dist, 3 scorings x 8/10/12/14):
  case (a) no source held: PR output identical to origin/main (all 12 combos),
  `fixedPieIndexed` true in all 12. `sourceScaleAgreement` no longer exists
  (retired, `tests/test_source_scale_agreement_retired.py`).
  Case (b) seeded hold on razzball: `fixedPieIndexed` true in all 12, razzball absent
  from sources and the included list in all 12, BUT the other sources' values change
  (for example ESPN adjusted up to +1.1 on values near 30-50, CBS up to +3.2, CBS series
  drops from 738 to 591 priced players, DDF blend differs in all 12). Cause: with the held
  source's combos emptied the player universe and the fixed pie renormalize over fewer
  priced players. ESPN VORP is unchanged. This differs from "other sources unchanged",
  so the PR was not merged. The branch (merge commit plus test fixes) is pushed.

### Branch cleanups (2026-10-12)
- 88 merged and 111 squash-merged remote branches deleted, 23 worktrees removed.
  Restore lists: `docs/branch-delete-restore-2026-10-12.txt` and
  `docs/branch-delete-restore-2026-10-12b.txt` in `~/Projects/fantasy-tools-clean`.
- Verified: per-PR tip SHA match for the squash-merged set. Not verified: unmerged
  branches were left untouched.
