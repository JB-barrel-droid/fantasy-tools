# 2026-10-12 JEG-625 land PR 534 (timestamp parser)

- Merged origin/main into fix/timestamp-parser-py39 (conflicts only in generated app/ and dist/ files; took main's, regenerated with make sync).
- Removed an accidentally committed `.venv` symlink from the PR.
- Verified: make validate exit 0 on py3.12; tests.test_timestamps (includes the call-site guard test_no_raw_calls) OK.
- Claimed, not checked: py3.9 run of the full suite.
- PR 530 not landed; left a comment asking it to rebase and route fromisoformat calls through parse_iso_timestamp.
