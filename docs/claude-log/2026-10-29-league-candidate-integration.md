## 2026-10-29 - League candidate integration

Contract: refresh #1072 after #1069 and #1071 published and passed live QA,
then require fresh exact-head CI and independent delta review before release.

### Verified (check named)

- Normal merge of current main `f88a96e83cae56ae01b4f20c856ddb38f11c9d3a`
  into previously reviewed `b26a4795a6c26ccac2ed3b304cdacf1b1fdc5a8b`.
  No rebase, force push, Supabase change, or unrelated deletion.
- HANDOFF conflict keeps both lane sections. League detail conflict preserves
  main's new starter-gain explanation while reading the full lazy fit.
- Source inspection found main's additional `ourFitDetail` table reader of
  `r.fit.us.starterDelta`. Compact fit now keeps that scalar; verbose fit data
  remains lazy. The harness asserts exact scalar parity with direct full fit.
- Prior exact-head CI and isolated Mac browser evidence is recorded in #1072.
  It does not substitute for this integration head's new checks.

### Claimed, not confirmed

- Integration-head CI and independent delta review pending at commit creation;
  terminal results are recorded on #1072 before release.
- Production publication/live verification still pending. Actual Jeremy league
  not replayed; synthetic regression and warm browser scenario are not user data.
