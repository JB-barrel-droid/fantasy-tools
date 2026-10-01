# Preview deploys (JEG-31) — Phase 1 approved, being built

Status: Jeremy approved the Phase 1 design and answered the three open questions on
2026-10-01 (see "Decisions"). Sections below describe the design; "Not built yet" items are
marked as the work lands. Linear:
JEG-31. Written 2026-10-01 by Claude (Claude lane); Muse reviews for methodology,
Jeremy decides.

## Goal (from JEG-31)

View a chart change at a non-production surface before it goes to production, serving
the same `dist/` the production deploy would publish for that commit, with a
one-page runbook. Out of scope: changing the production deploy itself.

## What production does today (verified)

`.github/workflows/pages.yml` triggers on push to `main`, manual dispatch and a daily
schedule. It runs, in order: checkout (`fetch-depth: 2`), Python 3.12, `make sync`,
`make validate` (`continue-on-error`), `build_source_value_lineage.py`
(`continue-on-error`), a "product changed" check, a blocking gate that fails only if
product files changed and validation failed, then uploads `dist/` and deploys it.
A recent run took about 75 s end to end; the deploy step about 8 s; the Pages
artifact was about 1.2 MB. [read `pages.yml`; job `110472801856` of run
`36892947644`]

No workflow runs on pull requests (GAP-016). Pages serves one site per repository, and
`deploy-pages` replaces the whole site, so a preview cannot live beside production on
the same repository without changing the production deploy.

## Findings that shape the design (verified 2026-10-01 at `6216144`)

1. **`make sync` is deterministic per commit, with one exception.** `build_tag()`
   derives the tag from the HEAD commit's own time and SHA, not from `now()`. I ran
   `make sync` twice on the same commit 61 seconds apart. Exactly one file differed:
   `assets/reference-freshness.json`, field `generated_at` (wall-clock). Every other
   file in `dist/` and `app/` was byte-identical.
2. **That same file is calendar-dependent.** It also records `today`, per-item
   `age_days`, `status` and the stale/expired counts, all computed against the day the
   build ran. So the acceptance criterion "byte-identical `dist/` for the same commit"
   cannot hold literally across two different days, and across two runs on the same day
   it holds except for `generated_at`.
3. **`make serve` does not serve what production serves.** It serves
   `app/trade-value-chart`; production publishes `dist/`. A local check through
   `make serve` therefore proves nothing about the published bytes.
4. **The lineage step cannot run from a clean checkout.** Locally it exits 1:
   `missing required source snapshots for ['fantasypros', 'usatoday'] (data/raw is
   gitignored)`. In production it is `continue-on-error`, so it can fail without
   failing the deploy. *Unverified in CI:* I reproduced this locally; I did not read the
   CI step's log, and the API reports `continue-on-error` steps as `success`.
5. A PR-triggered workflow checks out a merge ref by default. Building that would give a
   different build tag from the PR head, so the preview must check out the PR head SHA.

## Options for the preview surface

| | Surface | Setup needed from Jeremy | Real URL | Touches production deploy |
| --- | --- | --- | --- | --- |
| A | Workflow artifact (the built `dist/` plus a manifest) and a local-serve runbook | none | artifact download link, not a served site | no |
| B | A second Pages site in a separate repository, fed from the same build | create a repo, enable Pages, add a deploy token secret | yes | no |
| C | A third-party host (Cloudflare Pages, Netlify, etc.) | account plus secret | yes | no |

**Recommendation: A first (Phase 1), B later only if a served URL turns out to be
needed.** A needs no new accounts or secrets, cannot affect what users see, and also
closes GAP-016 because the same workflow runs `make validate` on every PR.

## Phase 1 design (needs sign-off before I build it)

1. **`.github/workflows/preview.yml`**, triggered by `pull_request` and
   `workflow_dispatch`. Checks out the PR head SHA with `fetch-depth: 2`, then runs the
   same build steps as `pages.yml` in the same order. It has no Pages permissions and
   no deploy step. It uploads `dist/` and a manifest as an artifact and comments the
   link, build tag and manifest root hash on the PR.
   `make validate` is **blocking** here, unlike `pages.yml`, because on a PR it is the
   gate; the lineage step stays `continue-on-error` exactly as in production.
2. **`pipelines/dist_manifest.py`**: a sorted per-file SHA-256 manifest and a root hash
   of `dist/`. It treats the one calendar-dependent field as a named, documented
   exception: in `assets/reference-freshness.json` only `generated_at` is ignored, and
   `today` is recorded so two manifests are only compared when it matches. A `--compare`
   mode lists every differing file.
3. **Drift guard test**: parses `pages.yml` and `preview.yml` and fails if the preview's
   build steps are not the production steps in the same order, so the preview cannot
   quietly stop proving anything.
4. **`make preview-local`**: `make sync`, then serve `dist/` (not `app/`).
5. **A one-page runbook** (this file, rewritten after the build): when to use a preview
   and when to push to production.

Tests will be negative-tested: change one byte in a synthetic tree and the root hash
must change; change only `generated_at` and it must not; change any other field of the
freshness file and it must; remove a step from `preview.yml` and the drift guard must
fail.

## Decisions (Jeremy, 2026-10-01)

1. **Surface: Option A**, workflow artifact plus a local-serve runbook. No accounts or
   secrets. B and C stay possible later if a served URL is needed.
2. **"Byte-identical" means:** every file identical, with only `generated_at` in
   `assets/reference-freshness.json` ignored, compared only when `today` matches. No change
   to `check_reference_freshness.py`.
3. **`make validate` is blocking on pull requests**, unlike `pages.yml`.

## Not verified

- That the Phase 1 workflow runs as designed; it has not been written or run.
- The lineage step's behaviour in CI (finding 4).
- Whether `actions/upload-artifact` retention and artifact size limits suit this repo
  (the artifact is about 1.2 MB, so this is unlikely to matter).
