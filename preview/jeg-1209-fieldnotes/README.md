# JEG-1209 Fieldnotes revision 3 preview (private review)

Find a trade (whole league) in the Fieldnotes design language, running the real sibling components unchanged. Review brief: `docs/design/jeg-1209-fieldnotes/continuation/brief.md`. Nothing here is linked from the app or deployed.

- `index.html` is built and self-contained (no network). Open it directly, or serve the repo root with `python3 -m http.server 8767 --bind 127.0.0.1` and open `/preview/jeg-1209-fieldnotes/index.html`. Routes: `#finder`, `#flow`, `#handoffs`; the revision-2 routes are reachable from the top nav.
- `src/` holds the continuation's own markup, styles and script. `vendor/` holds pinned copies of the sibling components; `vendor/MANIFEST.json` records each one's PR, commit and git blob.
- `python3 preview/jeg-1209-fieldnotes/build.py` rebuilds `index.html` from the unchanged revision-2 prototype (`docs/design/jeg-1209-fieldnotes/prototype.html`, sha256 checked), the vendor copies and `src/`. `--check` fails on any drift; `--vendor` refreshes the copies from their pinned commits.
- `python3 preview/jeg-1209-fieldnotes/checks.py --shots DIR` runs the browser checks (needs Playwright with Chromium) and writes screenshots named `<commit>-<route>-<width>.png` plus `shots.json`. CI runs it in `.github/workflows/jeg1209-preview.yml` and uploads the `jeg1209-fieldnotes-r3-shots` artifact.
