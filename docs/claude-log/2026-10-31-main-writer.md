## 2026-10-31 - Dedicated main writer (JEG-1441)

Contract: move the ten main-capable data workflows to one repository-scoped
GitHub App, with its credentials held only in the main-only environment.
People and agents will require PRs once the separately approved ruleset is
applied; this PR supplies the workflow side of that change.

### Verified (check named)

- The 98 offline tests in the `main-writer-checks.yml` command passed locally,
  including credential-destination/ref refusal, no persistence, security-boundary
  mutations, publication guards and unconditional deploy validation.
- Actionlint 1.7.12 passed all eleven changed/new workflows. A read-only PR
  workflow runs these contracts on the exact PR head without App credentials.
- GitHub environment metadata: `main-writer` (25881732773) allows only the
  exact `main` branch (policy 65030703), no tags, and no administrator bypass.
  Both approved App secret names are present. No values are in this repository.
- Existing App 5555063 is installed only on fantasy-tools. Its original key
  download was uploaded via stdin and deleted immediately after success.
- Full `make validate` reached 45 passing unittest commands, including all
  eight concurrent-main Git scenarios, then failed the unchanged Finder saved
  team keyboard test (`'' != 'beta'`, line 415). A single isolated baseline
  run fails identically on main c267aa71ef1d445670516b1858e0f9dfe5a48f93;
  the test, seven helpers and app/v2 match the migration branch. Existing
  PR #1233 already owns the macOS keyboard-test repair. It was not duplicated.

### Claimed, not confirmed

- Full `make validate` is blocked by that baseline Finder failure; it has not
  passed. Exact-head PR CI and independent Claude high-risk review remain
  pending. Publishing a draft does not waive those gates. No merge, ruleset or
  live App-authored data publication has been performed by this task.
- Refresh tests must be dry runs with no publication. Actual App-write proof
  must come from an authorized normal refresh. App-authenticated data pushes
  replace the redundant explicit Pages/render dispatches; their existing
  unconditional validation gates remain unchanged.

The credential helper uses Git's private stdin/stdout protocol without saving
tokens to config or disk. Main never falls back to the default token; branch
jobs have no access to the environment. The job steps share YAML anchors, so
tests that previously depended on literal step layout now resolve that anchor
and retain mutation checks. The old explicit Pages-dispatch assertion was
replaced because App pushes trigger the existing Pages/render push routes.
