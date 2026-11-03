# Fieldnotes continuation handoff (JEG-1209)

Existing visual direction and runnable source for Claude to continue; not a competing redesign. Status: historical revision-2 prototype, sanitized for project access on 2026-10-29. Current acceptance decisions supersede the frozen example behavior.

## Start here

1. Read [acceptance-amendment.md](acceptance-amendment.md) for current decisions and component ownership.
2. Read [recommendation.md](recommendation.md) for the visual system, flows and migration rationale.
3. Open [prototype.html](prototype.html). It is self-contained, editable HTML/CSS/JS with embedded historical data and the existing pure rule copies. No install, build, network request or live tool connection is required. The embedded Fraunces font is covered by [FONT-LICENSE.txt](FONT-LICENSE.txt).

If local-file restrictions apply, serve this directory with `python3 -m http.server 8766 --bind 127.0.0.1`, then open `http://127.0.0.1:8766/prototype.html#rosters`. Do not publish it as a site. Review at 1280 × 900 and 390 × 844; 320 and 768px were also checked. Other routes: `#home`, `#values`, `#finder`, `#chatbot`, `#guides`, `#paste`, `#compare`, `#targets`, `#settings`.

For the finder flow: Explore rosters → switch opponent/sort players → Explore trades involving a player → adjust Columns/Filters → Review both teams. Trade preferences demonstrates package/backup controls but deliberately marks results stale rather than rerunning search.

## What is real and what is illustrative

Numeric rows come from the historical Week 7 engine snapshot, captured 2026-10-28 with content clock 2026-10-25 and build tag tv-20261027-0014-1bdef712. The source checkout was 3919f998edf45204cf4edccf3425096054213a60. Fixture rosters are synthetic: four teams, 51 entries, with anonymous labels. These are not current data or a real user’s league. Source-field values and frozen rankings were not changed during sanitization.

Working interactions include roster switching, sorting, column visibility/order, opponent and player-focus filtering, inline details, keyboard controls and supported state encoding. Finder preferences are in-memory and reset on reload. There is no production workspace migration here. Package/backup controls do not recompute candidates. Results show five of 30 stored opportunities. No rejection diagnostics or JSN investigation result is invented.

The prototype uses the old Natural-fit predicate and rank, not approved 1A/2B/3A behavior. It has a fixed synthetic own team rather than the newly required two saved-team selectors. Shared preference persistence 5A is not implemented. The project-specific MCP endpoint has been replaced by a placeholder; Copy link encodes synthetic context but cannot connect tools or establish live calculation parity. Live deployment parity was not verified. ESPN fixture provenance is unresolved; the guide is not evidence of a successful real page copy.

## Scope and review

Only design-source/docs are supplied. No production code, fixture, math, deployment or site output is changed. Preserve this baseline and continue on a separate Claude branch; do not merge/publish as part of taking over. Current ticket: https://linear.app/jegabee/issue/JEG-1209

[handoff-verification.md](handoff-verification.md) records the local sanitation and smoke checks. Original review artifacts remain preserved separately; no private download link or account access is needed for this handoff.
