# Simplified private review and full-design handoff

Owner: JEG-1263 / cloud task `01a19e2c-1d9b-712e-a55e-eecbd8b04020`, draft PR #1297.
Full design and JEG-1483 math/coverage owner: `01a19d4e-1682-7576-aa51-fc43413330e6`.

The builder archives an already-fetched existing provider commit into a temporary directory, overlays only
`app/v2/simplified-site.js` and `.css`, and runs the ordinary static build. It does not merge refs, fetch, push,
deploy, change production or copy user workspaces. The artifact uses historical fixtures and explicitly pins its
display clock to their content week. That pin and the real provider/overlay hashes are in `review-manifest.json`.

```sh
CHROMIUM_PATH=/usr/bin/chromium RENDER_TESTS_REQUIRED=1 python3 tools/jeg1263/build_private_review.py \
  --provider-ref 714bb4a5b20198effaff6cfc91c0102b8587606d --output /tmp/new-private-review
CHROMIUM_PATH=/usr/bin/chromium python3 tools/jeg1263/verify_private_review.py \
  --site /tmp/new-private-review/site --evidence /tmp/new-private-review/evidence
python3 -m http.server 8763 --bind 127.0.0.1 --directory /tmp/new-private-review/site
```

Open `http://127.0.0.1:8763/review.html`. Full and Simplified use the same existing saved workspace. Normal entry
preserves it; only the explicit historical-example action replaces the preview origin's workspace. The zip is an
integration artifact for the full-design owner's existing private destination, not a second production site.

## Bounded module contract

- Only the scoped Simplified JS/CSS and dedicated tests belong to this lane. No shared navigation, shell, bootstrap,
  Fieldnotes or value-engine files are edited. Keep the exact name **Simplified site** and routes
  `#simplified-site` and `#simplified-site/trade/<encoded stable id>` reachable (§8, JEG-1209).
- Current dashboard hook: `TradeValueSimplifiedSite.activate(document.getElementById('v2Simplified'))`.
  The module's internal Full dashboard link uses existing `#find-league`; the full-design owner retains that alias
  or coordinates its one link target. No shared navigation hunk is needed for this artifact.
- New canonical result adapter: use `TradeValueSimplifiedSite.mount(container, {getContext, hash})` once, then
  `handle.update(false)` after the shared result changes. `handle.destroy()` removes its route listener. This path
  consumes a canonical result without requiring a second store or compatibility globals for the old discovery page.
- `getContext()` returns `{status:'loading'|'error'|'ready', error?, league:{name,myTeam}|null,
  basis:{horizon:'ros',label,valueLabel?,marketLabel?}, missing:[{key,text}], ideas, readout?}`.
  Every missing reason withholds answers. Only non-live fixtures carry `{fixture:{kind:'historical'|'synthetic',label}}`.
- `ideas` is the existing authoritative recommendation output: `{recommendations,stretch,counts}` in its supplied
  order. Each record carries stable `id`, `opponentId/name`, give/receive named player records, authoritative `ourGain`,
  existing `band/likelihood` compatibility fields, `why`, labeled `sources`, `gains.market` or existing market basis gain,
  and optional `health`, `fitLabel`. The view never computes a gain, threshold, source average, fit or ranking.
  `basis.valueLabel`, `basis.marketLabel` and `rec.fitLabel` are passed through from the canonical owner. Internal
  compatibility bands are not rendered as acceptance predictions; package evidence states the subject and scope.
- For a detail, `readout` is the shared `TradeValueReadout` result for that exact package/context. The component calls
  shared `renderSide` for both teams in DDF, market and supporting projections, preserving missing-player/bench notes.
  Canonical JEG-1483 should provide its common record via this boundary. Do not reimplement D3–D7 here.
- The legacy `liveContext/readoutFor` bridge is for the existing dashboard/provider: it reads the completed search's
  `pricingRows`, workspace, normalized common context and shared readout. A running/pending search withholds old results.
  The new full-design controller should feed its canonical context/readout through `mount` rather than infer a new
  Market setting from the legacy bridge's chart-key list.
- No source or saved settings are changed on entry, Back, pagination or bench toggles. Repeated action and desktop
  1280/phone 390/320 checks are in `verify_private_review.py`; negative paths clear previous answers. The no-result
  check uses actual manager exclusions, not fabricated recommendation output.

## Explicit pending integration

This artifact uses real #1084 provider code, still unmerged at the time it was prepared. It implements none of
JEG-1483's new starter-only predicates, Market composition/coverage changes, tolerances or link-overwrite policy.
Those remain with the full-design/JEG-1483 owner. Its review landing page states that limit. Import the scoped module
into the intended shared private review destination; production release still needs all normal gates.
