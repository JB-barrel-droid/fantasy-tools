# Waiver-board artifact contract (`waiver-board` v0.1; local swaps v0.2)

Status: Maintained. Owner tickets: JEG-1415, JEG-1418 (JEG-1196). Last updated: 2026-11-03.

One computed board per league setting feeds the Waiver board view (JEG-1420)
and Bench Churn (JEG-1197). Builder: `pipelines/build_waiver_board.py`. Schema
and validator: `pipelines/lib/waiver_board.py`. Design: `docs/design/waiver-bench-churn-concept.md`.

## What it reads

| Input | Lane | From |
| -- | -- | -- |
| Weekly inputs | This week | a `weekly-inputs` 1.x artifact (`docs/weekly-inputs-contract.md`, producer `pipelines/build_weekly_inputs.py`). Refused unless the contract validator passes it. |
| DDF Value | Value | `pipelines/value_reference.py` at the setting (Adjusted view, `ddf_value`, the engine's twin) on the published `players.json` and chart fixture, read only; or a saved values snapshot of the same shape (`--values`), refused unless it is view `adj`, series `ddf_value`. Its content week is the week the reference priced (the served week of its prior pair, as the page's week view; without a week history, the newest week the weekly charts serve), never the build day's calendar week. Checked against get-values' own pipeline in the tests. |

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

## Optional local swaps (v0.2, JEG-1418)

Ordinary builds keep the exact v0.1 output, including its unavailable `swaps`
placeholder. Passing `--swap-request PATH` (or `swap_request=` to `build_board`)
opts that local artifact into v0.2.0. Site-build integration is not changed.
There is no default gain cutoff: the caller must supply an explicit policy.

The request is a JSON object with exactly these fields:

| Field | Contract |
| -- | -- |
| `setting` | Exactly the board's scoring, teams and superflex setting. |
| `roster_keys`, `wire_keys` | Unique resolved integer player keys, representable exactly in JavaScript. Names are resolved by the existing paste resolver before this boundary. The caller supplies its wire-selection policy. |
| `wire_overrides` | `{add: [keys], remove: [keys]}`. A key cannot appear in both. Own players are excluded from the resulting wire. Unknown wire keys are reported; an unknown roster key disables swaps with a reason. |
| `context` | Engine league context: `shape` (QB/RB/WR/TE/FLEX/SUPERFLEX/BENCH slots, optional K/DST), `expected` (the four positions' lo/hi bands, optionally the engine's starters/bench/expected fields), `weights` (the engine's per-position bench weights or overall fallback), and optional `rosterSize`. No weekly fields are accepted here. |
| `gain_policy` | `{minimum: finite_number, comparison: "gt" or "gte"}`. Both fields are required. This records the caller's chosen cutoff and boundary; no policy is selected by this implementation. |

The v0.2 `swaps` block has exactly `available`, `missing_reason`, `request`,
`rows` and `unresolved_wire_keys`. Each row is `{add: player_key, drop:
player_key_or_null, gain: number}`. The full request is retained so the artifact
is inspectable and replayable. The CLI records the exact request-file bytes in
`inputs.swap_request` with the file name and SHA-256.

`gain` is the arriving player's DDF Value minus the departing bench player's
DDF Value; an open roster slot has no drop and costs zero. Missing DDF Value
never becomes zero. A disabled values source disables the swap block with its
source reason. Other weekly fields never affect gain or selection.

Subtraction uses the input numbers' canonical decimal forms, and the explicit
gt/gte policy compares that decimal difference exactly against its minimum.
Thus 3.35 minus 3.25 is equal to 0.1: gt excludes it and gte includes it. No
epsilon or fixed rounding precision is added, and the input DDF Values are not
changed. The reported gain remains a JSON number. Function callers' unary
`acceptGain(gain)` callbacks remain supported; the adapter also supplies the
source add and drop values as optional second and third callback arguments.

`pipelines/waiver_board_swaps.cjs` invokes the same pure adapter as local JS
callers, `app/v2/waiver-board-swaps.js`, which calls `waivers.js` and finder
`rosterImpact`/depth rules. The adapter preserves Waivers' best-drop choice and
ordering, reevaluates after each accepted move, and uses each player at most
once. A proposed drop must be a priced bench player and cannot worsen a thin
position. It omits an unsafe move rather than ranking an alternative drop.
Both additions and priced drops must have an existing supported fantasy
position (QB, RB, WR or TE); missing or unsupported positions are not eligible.

The validator checks the block and replays that same JS implementation to
verify the rows, gain, identities, order, availability and depth protection.
No second Python roster-decision path is introduced. Node is required only
when building or validating the opt-in v0.2 block; missing Node refuses it.
The legacy v0.1 path requires no Node invocation.

```
python3 pipelines/build_waiver_board.py --weekly-inputs inputs-wk8.json \
    --values values.json --scoring half_ppr --teams 12 --superflex 0 \
    --built-at 2026-10-30T12:00:00Z --swap-request local-request.json \
    --out /tmp/local-waiver-board.json
python3 -m unittest tests.test_waiver_board_swaps tests.test_waiver_board_swaps_pipeline
```

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

0.x until the remaining sections and verdicts land. Default output stays 0.1.0;
explicit local swaps use 0.2.0. The Python validator accepts both minor versions.
A 0.1-only consumer needs explicit 0.2 support before reading populated local
swap artifacts. 1.0.0 freezes the shape for JEG-1197.
