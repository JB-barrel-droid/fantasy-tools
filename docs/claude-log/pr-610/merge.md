## 2026-10-16 - PR 610 (JEG-620/621) merge prep

- Merged origin/main in, ran make sync (generated files regenerated, not hand-merged).
- Fixed: added divergence-issues.yml (JEG-610, push/manual, no schedule) to unmonitored_workflows in config/monitoring_coverage.json; test_real_repo_is_fully_covered was failing on it.
- Verified: test_sharks_savers, test_fidelity_sharks, test_source_probe, test_monitoring_coverage 91 passed.
- Not applied: supabase/migrations/sharks_probe_schedule_20261015.sql (needs Jeremy's go).
