# Codex assessment: data, pipeline and dashboard health

JEG-81 · 2026-10-02 · inspected baseline `81b2a8d` (GitHub main).

This is an independent, docs-only assessment for JEG-78. Neither the Claude nor
Muse assessment was read. It does not implement changes, consolidate the lanes,
or authorize follow-up work. All proposed practices and costs below are **Codex
judgement**, not externally sourced standards. Repository observations are
**established project practice** only to the extent demonstrated by the named
inspection or test; they do not establish current production health.

Two requirements govern every practice: never silently present stale source
data, derived fixtures or computes as current; preserve league size, scoring,
roster shape, bench share, source toggles and user inputs. Stale context can be
shown only with unmistakable labelling. A guard must validate the requested
configuration, rather than force a single configuration to make tests pass.

Evidence was gathered by reading the files named below and running `make
validate` in an isolated worktree. The validation result is recorded at the end.
Live publisher pages, deployed DOM, current Supabase rows, secret configuration,
alert delivery and restoration drills were **not verified**. The incident
descriptions below come from JEG-78, not fresh reproductions. Cost estimates are
rough engineering effort: low = hours to one day; medium = several days; high =
a week or more, including meaningful verification.

## Data health

| Practice (judgement) and why it matters here | Today and check performed (established project practice unless explicitly unknown) | Adoption cost (judgement) |
| --- | --- | --- |
| Separate publisher content vintage from pull, build and promotion times. Re-fetching unchanged projections cannot make them current. | **Partly.** Read rules 5/8 in `docs/pipeline-rules.md`, vintage derivation in `pipelines/verify_import_health.py` and `pipelines/check_reference_freshness.py`. Immutable provenance and publication-window checks exist. `pipelines/check_source_fidelity.py` also has a freshness path using `fetched_at`; naming and semantics need agreement across checks. Actual publisher vintage is unverified. | Medium: one shared contract, future-date and unchanged-content tests. |
| Define per-source publication deadlines and freshness SLOs, plus maximum derived-artifact lag. Never use one universal age threshold for daily projections and weekly charts. | **Partly.** Import health uses `pipelines/lib/publication_windows.py` and an ESPN daily limit; `tests/test_publication_windows.py` exercises windows. No complete source-to-served-compute deadline contract was established by this inspection. | Medium: owners, deadlines, grace states and expiry behaviour for each source. |
| Persist replayable raw inputs in the shared store with hashes, vintage and acquisition outcome. Local files must not be the sole refresh path. | **Partly.** Read `pipelines/import_supabase_references.py`, `pipelines/save_razzball_references.py`, and `.github/workflows/espn-supabase-sync.yml`; remote imports and a scheduled ESPN collector exist. Other collectors and historical completeness were not exercised. `.github/workflows/rebuild-chain.yml` imports seven named sources, while rule 7 still lists a narrower source set: written scope is drifting. | Medium to high: finish acquisition parity, reconcile the registry and prove replay from a clean runner. |
| Validate schemas, configuration coverage and units before valuation; distinguish unsupported, absent, null and real zero. | **Partly.** Read candidate builder/merge and `tests/test_source_combo_contract.py`; rule 4 protects missing-versus-zero semantics. Combo tests document source capability differences. This does not establish a single versioned schema for every stage. | Medium: shared source capability contract, explicit units, reject malformed/non-finite values and unexpected versions. |
| Use canonical player keys, fail closed on ambiguity and conflicting duplicates, and account for every join loss. Missing a high-value player is a correctness defect even if totals match. | **Yes for the documented identity path; partly end to end.** Read naming/matching rules, `pipelines/check_naming_drift.py`, `tests/test_espn_player_key_join.py`, and baseline commit's canonical naming fix. Candidate matching has review rows. `check_source_fidelity.py` still uses name fragments and skips absent pairs, so that check alone cannot prove full identity coverage. | Medium: canonical keys throughout diagnostics and conservation reports at joins. |
| Check row counts, position coverage, zero/null rates, rank/value distributions and largest changes against prior vintage. Quarantine suspicious shifts without deleting legitimate coverage. | **Partly.** Read `tests/test_espn_pool_cap.py`: deep tails preserve calibration and all players across scoring/team shapes. It specifically guards against destructive caps. Import health compares snapshot bytes and database counts. Broad source-specific distribution thresholds were not established. | Medium: explainable thresholds and review evidence, with real change and corrupted-input cases. |
| Bind lineage to actual bytes: raw snapshot → matched reference → section → adjustment inputs → served build. Preserve parent hashes and model/config version. | **Partly.** Read promotion hash checks in `pipelines/promote_comparison_section.py`, `pipelines/dist_manifest.py`, and `tests/test_lineage_snapshot_guard.py`. These protect selected boundaries. No complete dependency fingerprint consumed by every browser compute was demonstrated. | Medium: dependency manifest and compatibility checks, including mixed-build assets. |

