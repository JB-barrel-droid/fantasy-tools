# Weekly-input contract (`weekly-inputs` v1)

The shape of the one weekly-input artifact, `data/weekly/inputs-wk{N}.json`,
that the weekly producer (JEG-1228, S2 onward) writes and Versus Vegas and
later weekly consumers read. Built for JEG-1227 (S1 of JEG-1195) from the
readiness packet in PR #1083 (`docs/research/jeg-1195-weekly-inputs-readiness.md`,
section 5). The validator, `pipelines/lib/weekly_inputs_contract.py`, is the
one definition; this page explains it.

Status: Maintained, owner JEG-1227, verified 2026-10-29. Local only: nothing
here is applied to Supabase, and no producer, feed, schedule or page reads it yet.

## Check a file

```
python3 pipelines/lib/weekly_inputs_contract.py data/weekly/inputs-wk8.json
python3 pipelines/lib/weekly_inputs_contract.py --json FILE [FILE ...]
python3 -m unittest tests.test_weekly_inputs_contract
```

Stdlib plus `pipelines/lib/timestamps.py`, offline, no credentials. Exit 1 when any file has an error;
warnings alone exit 0. From Python:

```python
from lib.weekly_inputs_contract import validate, validate_file, is_valid
issues = validate(doc)        # list of Issue(code, path, message, severity)
assert is_valid(issues)       # no errors (warnings allowed)
```

## Rules

- **Weekly only.** Jeremy, 2026-10-29: "do not blend weekly data with ROS
  data, ever". The artifact and every leg say `horizon: "week"`. A leg id,
  source or field name that names rest-of-season data (`ros`,
  `rest_of_season` as a word) is rejected. Nothing in the artifact is filled,
  shaded or scaled from ROS data.
- **Numeric `player_key`** from `pipelines/lib/player_key_index.py`. A row
  that does not resolve keeps `player_key: null` and says why in
  `unresolved_reason`; it is kept, never guessed and never dropped. No two rows
  share a key.
- **Missing is null plus a reason, never zero.** Each null value has an entry
  in the cell's `missing_reason` (rows of an unavailable leg are covered by the
  leg's own `missing_reason`). A real zero is a number with no reason. A value
  that carries a reason is a fill and is rejected (`missing.zero_filled`).
- **Partial rows stay visible.** A row with some nulls is `provenance:
  "partial"`; a row with every value null is `"missing"`. Both stay in the file.
- **Availability and freshness are separate fields.** This resolves the #1083
  review point (an absent leg could not be encoded consistently when both
  lived in one enum):
  - `availability`: `complete` / `partial` / `unavailable`: does the leg have
    data. For points and rank legs it must agree with the rows (a complete leg
    has no nulls; a partial leg has at least one).
  - `freshness`: `current` / `one_week_behind` / `stale` / `unknown`, the
    vocabulary and rule of `pipelines/check_reference_freshness.py` (0 weeks
    behind the artifact's content week is current, 1 is one week behind, 2 or
    more is stale, no stamped week is unknown). Content vintage, never pull time
    (`docs/pipeline-rules.md` section 5). `null` exactly when the leg is
    unavailable.
  - Provenance backs the claim. A leg with data whose freshness is `current`,
    `one_week_behind` or `stale`, or whose label is `published`, has non-null
    `content_season`, `content_week`, `content_vintage` and `captured_at`. When
    the source stamps none of these, the leg is `unknown` and not `published`
    (`valid/unknown_no_provenance.json`).
  - `label`: `published` / `previous-season` / `modeled` / `stale` /
    `unavailable` (the standing labels). `unavailable` exactly when the leg is
    unavailable; `previous-season` exactly when the leg's content season is
    before the artifact's (and such a leg is stale); stale content is never
    labelled `published`. A 2026 leg in a 2027 artifact must say
    previous-season, so 2026 data is never shown as 2027.
- **Units are fixed per leg and never converted.** `fantasy_points` (finite
  numbers), `rank` (whole numbers from 1), `status` (`status`, `injury_status`,
  `injury_body_part`, `practice_participation`, `depth_chart_position` as
  strings, `injury_start_date` as an ISO date, `depth_chart_order` a whole
  number from 1; the names of the stored Sleeper status history), `bye_week` (1 to 18). Nothing here turns a rank into points
  or compares two legs.
