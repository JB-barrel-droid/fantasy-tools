# Risk Register

Last updated: 2026-09-19.

## Active Risks

| Risk | Severity | Status | Mitigation |
| --- | --- | --- | --- |
| Muse ZIP/code/data export is missing from the workspace. | High | Open | Continue with PDF-based planning only; source verification and local reproduction require the export. |
| Git metadata creation is blocked at `.git` in this workspace. | Medium | Open | Use normal files for now; if possible, use an external Git directory or ask for workspace permission repair before meaningful code migration. |
| Documentation may drift from implementation. | High | Open | Treat actual source files as authoritative once ZIP is available; document every discrepancy. |
| Production Supabase could be accidentally modified. | High | Controlled | Discovery is read-only; no production credentials have been used. |
| Secrets could be copied from export or browser sessions. | High | Controlled | `.gitignore` excludes env/private paths; do not commit cookies, keys, or service-role credentials. |
| Missing/null values could be silently converted to zero. | High | Open | Add tests before logic migration; preserve null display and line breaks. |
| Source-lock, preseason-lock, or disagreement ordering could drift. | High | Open | Port existing frontend behavior first; add golden ordering tests. |
| Dynamic Y-axis behavior could regress to a 70 cap. | Medium | Open | Test dynamic nice-step scaling from visible data max. |
| Muse publish path is nondeterministic. | Medium | Existing | Replacement should use deterministic static build/deploy, but only after equivalence. |
| Manual curation gap from `sources_data.json` to `comparison-sources-data.json`. | Medium | Existing | Script the copy/curation later; do not block static reproduction. |
| ECR content freshness gate currently blocks full rebuilds. | Medium | Existing | Preserve fail-closed behavior; static reproduction should use current finished artifacts first. |
| DDF/projection-derived values are stale in-season. | High | Open | Do not use DDF as the current source of truth. Preserve existing exported behavior for equivalence, but prioritize fixed-pie source comparison and require freshness validation before reviving projection-derived values. |
| Public copy currently says `FantasyPros` where product rule says `ECR`. | Low | Known defect | Track for later; do not fix during discovery/local equivalence unless explicitly scoped. |

## Known Issues Not To Fix First

- Historical trade designer/calculator is not part of the first migration.
- Some older cron instructions are stale.
- Some documentation conflicts with live code.
- Razzball integration is pending in the current finished data.
- `audit_continuity.js` is retired and should not be revived blindly.

## Required Approval Gates

Stop for user approval before:

- Any production Supabase write or schema change.
- Any public cutover from Muse to the replacement.
- Any credential/login action.
- Any business-rule change not inferable from current implementation.