## Pipeline health

| Practice (judgement) and why it matters here | Today and check performed | Adoption cost (judgement) |
| --- | --- | --- |
| Publish a coherent generation atomically; a failed rebuild must expose failure without publishing a mixed fixture or silently renewing its age. | **Partly.** Read `rebuild_comparison_chain.py`, rebuild workflow and `tests/test_rebuild_chain_workflow.py`. Failed chains publish status rather than the partially updated fixture. Promotions happen per source before the final fit, so local partial state still needs recovery discipline. Upstream import failures occur before the chain-status publication path. | Medium: transactional generation directory plus pointer/manifest, status publication for every failing stage. |
| Make runs idempotent by content/config identity; retry transient transport failures with bounded backoff, never review holds or semantic errors. | **Partly.** Chain documents stale-only rebuilding and no retry of held candidates. Workflow scheduling exists. ESPN scraper failure is swallowed with `|| echo`, followed by a save skip when no CSV exists; success therefore does not necessarily mean fresh acquisition. Repeated-run equality and bounded retry coverage were not verified. | Medium: explicit acquisition result, run fingerprint, duplicate-run and interruption tests. |
| Observe every stage with run ID, inputs, age, row counts, outcome, last attempt and last successful promotion. Alert on missed deadlines even when no job runs. | **Partly.** Read chain status handling, `build_pipeline_checkpoints.py`, and watchdog timeout code. Monitor artifacts exist. Human alert routing, acknowledgement, no-run detection and early-failure visibility remain **unknown**. | Medium: independent deadline checker and one accountable recipient; test delivery and missing-run conditions. |
| Treat data and code CI as blocking safety gates; monitor-only failure publication must use last-known-good product bytes. | **Partly.** Preview runs blocking `make validate`. Pages permits failed validation when the previous-commit diff is only under `dist/modules/`, after `make sync` has run. Its safety depends on generated output remaining suitable; inspecting that condition is not proof of immutable product preservation. | Medium: explicit product/monitor artifact separation, test failure paths and exact deployed digest. |
| Prove each guard discriminates: correct case passes, named defect fails, missing prerequisites report unknown/failure, and supported configurations are counted. Avoid tests pinned to incidental copy or today's player ordering. | **Partly.** Read `tests/test_espn_zeroed_staleness.py`, `tests/test_espn_pool_cap.py`, rendered gate self-tests and `tools/guard_harness.mjs`. Positive/negative tests exist. Fidelity checking skips missing pairs and stops after the first valid combo; an empty failure list is not evidence that all comparisons ran. | Medium: check IDs, applicability, evaluated denominator and mutations for silent skips/false alarms. |
| Keep durable backfill/rollback and rehearse restore into a candidate area with the same validation as forward changes. A rollback can itself be stale. | **Partly.** Promotion records retain replaced sections and before/after hashes; read `promote_comparison_section.py`. Operational restoration, full-generation rollback and historical replay were **not verified**. | Medium: documented drill using pinned inputs; mark restored vintages accurately. |
| Reproduce builds from a clean runner with pinned dependencies and least-privilege secrets; exercise local/CI parity. | **Partly.** Read workflows: Python 3.12 and environment-based Supabase shim; rendered gate has `package-lock.json` and uses `npm ci`. Raw snapshots are not assumed in unit CI. Real secret permissions, database policies and acquisition parity are **unknown**. | Medium: clean-run replay, dependency/runtime inventory and narrow collector credentials. |

## Dashboard health

