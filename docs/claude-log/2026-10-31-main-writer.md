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

### Publication-boundary correction after diagnostic audit

Acknowledged the old-head audit: rebuild-chain's shared commit script named
main explicitly while its branch job retained Contents write. Added a runtime
main-ref guard before staging and reduced that branch token to Contents read.
The guard fails closed when GITHUB_REF is absent. Existing pause/main scenario
harnesses now supply the main ref explicitly; their assertions are unchanged.

Verified: the new real-script test failed before the correction because its
throwaway local remote's main moved. Its companion mutation removes the guard
and proves the same unauthorized main write becomes observable. The scenarios
also require the branch ref to remain unchanged and reject an absent runtime
ref. These local remotes do not contact GitHub. CI now runs the concurrent-main
suite, rather than relying only on workflow text assertions.

Dry/check modes no longer mint the App token in weekly-store, status-history,
or ESPN sync; ESPN sync also skips its Git publication step in dry mode.
Verification dispatches are limited to espn-history-probe with dry_run=true:
that path skips App minting, Git publication and monitoring publication. Other
workflows' dry inputs can retain existing monitoring side effects and are not
authorized verification routes. No Supabase behavior was changed.

The original 535edb4 head passed all 13 GitHub checks, including full preview
and render, with strict reference comparison at zero mismatches. That receipt
belongs only to the old head. The corrected head needs fresh CI and independent
Claude Opus/high review. Local full validation's known baseline Finder failure
and the existing PR #1233 ownership remain unchanged; neither is waived here.

Verified after the correction: all 111 offline security/publication contracts
passed in 61.929 seconds. Actionlint 1.7.12 passed all eleven workflows. The
old publication-pause harness initially omitted GITHUB_REF; supplying the main
ref made that scenario explicit without changing any assertion. All branch,
missing-ref and guard-removal mutation scenarios passed.

### Approved trigger change and final review follow-up

Jeremy approved all three concrete decisions at 18:57 UTC on 2026-10-31:
manual-only divergence issues, GitHub's existing automatic deletion of only
remote refs/heads/codex/JEG-1441-main-writer after gated PR #1259 merge, and a
public PR-description update with verified current implementation and gates.
No repository deletion setting or local branch deletion is authorized by that
exception. The separately approved named scratch cleanup remains its own scope.

The divergence workflow intentionally removes its pre-existing main-push
trigger, including human pushes and PR merges, rather than merely excluding
App pushes. Manual dispatch still invokes the same issue builder, now naming
the served report explicitly. No Linear credential was read, changed or used.

The shell publication wrappers now require GITHUB_REF with ${GITHUB_REF:?}
before calling Git, complementing the credential helper's existing refusal of
empty refs. A real-shell regression test executes every extracted wrapper with
both missing and empty refs and a local fake Git command; Git must never be
called. The dispatch-only contract and wrapper test both failed before these
changes. Existing security assertions are retained, including a mutation that
restores the old main fallback. The credential unit matrix now directly covers
an empty ref. No live publication or external API call is used in these tests.

Verified earlier: all 13 CI checks passed on both 7c6e8c6 and 6772f10b. The latter
strict comparison agreed on 1,234,508 values with zero mismatches across all
seven sources, and the rendered gate had zero page errors and zero of twelve
fixed-pie failures. These are receipts for those heads only. The full independent
Claude Opus 4.6/high review passed 7c6e8c6 (session
28b52122-1634-4e7a-818d-7bc990cd8abe). A separate charter review comment also
identified the trigger/fallback follow-ups; those findings are addressed here.
The final changed head still requires fresh CI and one Claude high-risk delta
review. Main was integrated normally through 12887fc7, with no rebase or force
push and no generated changes relative to main. Ruleset activation still needs
fresh action-time confirmation; App publication proof must use an authorized
normal refresh, and all refresh verification tests remain non-publishing.

Verified after the approved change: all 118 offline credential/publication and
manual issue-builder tests passed in 52.397 seconds. The existing served-report
contract passed separately, and actionlint 1.7.12 passed all twelve workflows.
Whitespace checks passed. These tests make no live Linear or GitHub writes.
