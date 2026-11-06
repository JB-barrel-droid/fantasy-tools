## 2026-11-03 - JEG-1418 high-risk review corrections

Contract: verify and correct the three P2 findings from independent review of
PR #1296 at `1506831a81d26d952f11c608fa69e77a5dc3b23d`, on the existing
`be/JEG-1418-swap-adapter` branch. Preserve running validation, source ownership
and the existing Waivers/finder rules. No new threshold policy, merge or deploy.

### Findings acknowledged and corrected

1. Decimal boundary arithmetic: binary subtraction made 3.35 minus 3.25 pass
   gt 0.1, and made 3.55 minus 3.25 fail gte 0.3. Subtraction now uses the
   canonical decimal forms of the existing finite numeric inputs. Explicit
   JSON gt/gte policies compare integer coefficients at a shared exponent,
   without an epsilon or fixed rounding precision. The serialized gain is a
   number; input DDF Values, Waivers evaluation and ordering are unchanged.
   Existing unary acceptance callbacks remain supported; source add/drop
   values are supplied as optional second/third callback arguments.
2. Position eligibility: the adapter now limits candidates AND priced bench
   drops to finder's existing QB/RB/WR/TE set. A null/unsupported position
   cannot produce a swap, including an open-slot move. Supported candidates
   remain eligible when the same wire includes an unsupported candidate.
3. Single-use proof: the old open-slot fixture admitted WR 2 before RB 1, so
   dropping that newly added player would lose raw value and be rejected even
   without the used-drop guard. The corrected fixture admits RB 2 first
   (weighted gain 1), ahead of TE 5 (weighted gain 0.5). A later move dropping
   that RB for the TE has raw gain +3 and is rejected by the used-drop guard.
   An in-memory mutant removes only that guard, produces both moves and reuses
   key 8; the same uniqueness assertion detects it. Actual repository source
   is never temporarily mutated. The existing guard itself remains in place.

### Verified (check named)

- Before changing implementation, the expanded native suite on the reviewed
  source had 23 cases: 19 pass, 4 fail. Failures cover decimal equality,
  scientific-notation precision, unsupported candidate positions and unknown
  priced-drop positions. Log: `/tmp/jeg-1418-review-before.log`.
- `node --test tests/waiver_board_swaps.test.cjs`: 23 cases pass after the
  implementation correction. Log: `/tmp/jeg-1418-review-after-node.log`.
  The six existing frozen Waivers fixture parity cases remain unchanged.
- `python3 -m unittest tests.test_waiver_board_swaps
  tests.test_waiver_board_swaps_pipeline tests.test_pipelines_import_standalone`:
  21 Python checks pass, including the 23 native cases. The pipeline adds an
  independent Python Decimal oracle for strict/inclusive equality, real
  differences on both sides of a boundary and scientific notation. It also
  checks that replay rejects a forged strict-equality swap and unsupported
  candidate swaps. Final exact-head receipt is recorded in the PR description.
- The mutation control explicitly produces `{add: 8, drop: null, gain: 2}`
  followed by `{add: 9, drop: 8, gain: 3}` only when the used-drop guard is
  removed, and the player-uniqueness assertion fails on that output.
- Scoped whitespace checks pass. No existing fixture or assertion is weakened;
  the original single-use assertions are retained with a discriminating input.

### Validation and correction-ticket handoff

The original broad validation has ended. Its saved log stops at
`tests.test_v2_phone_source_links_render.PhoneSourceLinksTest.test_source_links_have_44px_targets`
because it found zero source links at widths 320 and 375; make reports a
test-core failure. This is an observed out-of-scope failure, not a claimed
baseline attribution or a full exact-head receipt. The existing generated
churn remains untouched. The coordinator reports a reviewer-owned broad run
in progress; no new broad run, cancellation or other session control occurred.

The existing golden weekly-input SHA mismatch remains assigned to JEG-1419 /
PR #1264; its reproduction on pre-change source is documented in the earlier
session entry. This correction does not edit that fixture.

AGENTS.md requires substantial review corrections to be child tickets on the
same branch/PR. Automatic approval review rejected creation of the first
proposed child, "Correct decimal equality at local swap gain boundaries",
stating that a new Linear bug issue is an external organizational commitment
without authorization for that specific issue. The child was NOT created and
was not retried. The other two child creations were not attempted. The fixes
and exact findings are recorded here and in the existing draft PR; permission
to create the correction children remains an administrative blocker for the
coordinator. No alternative ticket tool or indirect workaround was used.

Independent delta review must name the corrected head. No author review pass,
green full-CI claim, merge, deployment, access change or production activation
is asserted.
