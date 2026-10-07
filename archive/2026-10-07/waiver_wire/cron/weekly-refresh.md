# Waiver dashboard refresh runbook

There is no dedicated waiver-dashboard cron. The board refreshes as part of
the weekly chain (Monday imputation -> Wednesday ECR loop). Manual refresh:

1. `python3 pipeline/bin/impute_monday_tv.py` — rebuild Monday legs
   (`results/imputed_proj_<scoring>.json`).
2. `python3 pipeline/bin/build_waiver_dashboard_data.py` — rebuild the
   dashboard data file.
3. `python3 pipeline/bin/coverage_check.py` — fail-closed audit; exit 0
   required before publishing.
4. Re-stage `dashboard/index.html` from the artifact edit and verify the
   live page before announcing.

Monday-safe: the delta layer never requires fresh expert ECR.
