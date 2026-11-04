# Versus Vegas local preview (JEG-1481, part of JEG-1195)

Build from a stored `weekly-inputs` v1 JSON artifact:

```sh
python3 pipelines/build_versus_vegas.py tests/fixtures/weekly_inputs/valid/unavailable.json --out /tmp/versus-vegas/index.html
python3 -m http.server 8000 --directory /tmp/versus-vegas
```

Open `http://localhost:8000`. This example uses synthetic, unavailable inputs;
the page keeps every player visible and explains missing coverage. The output
is self-contained and makes no network requests. Nothing is wired to `make sync`,
the dashboard shell, `dist`, runtime writers or publication.

The page consumes the shared Fieldnotes foundation from `app/v2/v2.css` at
render time, including its single Fraunces declaration and existing tokens/native
components. The existing font and license are embedded for an entirely offline
export. Shared shell/token/font files are read-only. The header's final navigation
labels are context for design review; no production routes are connected.

Two isolated design alternatives use the same payload: `--layout compact`
(source-health band, default) and `--layout analysis` (desktop source side panel).
Both use compact ruled rows with a readable stacked layout on phones. Native
identity/provenance disclosures and all source values remain available.

```sh
python3 app/versus-vegas/build_review.py --out /tmp/versus-vegas-review
# Or preserve an actual stored artifact's values and provenance:
python3 app/versus-vegas/build_review.py --input /path/to/weekly-inputs.json --out /tmp/versus-vegas-review
```

The default review export is explicitly labeled synthetic and uses the existing
frozen comparison fixture. It does not claim active ECR/PropLine data. Canonical
reference inspection and the current shell/nav decision are in `DESIGN.md`.

The adapter uses the existing weekly-input validator, then selects only
`experts.ecr_weekly` (`fantasypros_ecr` from the producer, or `fantasypros`
from the shared contract fixtures) and `vegas` (`propline`). ESPN and other
sources cannot fill either side. Missing values remain null with the producer's
reason, or an explicit absent-leg / absent-scoring reason. Raw source values,
content vintage, freshness, provenance, identity and artifact SHA-256 remain
inspectable. Each player's expandable identity detail shows `player_key`,
`resolved_by`, and `source_ids` as supplied by the producer; absent identity
provenance is explicitly unavailable. Freshness is the shared contract's content-week classification;
it is not a claim that a saved artifact is current today.

Difference is descriptive `Vegas − ECR` fantasy points, only when both cells
are present, complete, current within the artifact week, and canonically
identified. Partial and td-filled rows remain unflagged in every scoring. Ranks
are displayed as ranks; no rank-to-points conversion or inferred positional
rank is made. Both-values coverage and comparable-points coverage are separate.
Verified plays remain empty pending the shared compute/play gate (S4). This
page does not implement pricing or a play recommendation threshold.

Scoring, position, coverage and sort persist in URL query parameters; reload
and browser back restore them. Unknown parameters are preserved. Defaults show
all players, including missing, partial and unresolved rows, in Half PPR.

```sh
python3 -m unittest tests.test_versus_vegas
RENDER_TESTS_REQUIRED=1 python3 -m unittest tests.test_versus_vegas_render
```

The adapter suite also runs the real offline producer CLI on its committed
fixtures, then feeds its output directly to the preview CLI without relabeling
or mocking. It checks unavailable coverage, unresolved rows and identity fields.
The browser test uses only a loopback HTTP server and the repo's hermetic
Playwright setup. Tests create synthetic ECR/PropLine rows from the existing
committed shared-input fixture; no production data or fixtures are modified.
