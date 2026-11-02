## 2026-11-02 - JEG-1468 shared front-door test follow-up

Contract: reuse the coordinator's bounded front-door identity fix on PR #1286,
preserving its validation log and the already-reviewed CORS implementation.
No additional main catch-up or production operation.

### Verified (check named)

- The integrated branch still contained the former-owner SITE literal.
  Cherry-picked `be2cb8cd19fce2cfa09101dd5b299c85b266c907` with provenance.
  Its test and JEG-1450 validation log exactly match the supplied commit
  (`git diff --exit-code`); no alternative fix was authored.
- With `DDF_GITHUB_REPOSITORY=datadrivenfootball/fantasy-tools`, canonical
  Python 3.12 passed all 12 tests in FrontDoorIdentityTests and test_org_cutover.
  The first sandboxed attempt could not bind its local build-helper server;
  the same focused command passed when localhost execution was permitted.
- CORS source, its regression and the security workflow remain byte-identical
  to reviewed head `8f394cba1287e0d2cc3d4e5d12c95beda020ffe9`.
- Generated build output from the focused test is excluded from the PR.

### Claimed, not confirmed

- The earlier `f891588f` CI attempt is superseded by this bounded integration.
  Full ordinary PR CI and the parent's independent integration delta review
  must qualify the new exact head. No full local suite was repeated.
