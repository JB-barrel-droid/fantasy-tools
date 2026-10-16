## 2026-10-16 - PR 616 (scheduled Sharks save workflows) merge prep

- Merging #610 with --delete-branch deleted #616's base branch, which closed #616 and it could not be reopened. Re-opened the same branch (jeg620-621-workflows) as a new PR against main.
- Merged origin/main (clean), ran make sync.
- Verified: test_sharks_savers, test_fidelity_sharks, test_source_probe, test_monitoring_coverage 95 passed.
- Not applied: supabase/migrations/sharks_probe_schedule_20261015.sql (needs Jeremy's go).
