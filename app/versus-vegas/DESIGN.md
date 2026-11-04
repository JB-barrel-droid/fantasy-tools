# Isolated Fieldnotes alignment / JEG-1481

Inspection baseline: PR #1294 head `94044b3c613ffe6bf0743fd3c21bd03039a0cf98`.
The design coordinator confirmed this lane owns its weekly paths; shared shell
and tokens are read-only. This is a draft page update, not public integration.

## Verified references

- Current [review board](https://chatgpt.com/space/page_326d74c86ee48191b676a2ff673da36f), read 2026-11-04: visible numbers first; optional analysis in one workspace, no mandatory review page. Individual trade concepts remain in review.
- [Build a Trade revision 7](https://chatgpt.com/space/page_eb15c9180f308191b6b0a36b86c46ea3), including the actual image `libfile_89b5ad25664c81918a72dd6882c5bfa9`: cream canvas, dark green header, serif brand/title, sans-serif data, compact ruled rows, inline analysis. Image SHA-256 `d917a6f29b7f60850912af9f21b1c05bad86eba846e7b52bdc4d8bd4e4f1949a`.
- [Settings reference](https://chatgpt.com/space/page_0729142adb2c81919cebc9d7a08eee0f), image `libfile_c05c77195430819192cb6e9de0f5df64`: restrained rounded panels/controls and compact grid. Image SHA-256 `473295ade16520ada474559f63650fd4492082558d0cfd792b3545b861cbe7f5`.
- [Component contract](https://github.com/datadrivenfootball/fantasy-tools/blob/main/docs/design/fieldnotes-components.md), fetched directly from GitHub: roles, spacing, shape, focus/contrast, self-hosted Fraunces, native disclosures. Actual implementation: `app/v2/v2.css:2471` onward; compact row and right-aligned numeric treatment: `app/v2/values-fieldnotes.css:74` onward.
- Latest coordinator-confirmed navigation overrides older examples in the contract: **Home → Build a Trade → Trade Recommendations → Values → More**. No old Buy & sell / Check a trade labels are adopted. A standalone draft may show the shell context but must not wire production routes.

## Source inspection and mapping

| Area | Existing owned page | Verified alignment |
| --- | --- | --- |
| Type | Georgia display, system UI, oversized title | Existing Fraunces 600 display declaration; sans-serif body/data; shared 52/37px hero roles |
| Canvas / ink | Local literal palette in `style.css` | Canonical `--ddf-canvas`, `--ddf-surface`, `--ddf-ink`, `--ddf-muted`, semantic roles |
| Geometry | 1160px, 28px desktop gutter, square cards, 2px controls | 1184px max, 32/16px gutters, 16px cards, 9px controls, 44px targets |
| Table / row | 17px vertical cell padding, 650px minimum width | Compact ruled desktop table, tabular/right-aligned numbers; readable mobile row layout without hiding source values |
| Navigation | None in standalone page | Page-local non-routing shell preview in final label order; shared shell remains untouched |
| Disclosure | Native identity/source details, global styling | Shared native disclosure/focus treatment, scoped to this page; no mandatory step or hidden replacement values |
| Above fold | Large title, stacked health before table | Compact title/context, filters, visible coverage and first comparisons; keep freshness and missing reasons available |

## Two bounded alternatives

1. **Compact notebook:** source health in a compact band above the comparison;
   primary rows stay wide. Recommended starting point for the weekly workflow.
2. **Analysis beside the table:** the same source health in a desktop side panel,
   inspired by optional inline analysis. Same data/filter semantics and mobile
   order; no second page or additional calculation step.

Both consume the existing shared token/component definitions read-only. No
competing palette, font declaration or shared token is authored here. Source
images guide hierarchy; token geometry is authoritative rather than raster
measurements. Numeric content is never copied from the trade design images.

## Evidence and limits

The existing 110 local / 17 focused-CI receipts are baseline evidence for
94044b3c, not an automatic pass for a new design head. Comparison producer,
validation, unit conversion/refusal, coverage and filter behavior stay intact;
design checks are bounded to this isolated page while PR #1304 CI is active.
Rendered alternatives/snapshots must preserve actual input values and provenance;
synthetic fixture previews must be labelled as fixtures, never live values.

This environment currently has no installed Playwright Chromium executable and
no exposed cloud browser tool. Prior browser/artifact download denials are not
retried. The existing bounded CI renderer can produce isolated snapshots; do
not claim visual inspection of images that cannot be retrieved here.

First concrete patch: `template.html`, `style.css`, presentational row attributes
in `view.js`, and `fieldnotes_styles()`/layout selection in the offline renderer.
The shared Fieldnotes foundation is read and bundled at build time, not forked.
Its inspected local/current-main block SHA-256 is
`7becddf342f069d6d7d2404acc9f664c40a0ce7299001a1f173143fbd387e4e3`.
The original single font declaration embeds the existing font and license for
offline viewing. Compact and analysis exports are generated by `build_review.py`;
same payload, different layout attribute. Local bounded suites now pass 112
tests (the original 110 plus two presentation/payload regressions). Focused CI
will run the original behavior checks plus both layouts at 390/1280px and save
four rendered screenshots. The older 110/17 receipts remain scoped to their
original head.
