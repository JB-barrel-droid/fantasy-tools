# JEG-242: integration investigation and continuation

Work is incomplete. No refresh/view wiring, fixture mutation, promotion or
production parity has been implemented on this branch. Base: PR52 stack,
author commits9f7fb0a/0d5e3d3; latest fetched main39a3f29 separately adds JEG212
validator. Current old Supabase refresh uses unified.translate_source; widget
curve-widget.js791–810/2619–2654 keeps value-above-waivers and adjusted modes
pending. Sync builds the older fixture schema. New candidate math is tested in
PR47–52, but green arithmetic is not integrated/rendered parity.

## Verified source observation

Read the exact approved JEG180 workbook through connected Drive. Title:
JEG-180 Option C — FantasyCalc Model, ID1cjMD7GlsNv1vAk2eC-p5maw1JK0s4kB8oJ-QV83JqTU.
Sentinel reads README/IN_League/IN_Ours/CALC_Params/OUT_Translated/CHECKS A1:L12
are preserved in jeg-242-sheet-sentinels.json. These bounded reads are incomplete,
not a full oracle. IN_League shows12teams/12flex/72bench; IN_Ours lists legacy
approved targets148.84/26.27/995.91/175.75/975.04/172.07/145.73/23.38.
CALC_Params shows actual publisher group sums and full-precision allocation
factors. OUT_Translated has live imputed values plus several distinct translated
columns: position70 maxima, new repeated70/55 values and old #DIV/0 errors.
CHECKS reports OK despite these old-column errors. Therefore do not adopt a
blanket workbook OK or its translated columns as approved JEG209 batch70 oracle.
Pin the approved imputed role/group/U columns specifically, then independently
validate batch70 against the revised linear design. Read full IN_FC/CALC_Main/
OUT_Translated rows and formulas before selecting a numeric fixture; preserve
source snapshot hash and explicit canonical name/key match. No identities guessed.

## Integration approach

Extend candidate/review infrastructure while preserving separate current-method
contracts. Build an explicit local refresh plan over publisher native snapshots,
roster/target manifests and granular legs; call current producers and shared batch
math, then write only output candidates. Admission must verify canonical fixture
membership/position, complete source coverage or explicit exclusions, content
vintage and review_rows, units and shape. Published legacy targets and granular
raw-surplus units remain distinct until a reviewed migration approves a conversion.
Do not silently point JEG206 legacy total_vorp consumers to raw totals.

Add a schema-specific review for the new artifact; the existing comparison review
cannot consume shared-batch70-views-v1 without an adapter and independent proof.
An opt-in local preview may load the candidate in a copied output dashboard,
leaving production pending. Rendered checks must exercise each view against exact
artifact values, genuine0 vs absent, unsupported grain, control constraint,
requested/effective budgets and all-source peak. Indexed needs native*70/max,
not the candidate native map unscaled. Granular Indexed remains unavailable.
Production sync consumes only independently reviewed/integrated artifacts.
No URL/status declaration alone is an authorization gate.

Read-only MCP architecture advice is advisory: its suggested direct invocation of
old comparison review on the new schema is unsupported; its0.15 bench-share parity
and claim that loading a reviewed blend is a Sheet oracle are insufficient.
Candidate hash admission and methodology provenance are necessary, not sufficient.

## Next concrete work

1. Fetch current main and inspect JEG212 validator tolerances/units before adapting.
2. Capture complete approved Sheet imputation oracle (roles/U/group sums), separate
   its legacy transformed columns; match names only through verified canonical data.
3. Implement local candidate refresh and schema-specific review with hashes/gates.
4. Implement copied-dashboard preview and numerical/rendered three-view parity.
5. Add tests.test_three_view_pipeline_wiring to required Makefile checks; negative
   tests must fail old unwired path. Run targeted tests then make validate on exact
   integration HEAD; record holds and source hashes. Roman owns merge/deployment.

Prior validation remains35 targeted tests and composite make validate0 for PR52,
not current main39a3f29 or this unimplemented integration. Architecture investigation
session13a86542-bbb3-4d61-9c40-0581a8c55c00 completed read-only. JEG242 stays
In Progress, parent JEG183 In Review. Do not mark either Done from this note.

Continuation: captured all195 IN_FC/CALC_Main/OUT_Translated effective-value rows
plus IN_League A1:G13 in jeg-242-sheet-values.json (SHA256
ee21497ce441ccde935a464fa03980b7657ab0b68818c2b9f3f625a9788357e0).
`python3 -m unittest tests.test_option_c_sheet_oracle` runs1 meaningful pinned
oracle test:195 roles/groups/full-precision imputed values match with0 differences.
Together with reference/inversion/anchor18 tests pass. Synthetic enumeration IDs
are arithmetic placeholders only; no canonical membership/production parity claim.
Formula capture/canonical matching and all runtime integration steps remain.
Required Makefile includes the oracle module. Old rounded producer cannot match
full-precision oracle at relative1e-12; no translation columns are accepted as
batch70 truth. The preserved arithmetic report records195/0, not rendered parity.

Oracle slice full composite `make validate` exits0, log
/private/tmp/jeg242-oracle-validate.log. Composite based on main5792ba5 plus
PR43/47–52 and the oracle code; later main39a3f29 not integrated. The cherry-pick
of268b6d3 had a documentation-only modify/delete conflict because the prior
handoff-only commit was absent in the validation checkout; resolved by keeping
the complete author handoff. Runtime/test code applied unchanged before validation.
Draft PR53 contains this incremental oracle/handoff slice. JEG242 is not complete.

## 2026-10-03 01:07 CDT — step (1) complete on main

c62770c "JEG-242: complete Sheet oracle — approved formulas pinned, 195/195
canonical player-key matches (7 tests)" is on origin/main. The approved
CALC_Main formulas (role/group/alloc-factor/imputed-VORP) are pinned in
docs/audits/jeg-242-sheet-oracle-complete.json, all 195 rows match canonical
player_keys via pipelines/lib/canonical_players.py (reason == "ok"), and
tests/test_sheet_oracle_canonical.py (7 tests) passes on main. This supersedes
the synthetic-ID oracle for formula/canonical purposes; the synthetic oracle
module remains as a values-level reference only.

Also on this branch (muse/jeg-242-batch70-review): pipelines/review_batch70_views.py,
the schema-specific review for shared-batch70-views-v1 candidates (gates:
schema/status, scale, 8-group allocation, three-view shape, one common 70
anchor, per-source budget conservation, manifest provenance, --batch hash
admission; control provenance surfaced, never approved), plus
tests/test_review_batch70_views.py (9 tests: real-producer candidate passes;
tampered batch, missing manifest, non-candidate status, legacy per-source 70
scaling, unexcluded source, sidecar mismatch all fail). Registered in
Makefile test-unit.

Remaining: (2) local candidate refresh over publisher native snapshots +
DDF group VORPs with the review wired in; (3) copied-dashboard preview with
numerical/rendered three-view parity; (4) tests.test_three_view_pipeline_wiring
in required checks. The blend reference for (2) needs Jeremy's
weighting/horizon decision (reweight_reference.py accepts an explicit
candidate policy; weights are not invented by the lane).
