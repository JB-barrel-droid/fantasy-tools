# Risk Register

Last updated: 2026-09-22.

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
| Player news can be stale, duplicated, or mismatched to the wrong player. | High | Open | News ingestion must key by canonical numeric `player_key`, preserve headline publication timestamps, and label each headline pre-value or post-value relative to the value artifact timestamp. |
| Pure VORP can be confused with indexed trade value if plotted on the same basis. | Medium | Controlled | Keep Pure VORP behind a separate value-basis mode and label it as ESPN PPG above waiver, not fixed-pie trade value. |
| Public copy currently says `FantasyPros` where product rule says `ECR`. | Low | Known defect | Track for later; do not fix during discovery/local equivalence unless explicitly scoped. |

| Adjusted source projects sit above the ESPN leg's scale at QB. | High | Open | Measured 2026-09-22 on `full_12`: QB peaks 26.6-34.1 against the leg's 17.2 (1.5x-2.0x); RB 85.0-92.5 against 81.8. These four curves are ON by default and the hero copy promises one trade-value scale. Surfaced on the page as the `adjusted-scale-agreement` chart-health warning. The distortion is in the stage-2 adjustment cells (per-position `alpha + beta * value` refit, then one global renormalisation), not in the frontend. |
| CBS publishes only 124 players and 16 QBs; Bo Nix is not among them. | Medium | Open | The fixture matches the promoted CBS reference exactly, so nothing is being dropped downstream. Whether CBS published him is unverified: `data/raw/sources/` does not exist on the workstation and the recorded CBS chart URL now 404s. Needs a current CBS chart URL or Supabase read access to settle. Do not impute a value. |
| Importer/health assumed one vintage per table; multi-week tables broke both. | High | Fixed 2026-09-25 | `import_supabase_references.py` and `verify_import_health.py` read ALL historical rows per source, so once USA Today held weeks 2+3 the import failed closed and the health gate would TABLE_DRIFT on retained older weeks. Fixed: `_select_latest_week()` / `_select_latest_snapshot_date()` scope reads to the latest complete vintage (never blended); manifest records scoping + `week_designated`; health scopes its re-query to the manifest vintage. `derive_db_vintage()` / `table_vintage()` deliberately NOT weakened (direct unit tests prove they still fail closed on multi-week rows). |

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
