## 2026-11-05 - Deterministic helper continuity controls / JEG-1509

Contract: correct JEG-1333's existing fractional-seat helper continuity tests. Only `tests/test_fractional_seats.py` and this log change. Jeremy explicitly approved creating and claiming the correction child on November 5 at 06:44:55 UTC. Branch: `codex/JEG-1509-continuity-controls`; parent: JEG-1333.

### Verified (check named)
- JEG-1509 is claimed by the Cloud Codex helper correction lane, assigned to Jeremy with `codex`, `Bug` and `review-high-risk`. Parent children, ticket comments and an exact test-path open-PR search showed no competing owner.
- Base main is `fbaf72fd24d517135a9c71c42f2261e08eb5c83c`. The helper and focused test files match the earlier verified base `216a9143ed33da42220777124c44c55d6fac1d3c`; no production code is changed.
- The base's `ContinuityTest.test_crossings_are_continuous` fails: `no bench crossing within 1.5 PPG of a cutoff` for ppr/14. This was reproduced before the repair; the original full module has 9 passes and 1 failure. The baseline wrapper identifies an unregistered red; no registry change is made.
- Cause: discounted rank determines position counts. A moved fringe player can replace a same-position neighbor without transferring a seat between positions. Current live projections therefore do not guarantee the searched crossing exists. A diagnostic reach of 5 PPG still found no ppr/14 bench crossing; widening the test search is not the fix.
- The constructed flex boundary has F-1 protected RBs plus two equal raw-score candidates. The bench boundary has B-1 protected candidates plus two equal discounted-score candidates. The fixture contract verifies no live projection load, sorted inputs, an actual RB/WR seat transfer, conserved flex and bench counts, available player depth, and unchanged flex counts in bench controls.
- `python3 -m unittest -v tests.test_fractional_seats`: 11/11 pass on the repaired working tree. Includes all six original continuity scenarios, hard-cutoff controls, 200 random JS/Python league comparisons within 1e-12, CDF/decomposition parity, conserved counts and sigma-zero/small-sigma limiting behavior.
- Every constructed hard scan jumps 2.0; the largest soft scan step is 0.009598208315. `STEP=0.01`, `STEP_BOUND=0.05` and the hard-control assertion remain unchanged. Forcing sigma-zero output into the positive continuity test makes its actual `assertLess` fail. The hard-control test now covers all six scenarios instead of four.
- `git diff --check` passes. The prepared patch applied cleanly to the pinned base. Original scratch patch and before/after receipts remain preserved under `/tmp/jeg1333-correction`.

### Claimed, not confirmed
- Working-tree and earlier scratch checks are focused evidence. The PR/ticket receipt must separately name the committed head after its focused rerun; neither these checks nor the scratch candidate establish full qualification.
- Full `make validate`, exact-head CI and independent high-risk review remain separate gates. No merge, deployment, Supabase action, access change or deletion is performed.
