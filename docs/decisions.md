# Decisions Log

This file is the durable record of time-boxed decisions the project queues
for the human reviewer. The mechanism exists because not every parked item
deserves a synchronous tap — but every parked item must have an explicit
deadline, an explicit default-on-silence, and an explicit outcome once the
queue closes.

This log is **not** a backlog and **not** a planning doc. It is the queue
itself. Each entry is one open or recently-closed decision.

## Queue Rules (JEG-93)

1. **Default deadline is 7 days** from the date the entry is added. The
   `deadline` field carries the exact date; the 7-day default is a floor,
   not a ceiling — a longer deadline is allowed when the reviewer asks
   for one, but never silently.
2. **Silence by the deadline = proceed with the recommendation and record
   the outcome as `proceeded`.** No further tap required.
3. **A veto any time before the deadline stops the decision.** The
   outcome is `vetoed`, the `outcome_date` is set to the day of the veto,
   and a short note goes in the `Outcome Note` block. No replacement
   recommendation is recorded here — that belongs in a new entry.
4. **A modification before the deadline replaces the recommendation but
   keeps the entry open.** The outcome is `modified`, the new
   recommendation is appended under `Outcome Note`, and the deadline is
   either preserved (the reviewer's call) or extended with a new
   `deadline` line. A `modified` entry is still in the queue until a
   subsequent `proceeded` or `vetoed` closes it.
5. **Methodology, copy, and publish decisions are EXCLUDED from the
   silence-default.** They always need the explicit tap. Entries of
   this kind carry `silence-default: explicit-tap` and the queue rule
   that closes them is the human reviewer tap, not the clock.

The 7-day default is a calendar default. The reviewer may also force
`explicit-tap` on any entry by setting `silence-default: explicit-tap`
in the front matter — the queue treats that as "even if the clock
runs out, do not auto-execute."

## Entry Format

Each entry is a second-level heading `## <id>: <title>` followed by
a front-matter block, four required content sections, and an outcome
block.

Required front-matter keys (every key must be present, in any order):

| Key | Format | Notes |
| --- | --- | --- |
| `id` | slug like `jeg-93-001` or `draft-2026-10-02-usatoday-drift` | Stable. Used by the validator. |
| `created` | `YYYY-MM-DD` | Day the entry was added to the queue. |
| `deadline` | `YYYY-MM-DD` | Day the silence-default expires. Default 7 days after `created`. |
| `category` | free text, lowercase-hyphen | e.g. `native-drift`, `leg-promotion`, `methodology`, `copy`, `publish`. |
| `silence-default` | `proceed` or `explicit-tap` | Methodology / copy / publish entries must use `explicit-tap`. |
| `outcome` | `pending` / `proceeded` / `vetoed` / `modified` | `pending` while the queue is open; closed once an outcome is recorded. |
| `outcome_date` | `YYYY-MM-DD` or empty | Empty while `outcome: pending`. |
| `recommendation` | one short line | The single exercised recommendation the silence-default would execute. |

Required content sections:

- `### Context` — what parked the item; the surrounding state.
- `### Problem` — the question the decision answers.
- `### Options` — bulleted or numbered list of the realistic choices.
- `### Recommendation` — the one option above, expanded, with the
  rationale in plain language.
- `### Outcome Note` — empty while `outcome: pending`. When the queue
  closes, the outcome is recorded here (the `outcome` field alone is
  not enough — the note carries the date and the short justification).

Drafts that have not yet been queued live under `docs/decisions/drafts/`
and follow the same shape, but their `outcome` is `pending` and their
recommendation line starts with `DRAFT:` so the validator and any
reader can tell drafts apart from queued entries.

---

<!-- New entries go below this line. The validator parses the file from
top to bottom; do not insert narrative between entries. -->