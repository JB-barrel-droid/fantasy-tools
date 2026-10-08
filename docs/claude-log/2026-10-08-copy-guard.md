## 2026-10-08 - copy-guard: test_public_copy_no_vorp green on principle (fix/copy-guard-vorp)

Base: origin/main 12f6947. The guard was red with 8 flagged literals in
app/trade-value-chart/assets/curve-widget.js, added by the weeks-tidy and
views-invariants merges.

### What each literal was

| Line (main) | Literal | Reaches users? | Action |
| --- | --- | --- | --- |
| 3419, 3617, 3651 | `"_vorp"` in `series.endsWith(...)` | no, key suffix check | guard: key position |
| 4181 | `"vorp"` in `measuredPublishedView(key, "vorp")` | no, view id | guard: key position |
| 4213 | `"vorp"` in `["indexed", "vorp", "adjusted"].forEach` | no, view names | guard: key position |
| 3590 | `"buildVorpRows on the saved projections + scaleToSharedTotal"` | yes: `getWeekValues().method` is shown by math-inspector.js as `prior_note` | reworded to "VORP vs waivers rebuilt from the saved projections, then scaled to the shared total" |
| 4183, 4199 | `"saved vorp_views"` (viewInvariants `mode`) | no consumer anywhere | now `"saved"`, the value every other mode field uses |

### Guard change

The two single-line regex exemptions (VIEW_MODE_ORDER, publishedViewMap) were replaced with
one rule. A literal is an internal key only if it (1) is lowercase snake_case, (2) is in a key
position (call argument, array element, index, object key, comparison operand), and (3) has no
rendering sink in its statement. Assignments, returns, object values and ternary branches are
still flagged, so the rule fails closed. The espn/cbsros/razzball_vorp data-key set stays.
The guard was added to test-core.

### Verified (check named)
- The guard run against `git show origin/main:.../curve-widget.js` flags exactly the 3 non-key literals (3590, 4183, 4199). Before the change, main flagged 8.
- Injected into the fixed widget, `caption.textContent = "vorp";`, `const lbl = {label: "Raw VORP"};` and `el.title = series.endsWith("_vorp") ? "vorp" : "";` are each flagged. In the last one, both literals are flagged because the statement has a sink.
- tests/test_public_copy_no_vorp.py: 10 tests pass. The pre-existing negatives are unchanged, and new key-position positives and copy-position negatives were added.
- `make sync` and then `make validate` exit 0, both with CHROMIUM_PATH set and with playwright unimportable (noplaywright PYTHONPATH).
- grep: there is no other consumer of `viewInvariants.*.mode` or of the old method string in app/, tests/ or scripts/. The weeks-tidy risk row still quotes "buildVorpRows" as prose and was left alone.

### Claimed, not confirmed
- The math inspector's prior-week note now shows the reworded text. I did not render the inspector to check this. The claim rests on math-inspector.js:639 reading `prior.method`.
- No chart numbers move, because only strings changed. I did not run a sweep.
