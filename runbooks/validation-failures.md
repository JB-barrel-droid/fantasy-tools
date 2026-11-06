# Validation failures

Diagnostic response guide. Owner: JEG-1529. Last verified: 2026-11-05.


### Band-line

**Check IDs:** BAND-LINE-MATH, BAND-LINE-PARITY, BAND-LINE-ES-SENSITIVITY. **Owner:** validation lane diagnoses; Roman coordinates publication recovery; Jeremy owns new methodology/exemption scope decisions. Repair: [JEG-1511](https://linear.app/jegabee/issue/JEG-1511). Policy: [JEG-1518](https://linear.app/jegabee/issue/JEG-1518), integration text in [exemption decision policy](../docs/exemption-decision-policy.md).

**What this protects.** A projection source's waiver line averages the seven values around the first non-rostered seat, limiting one fringe projection's influence on all other players' Adjusted values. With enough coverage the sorted zero-based window is `[max(0,N−3):min(length,N+4)]`; zero seats clip at the top, short/exact-fit coverage uses the last value, empty/negative has no line. The 1/7 change is for a full stable seven-member band; clipped windows have different denominators. Math, JS/Python/spec parity, and negative controls protect the implementation separately from the 1.0 economic sensitivity bound. The perturbation test holds the complete allocation mix fixed; its companion allows allocations free and distinguishes slot flips.

**Recognize the designed-mechanism shape.** In Week 9, Murray's Razzball QB projection 13.8→12.8 changed an unchanged seven-key band's line by exactly −1/7 PPG (rounded 13.686→13.543). ES expected-start parts depend on shared position lines/edges. Group totals and budget/group-total rates then change, moving another QB about 1.03 points although his projection did not change. Thin TE cases also breached (Pitts 1.723, Kincaid 1.223). This is an economic amplification breach, not proof of broken seven-player averaging, not a necessary band-membership crossing, and not an ESPN-source failure.

**First actions.** Preserve the failing fixture and source content vintages, head/run and hashes before refresh or retry. Read the breach's named player(s), bound, observed move and before/after intermediates. Reproduce the named test against those exact inputs. Verify canonical identity, band arithmetic/window membership, projection clipping, unchanged affected-player input, full allocation replay including weights, free-mode slot flips, ES parts/lines and budget/group totals. Run band math and all three implementation parity controls. Compare multiple settings and bakes before generalizing. Missing evidence is an unclassified failure, not exemption evidence.

**Pre-decided response.** Follow the JEG-1518 scope ladder. If an already authorized, recorded mechanism signature exactly matches, the lane owner may apply that signature and must log every use. Historical PR #1315 proposed QB/TE, movement >1.0 and ≤2.0, at most 12 exemptions **per test**, with held allocations or free allocations without a slot flip. That candidate is evidence of a proposed signature, not blanket standing authorization. Register/verify Jeremy's decision before using it; do not require membership crossing. An unregistered shape, wider effect/count/positions, or changing a class to reporting-only requires the policy's explicit decision owner. Never serially enumerate player/scoring tuples as a substitute for a justified mechanism scope. Identity, provenance, missing-as-zero, engine/reference disagreement and broken band arithmetic remain outside this exemption.

**Current routing exception.** PR #1316 separately moved the entire perturbation class to reporting-only under Jeremy's incident direction, leaving math/end-to-end blocking. Preserve and visibly report that current role; do not silently restore, broaden, or portray it as the narrower PR #1315 predicate. Repair/removal/restoration is tracked by JEG-1511. Publication urgency invokes same-hour ownership/escalation under JEG-1512; it does not authorize hiding the diagnostic or changing value math.

**Change and verification.** Any assertion weakening, exemption, threshold/count expansion, or gate-routing change requires independent review and CI on the exact proposed head under JEG-1518's proposed policy. Retain positive and negative controls for the boundary and nonmatching failures. After integration, rerun the publication chain on the preserved candidate and verify served week/vintage and rendered data. Close the incident only with dated publication evidence and an owned restoration condition.

**Where the error links.** Every band-line record and summary links directly to `runbooks/validation-failures.md#band-line`, with a versioned repository permalink in CI, and to `docs/exemption-decision-policy.md`/JEG-1518 and JEG-1511. These are proposed integration paths; this document contains the complete entry now, and no repository runbook has been created by this task.


Implementation status: the entry above preserves the full JEG-1517 proposal. The repository paths now exist. No exemption authorization or gate-routing change is granted by installing this entry. Breach records retain unclassified mechanisms until the same-run evidence is diagnosed.

## Record transport (validation-breach/1)

Each sensitivity breach emits a standalone `[BREACH]` summary and one
`VALIDATION_BREACH_JSON ` line containing the complete JSON object. The log
line is the lossless transport; do not parse the human assertion for evidence.
Records include canonical identities, all comparable affected rows, a stable
argmax (lowest key wins ties), signed/absolute/excess movements, bound/units,
perturbation/clipping, allocations with weights, source intermediates and band
vectors before/after, canonical input content and SHA256, role and status,
reproduction command, repair/policy/runbook links. Mechanisms are explicitly
unclassified until diagnosed. CI records additionally provide a runbook
permalink at the current head. Outside CI, unavailable head/run IDs are null.

`pipelines/record_post_rebuild_validation.py --log <captured-log>` retains every
record in both chain-status copies and writes the same list to
`output/post-rebuild-validation-breaches.json`. Repeated records are retained,
including exempt records; no top-N truncation applies. Malformed structured
transport raises an error rather than silently dropping evidence. Legacy logs
without records keep their existing regex summary. The JSON sink is replaced
for each invocation, so the caller must pass the intended original or retry log
explicitly; it does not load an unrelated previous-run artifact.

The full perturbation class remains reporting-only. The log/sink do not change
thresholds, known-case predicates, slot-flip behavior, or Makefile routing.
