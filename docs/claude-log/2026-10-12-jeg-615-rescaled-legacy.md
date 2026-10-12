## 2026-10-12 - JEG-615 rescaled copy in the legacy dashboard and dataset_status

Copy only; follow-up to JEG-510. "as published" -> "rescaled" in app/trade-value-chart (comparison-dashboard.js badges and descriptions, curve-widget.js group label, index.html method caption), app/inspector/math-inspector.js table title, and pipelines/lib/dataset_status.py (method label "Rescaled (reindexed)", method descriptions). app/v2 untouched. Rebuilt with make sync.

### Verified (check named)
- make validate exit 0 (see PR).
- Tests edited only because the pinned string is what changed: test_static_export (group label), test_razzball_production_followups (badge text, in both the embedded JS copy and the assertions).

### Claimed, not confirmed
- Internal comments and docs (methodology.md, v2-design-notes.md) still say "as published"; left as history.
