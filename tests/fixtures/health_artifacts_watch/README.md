# Health-artifact watch fixtures (JEG-1239)

Anonymous, minimal copies of the two served health artifacts, shaped like
`dist/modules/pipeline-checkpoints.json` and
`dist/modules/source-import-health.json` (timestamp fields plus empty
`sources`). No source names, values or league data.

- `published/`: what one health-artifacts run published (2026-10-28 18:50 UTC).
- `served_previous/`: the previous deploy still being served when the watch
  judged at 19:17 UTC, 25+ minutes later. Valid JSON with ages 386 and 109
  minutes, the ages reported on JEG-1239: both under the 720-minute content
  limit, both older than this run's publication.