- **Scoring formats** are `standard`, `half_ppr`, `ppr` (the keys of
  `pipelines/lib/scoring.py`). A points or rank leg lists the formats it
  carries in `scoring`, and every row carries exactly those keys, null where
  missing.
- **Order.** Rows are sorted by `player_key` ascending, then unresolved rows by
  name, so repeat builds are byte-stable when written with sorted keys.

## Shape

Top level: `schema` (`"weekly-inputs"`), `schema_version` (semver, `"1.0.0"`),
`horizon` (`"week"`), `season`, `content_week` (the Tuesday-flip week of
`pipelines/nfl_week.py`), `built_at` (UTC timestamp), `producer`, `legs`,
`players`, and an optional `input_report` (the producer's read and drop counts,
free-form object).

`legs` declares each leg once, keyed by leg id: `vegas`, `status`, `bye`, or
`experts.<name>` for any weekly expert source (`experts.espn_weekly`,
`experts.ecr_weekly`, later ones). Each leg has `kind` (vegas / expert /
status / bye, matching the id), `source`, `horizon`, `units`, `scoring`,
`content_season`, `content_week`, optional `game_week` (Thursday flip, slate
fields only), `content_vintage` (ISO date), `captured_at` (UTC timestamp),
`availability`, `freshness`, `label`, `missing_reason` (required when
unavailable), an optional `note` and optional `inputs` (the local files the
leg was built from, each `{name, sha256}`). A leg with no producer yet is declared
unavailable with nulls, not left out:

```json
{
  "availability": "unavailable",
  "captured_at": null,
  "content_season": null,
  "content_vintage": null,
  "content_week": null,
  "freshness": null,
  "horizon": "week",
  "kind": "vegas",
  "label": "unavailable",
  "missing_reason": "PropLine feed on hold until the key exists (S3)",
  "scoring": [
    "standard",
    "half_ppr",
    "ppr"
  ],
  "source": "propline",
  "units": "fantasy_points"
}
```

Each row has `player_key`, `name`, `position` (QB / RB / WR / TE / K / DST),
`team` (or null), optional `unresolved_reason`, optional `resolved_by` (which
identity rule matched) and `source_ids` (the source ids seen), and `legs`: one cell per
declared leg (none omitted), each with `provenance` (`complete`, `partial`,
`missing`, or `td-filled` on the vegas leg only), `values` and, for nulls,
`missing_reason`:

```json
{
  "legs": {
    "bye": {
      "provenance": "complete",
      "values": {
        "bye_week": 7
      }
    },
    "experts.ecr_weekly": {
      "provenance": "missing",
      "values": {
        "half_ppr": null
      }
    },
    "experts.espn_weekly": {
      "provenance": "complete",
      "values": {
        "half_ppr": 12.3,
        "ppr": 14.8,
        "standard": 9.8
      }
    },
    "status": {
      "provenance": "complete",
      "values": {
        "depth_chart_order": 2,
        "depth_chart_position": "WR",
        "injury_body_part": "Hamstring",
        "injury_start_date": "2026-10-26",
        "injury_status": "Questionable",
        "practice_participation": "Limited",
        "status": "Active"
      }
    },
    "vegas": {
      "provenance": "missing",
      "values": {
        "half_ppr": null,
        "ppr": null,
        "standard": null
      }
    }
  },
  "name": "Fixture Wide Receiver",
  "player_key": 9000103,
  "position": "WR",
  "resolved_by": "espn_player_id",
  "source_ids": {
    "espn_player_id": 103,
    "sleeper_id": "S9000103"
  },
  "team": "CCC"
}
```

Full examples: `tests/fixtures/weekly_inputs/valid/complete.json` (every leg
current), `valid/partial.json`, `valid/stale.json`, `valid/unknown.json`,
`valid/unknown_no_provenance.json`,
`valid/unavailable.json`, `valid/rank_leg.json`, `valid/zero_value.json`,
`valid/unresolved_player.json`, `valid/previous_season.json`. The players and
numbers in them are synthetic.

Out of scope here: which expert legs a comparison reads (a named, versioned
setting owned by the compute slice, S4), any comparison or rank-to-points math,
and the waiver board (JEG-1196 takes no weekly data for now).

## Versions

