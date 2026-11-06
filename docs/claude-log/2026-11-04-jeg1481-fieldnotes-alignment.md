## 2026-11-04 - Isolated weekly page Fieldnotes alignment / JEG-1481

Contract: Jeremy requested background visual alignment with DDF's developing
design language. Same sole weekly-page owner, branch and draft PR #1294; base
head `94044b3c613ffe6bf0743fd3c21bd03039a0cf98`. Central design coordinator
confirmed weekly paths are free. Shared shell, sources and other page owners
remain read-only. No live-route wiring, data activation, merge, deployment,
Supabase, deletion, credential/access changes or cap override.

### Verified (check named)

- Read the exact current review board, Build a Trade revision 7 and final-nav
  Settings Pages; inspected their actual images through authorized Page references.
  Exact URLs and image hashes are in `app/versus-vegas/DESIGN.md`. The concepts
  are not all approved; only the coordinator-confirmed common shell rules and
  component contract are used. Latest Home → Build a Trade → Trade
  Recommendations → Values → More overrides older contract nav examples.
- Fetched `docs/design/fieldnotes-components.md` and the shared CSS from GitHub.
  Existing local/current-main Fieldnotes foundation blocks match SHA-256
  `7becddf342f069d6d7d2404acc9f664c40a0ce7299001a1f173143fbd387e4e3`.
  The renderer now reads this existing foundation, its spacing roles, its one
  Fraunces declaration, font and OFL license. No competing palette, duplicate
  font declaration or shared token edit is introduced. All page rules are
  scoped to `.versus-vegas`.
- Two isolated alternatives: compact health band and desktop source side
  panel. Both retain the same source payload, URL filters, comparison units,
  null/zero distinctions, identity/source disclosures, currentness/provenance
  and held verified-play state. The header shows final nav context without
  production links. Mobile rows expose the same data without page overflow.
- `python3 -m unittest tests.test_pipelines_import_standalone tests.test_weekly_inputs_contract tests.test_build_weekly_inputs tests.test_versus_vegas`:
  112 tests pass (the original 110 plus two presentation/payload regressions).
  Node syntax and `git diff --check` pass. Receipt:
  `/tmp/jeg1481-design-bounded.log`. No existing assertion was weakened.
- `python3 app/versus-vegas/build_review.py --out /tmp/jeg1481-fieldnotes-review`
  exports `compact.html` and `analysis.html` using the existing frozen fixture,
  explicitly labeled synthetic. Shared input digest
  `f3d863365291561eaed51fce42fc4d039dccdadbc6f6a947721c87e8a17f8d48`.
  Real `--input` artifacts retain their original source values and provenance;
  no numbers are copied from the trade concepts and no live values are invented.
- PR #1304's broad CI was active when checked. Only bounded local suites and
  the existing focused draft renderer are used for this update; broad suites
  remain deferred. No denied Linear/browser/artifact action is retried.

### Claimed, not confirmed

- The focused browser tests now exercise both alternatives at 390/1280px,
  geometry (1184px, 16/32 gutters, 16/9 radii, 44px targets), visible zero,
  above-fold first row, nav order, URL reload/back, identity and no external
  requests. Four screenshots are configured for the bounded CI artifact;
  exact new-head result/artifact receipt will be recorded in the PR/handoff.
- Local Chromium remains absent; no download is attempted. This environment
  exposes no cloud browser tool. Snapshot rendering in existing CI is not a
  claim that screenshots were downloaded or visually inspected here.
- Earlier 110 local/17 focused-CI and independent inspection receipts remain
  baseline evidence scoped to their old head. New design-head rendering and
  independent design review remain distinct gates. Source activation,
  verified-play compute, public route integration and release are not done.
