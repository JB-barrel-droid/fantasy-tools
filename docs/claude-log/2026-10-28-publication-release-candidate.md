# Publication release candidate, 2026-10-28

Combined existing draft PRs #1054 (JEG-1206) and #1059 (JEG-1215) on main
3919f998. Source-health #1022 and #1042 remain separate because their weekly
freshness plus alert dependency crosses source-isolation build scope.

The rebuild keeps #1054's ordinary three-attempt push from an isolated
worktree. The pause guard runs before the root candidate commit and immediately
before each isolated worktree push; it fetches current-main control on each
check. An active pause saves the staged candidate patch and exits the
publication step before the retry, while ingestion/validation/downstream jobs
continue. Confirmed pushes still drive Pages and permit stuck-alert closure.

Targeted local regression: 154 workflow, retry, pause, alert and timestamp
tests passed, including an active-pause candidate retention case. Full combined
PR CI and independent review are required before merge. No live pause, merge,
workflow dispatch, Supabase change or deletion occurred.