A reader accepts any `1.x.y`; another major, or a version that is not
MAJOR.MINOR.PATCH, is refused. Adding an optional field is a minor bump. A field
the reader does not know is an error when the document's minor is one the
reader knows (a producer typo) and a warning when the document is newer, so a
1.0 reader keeps reading 1.1 files. Newer minors never relax the rules above. A
new weekly expert source is a new `experts.<name>` leg and needs no bump.

## Validation codes

Every issue has a `code`, a JSONPath-style `path` (for example
`$.players[2].legs.vegas.values.ppr`), a message and a severity.
`tests/test_weekly_inputs_contract.py` pins this table to the validator and
exercises every code.

| Code | Meaning |
|---|---|
| `json.invalid` | The file is not parseable JSON. |
| `type.document` | The document is not a JSON object. |
| `field.missing` | A required field is absent. |
| `field.unknown` | A field this reader does not know (error at a known minor version, warning at a newer one). |
| `field.type` | A field has the wrong JSON type. |
| `schema.name` | `schema` is not "weekly-inputs". |
| `version.malformed` | `schema_version` is not MAJOR.MINOR.PATCH. |
| `version.unsupported_major` | `schema_version` major is not 1. |
| `season.range` | A season is outside the supported range. |
| `season.future` | A leg's content season is later than the artifact's season. |
| `week.range` | A week is outside 1..18. |
| `week.future` | A leg's content week is later than the artifact's content week. |
| `timestamp.format` | A date or timestamp is not ISO 8601 (timestamps need a UTC offset). |
| `ros.horizon` | A horizon other than "week" (rest-of-season data is never allowed). |
| `ros.leg` | A leg id or source names rest-of-season data. |
| `ros.field` | A field name anywhere in the document names rest-of-season data. |
| `leg.id` | A leg id is not vegas, status, bye or experts.<lower_snake_name>. |
| `leg.none` | The document declares no legs. |
| `leg.kind_mismatch` | A leg's kind does not match its id. |
| `leg.no_reason` | An unavailable leg has no missing_reason. |
| `leg.provenance_unknown` | A leg with data that claims current, one_week_behind or stale freshness, or a published label, has a null content_season, content_week, content_vintage or captured_at. |
| `leg.unavailable_has_values` | A row carries a value for a leg declared unavailable. |
| `availability.value` | availability is not complete, partial or unavailable. |
| `availability.inconsistent` | A points or rank leg is complete but a row has a null, or partial with no null in any row. |
| `freshness.value` | freshness is not current, one_week_behind, stale, unknown or null. |
| `freshness.inconsistent` | freshness disagrees with the leg's content week, or is set on an unavailable leg. |
| `label.value` | label is not published, previous-season, modeled, stale or unavailable. |
| `label.inconsistent` | label disagrees with availability, freshness or content season. |
| `units.incompatible` | A leg's units are not allowed for its kind. |
| `scoring.unknown` | A scoring format other than standard, half_ppr or ppr. |
| `scoring.mismatch` | A leg's scoring list does not fit its units, or a row's values do not match the leg's scoring list. |
| `player.key_type` | player_key is not a positive integer or null. |
| `player.duplicate_key` | Two rows share a player_key. |
| `player.unresolved_no_reason` | A row with player_key null has no unresolved_reason. |
| `player.position` | position is not QB, RB, WR, TE, K or DST. |
| `order.players` | Rows are not ordered by player_key, then unresolved rows by name. |
| `row.undeclared_leg` | A row carries a leg the document does not declare. |
| `row.leg_missing` | A row omits a declared leg (write it with null values and reasons instead). |
| `value.type` | A value has the wrong type for the leg's units (points must be finite numbers). |
| `value.range` | A rank, bye week or depth order is not a positive whole number in range. |
| `missing.no_reason` | A null value has no missing_reason entry. |
| `missing.zero_filled` | A value carries a missing_reason but is not null (a zero or other fill). |
| `missing.reason_unused` | A missing_reason names a key the row does not have. |
| `provenance.value` | provenance is not complete, td-filled, partial or missing. |
| `provenance.inconsistent` | provenance disagrees with which values are null. |

## Fixtures

`tests/fixtures/weekly_inputs/build_fixtures.py` writes every case as a small
change to one base document, plus `expected.json` (the error and warning codes
each case must produce, in order). The test rebuilds them and requires the
committed files to match byte for byte, so add a case in the script, run it and
commit both.