| Practice (judgement) and why it matters here | Today and check performed | Adoption cost (judgement) |
| --- | --- | --- |
| Test rendered product and monitor against the built artifact and deployed URL. Require expected controls, sections, curves, table rows and network responses, not merely absence of exceptions. | **Partly.** Read `tests/rendered_gate/gate.mjs` and preview workflow: headless page errors and DDF pie totals are checked across up to 12 scoring/team shapes, with injected-error and bad-pie discrimination. Verdict rejects zero shapes, not fewer than 12. Console/resource errors, monitor rendering and source values are outside that gate; Pages does not run it directly. | Medium: complete coverage assertion, monitor route checks and deployed synthetic with build identity. |
| Compare selected rendered values and allocation against an independent oracle using pinned raw inputs; totals alone can conceal wrong players, ordering or units. | **Partly.** Read Python translation tests, guard harness and fidelity checker. These establish useful internal checks. Harness executes browser guard math, so shared implementation defects remain possible; fidelity script compares fixture/JSON rather than rendered cells. Independent rendered numerical agreement is **unverified**. | Medium to high: small transparent oracle, tolerances and known difficult players/configurations. |
| Evaluate freshness against current time and publisher deadlines, not solely another stale fixture's week. Label source vintage, derived build age and unavailable/unknown status next to the values. | **Partly.** Read `weekForSource`, `sourceIsStale`, context text and source labels in `curve-widget.js`: explicit stale-week labels exist. Week comparisons and adjustment pause state do not establish wall-clock expiry of every source, an old open tab or a jointly stale build. | Medium: verified expiry metadata, recheck on visibility/time boundaries and unmistakable local status. |
| Bind computes/caches to complete inputs and compatible data/model versions. On changes, refresh chart, pie, rank and table together; reject late results from prior configurations. | **Partly.** Read configuration/calibration caches and `refreshAfterWeightChange` in `curve-widget.js`; live recalibration and user-deselection state exist. Full mutation coverage for source bytes, roster, bench share and user inputs was not proved by the scoring/team gate. | Medium: dependency fingerprint and change-away/change-back tests, including rapid changes and asset mismatch. |
| Keep flexible inputs with explicit capability and feasibility states. Do not present fallback league values as the requested configuration. | **Partly.** Read `test_source_combo_contract.py`, roster controls, bench-share bounds and pause logic. Supported shapes and live controls exist. End-to-end arbitrary roster/user-input cases remain **unverified**. | Medium: boundary/property cases and clear unsupported-state assertions without freezing inputs. |
| Define user-facing SLOs and error budgets for fresh correctly rendered sessions; run independent synthetics that can report blocked verification. | **Unknown.** Local rendered tests are present; no complete operational SLO/error-budget or deployed synthetic evidence was established. Egress failure must mean verification unavailable, never product healthy. | Medium: freshness/correctness indicators, synthetic location outside agent lanes, stored evidence and alert ownership. |
| Verify keyboard navigation, visible focus, readable non-colour status, responsive layout and interaction performance at realistic source/player counts. | **Partly.** Read `aria-label`, `aria-pressed`, range/number controls and keyboard handling in `curve-widget.js`. Screen-reader behaviour, contrast, mobile layout and measured performance budgets are **unverified**. | Low to medium: keyboard/mobile checks and repeatable load/interaction measurements. |

## Test against the known failures

These are **judgement** applications of the practices to the incidents reported
by JEG-78, not declarations that the production incidents were re-tested here.

- **JEG-8, failed scheduled rebuilds:** missing-run SLOs and failure publication
  at import as well as chain stages catch the outage; served-age checks catch
  its user impact even if the status pipeline also fails.
- **JEG-51, nonexistent combo returned green:** enumerate the capability matrix,
  record evaluated comparisons and inject suffix/non-default-combo cases.
- **JEG-68, correct markup flagged:** derive the expected direction from input
  methodology; valid pre-valued inputs must pass alongside broken-direction cases.
- **Typo-pinned test blocked deploy:** test semantic behaviour and distinguish
  presentation contracts from incidental wording; retain legitimate deploy gates.
- **JEG-44/47, page-load exception:** rendered artifact gate plus injected throw;
  deployed synthetic confirms the exact build actually reached the browser.
- **JEG-18/55, machine-only snapshots:** shared replayable storage and clean-run
  acquisition demonstrate independence from one operator's disk.
- **JEG-67, destructive no-op pool cap:** deep-tail metamorphic tests assert
  retained values, calibration and complete player coverage together.
- **Agent egress blocked:** publish verification-unavailable status and preserve
  last verified time; independent hosted verification supplies the missing proof.

## Validation and limits

`make validate` checks naming, reference generation, artifact sync, guard-harness
positive/negative cases and the unit suite. It does **not** run `test-integration`
or the rendered browser gate in this baseline Makefile. A pass establishes those
local contracts, not live freshness, Supabase correctness or deployed rendering.
No code, fixture or runtime data changes are part of this assessment.

**Established check result:** `make validate` failed on baseline `81b2a8d` in
`tests.test_vorp_translation_unified.TestScoringAwareFlex.test_unified_custom_capacity_and_legacy_parity`
with nine flex-count mismatches (for example, 6 versus 5). The same test module
was run directly and reproduced the failures; its code and inputs are unchanged
from the baseline. Validation stopped there, so subsequent unit modules were
not exercised by this run. Generated sync outputs were discarded, leaving only
this document in the proposed change. The failure requires separate code triage;
this docs-only draft must not be described as validation-green or merge-ready.
