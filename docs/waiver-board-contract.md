# Waiver-board artifact contract (`waiver-board` v0.1)

Status: Maintained. Owner ticket: JEG-1415 (slice 1 of JEG-1196). Last updated: 2026-10-31.

One computed board per league setting feeds the Waiver board view (JEG-1420)
and Bench Churn (JEG-1197). Builder: `pipelines/build_waiver_board.py`. Schema
and validator: `pipelines/lib/waiver_board.py`. Design: `docs/design/waiver-bench-churn-concept.md`.

## What it reads

| Input | Lane | From |
| -- | -- | -- |
| Weekly inputs | This week | a `weekly-inputs` 1.x artifact (`docs/weekly-inputs-contract.md`, producer `pipelines/build_weekly_inputs.py`). Refused unless the contract validator passes it. |
| DDF Value | Value | `pipelines/value_reference.py` at the setting (Adjusted view, `ddf_value`, the engine's twin) on the published `players.json` and chart fixture, read only; or a saved values snapshot of the same shape (`--values`). Its content week is the week the reference priced (the served week of its prior pair, as the page's week view; without a week history, the newest week the weekly charts serve), never the build day's calendar week. Checked against get-values' own pipeline in the tests. |

The board prices nobody. Every DDF Value and prior-week DDF Value is the
reference's own number. Change is DDF Value minus the reference's prior-week
DDF Value at the same setting (last week's inputs through today's math, the
same pair the site's risers and fallers use).

## Two lanes, never blended

Jeremy, 2026-10-29: "do not blend weekly data with ROS data, ever".

| Lane | Row fields | Fed by |
| -- | -- | -- |
| `value` | `ddf_value`, `prior_ddf_value`, `change` | sources `values`, `values_prior` |
| `this_week` | `points`, `status`, `injury_status`, `practice_participation`, `bye_week`, `on_bye` | sources `points` (the leg named in `points_leg`), `status`, `bye` |

No field of one lane is computed from the other, and the validator rejects a
field in the wrong lane or a week-lane source feeding a value field. Rows are
sorted by DDF Value (highest first, missing last), then `player_key`. Nothing in
v0.1 sorts or decides on the This week lane.

## Sources and when they are disabled

Every source carries `lane`, `source`, `availability`, `freshness`, `label`,
`content_season`, `content_week`, `content_vintage`, `enabled`,
`disabled_reason` and `feeds`. A disabled source makes every field it feeds
null on every row, with the source's reason.

| Source | Enabled when |
| -- | -- |
| `values` | the DDF Value input is this season, not for a later week than the board, and current or one week behind (a rest-of-season price a week old is still a fair price). Stale (2 or more weeks) or another season disables it; another season is labelled `previous-season`. |
| `values_prior` | `values` is enabled and the reference has the week before (needs the week history `make sync` writes). Its `content_week` is that prior week; its freshness and label are those of the DDF Value it is paired with, since the pair is last week's inputs through today's math. |
| `points` | the named expert leg has data, is this season, is `current` (a one-week-behind projection is last week's game, not this week's), and carries the setting's scoring. |
| `status` | the Sleeper status leg has data, is this season and is `current`. |
| `bye` | the bye leg has data and is this season (a season table does not age within the season). |
| `status`, `bye` missing from the file | the weekly contract allows a file without them; the source is unavailable and disabled, "the status leg is not in the weekly inputs". |
| other weekly legs (`vegas`, `experts.ecr_weekly`, ...) | listed for the source strip; v0.1 feeds nothing from them. |
| `rostered_pct`, `kickoff` | not in weekly-inputs 1.0.0 yet: always unavailable until JEG-1416. |

The validator re-derives these rules rather than trusting `enabled`: an enabled
source must be this season's and not for a later week; points and status must be
`current` and for the board week; DDF Value current or one week behind; the prior
the week before DDF Value's week and only with DDF Value on; nothing but these
five sources may be enabled. Freshness is null exactly when a source is
unavailable, and a value source's freshness must be what its weeks give (the
weekly contract's rule; the prior pair takes DDF Value's). A source is labelled
unavailable exactly when it is unavailable, previous-season only for an earlier
season, and stale or previous-season content is never labelled `published`. A
values snapshot may carry only `published`, `modeled` or `stale`; the board
derives `unavailable` and `previous-season` itself. Feeds must be the source's
own fields.

## Rows

`players`: every resolved weekly-input player and every player the DDF Value
input prices. A field is a value with no reason or `null` with
`missing_reason[field]`, never both; 0.0 is a real value. A kicker or defense
has no DDF Value ("DDF Value does not price kickers or defenses"); a priced
player missing from the weekly inputs has every This week field "not in the
weekly inputs". `unresolved`: weekly rows with no `player_key`, with the
producer's reason, never joined to a priced player. A player the reference priced
last week but not this week, and who is not in the weekly inputs, is not on the
board (the board lists this week's players).

Each row is checked for consistency: `change` is exactly `ddf_value - prior_ddf_value`
and is missing whenever either side is; `on_bye` is a boolean present exactly when
`bye_week` is, and true exactly when `bye_week` is the board week; a field fed by a
disabled source carries that source's own reason; reasons are non-empty strings.

`sections` and `swaps` are `{available: false, missing_reason}` in v0.1
(JEG-1417, JEG-1418).

## Running it

```
python3 pipelines/build_waiver_board.py --weekly-inputs inputs-wk8.json \
    --scoring half_ppr --teams 12 --superflex 0 \
    --built-at 2026-10-30T12:00:00Z --from-reference --out /tmp/waiver-board.json
python3 pipelines/lib/waiver_board.py /tmp/waiver-board.json
python3 -m unittest tests.test_build_waiver_board
```

Offline: no network, no Supabase, no credentials, no wall clock (`--built-at`
is the clock; with `--from-reference` it also sets the reference's day).
Same inputs give the same bytes. A refused run exits 2 and writes nothing.
`inputs.values.sha256` covers the exact bytes `--values-out` writes.

## Versions

0.x until sections, verdicts and swaps land; a reader accepts 0.1.x only.
1.0.0 freezes the shape for JEG-1197.
