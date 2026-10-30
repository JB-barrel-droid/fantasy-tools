# Source isolation publication integration, 2026-10-28

From reviewed #1063 at e28410b3 and #1050 at 55ef634a. #1063 remains intact
as the smaller fallback. The new branch is
`be/publication-source-isolation-release`; it does not use an unrelated ticket
number in its branch name. No main merge, production workflow dispatch,
Supabase change or pause activation.

The rebuild workflow records the original complete `make validate` exit code
before printing its log. If red, it asks the reviewed isolator to identify one
fully attributable changed source and restore only its published section. A
decline/error records non-green chain status and exits. After isolation it runs
exactly one complete validation retry on the rolled-back fixture, without
running the source chain again. A red retry records failure and exits. A green
retry still requires `confirm`; any confirm failure records non-green status
and exits before fixture publication. The existing publication retry, pause
expiry, artifact retention and confirmed-publication alert remain intact.

The injected workflow-shell tests cover healthy first pass, isolation decline
and error, failed retry, confirm error, and healthy source advancement only
after retry and confirm. The isolator's own suite covers source attribution,
rollback boundaries, fixture/leg integrity and corrected-save release.

Current-head CI and independent review remain release gates.
