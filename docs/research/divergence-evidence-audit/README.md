# Divergence evidence audit (JEG-1277, for JEG-952)

**Verdict: not sufficient.** JEG-952 (tune the divergence thresholds) needs
four dated weekly divergence reports. Committed history holds reports
labelled weeks 5, 6, 7 and 8, but only **three qualify (weeks 5, 6 and 7),
for every one of the seven sources**. The week 8 report was built while every
source was still served as week 7. No threshold is recommended, and none can
be from this evidence.

The per-week detail is generated, not written by hand:
[availability-matrix.md](availability-matrix.md) (table) and
[availability.json](availability.json) (the same facts, machine-readable).

## What counts as a qualifying week

A committed report (one version of `dist/modules/source-divergence.json` on
main) counts for a source only when all of these hold. The audit
(`tools/research/divergence-evidence-audit/audit.py`) checks each one.

1. It is a committed receipt: a git commit and report blob, schema
   `source-divergence-v1`, no recorded error.
2. Three dates are present and kept apart: the report date (`generated_at`),
   the build date (`fixture_built_at`) and the source's own content date from
   the fixture of that build. A fetch time is never used as the content date.
3. Counts are present and agree: every combo has a denominator `n` > 0 and an
   `outliers` count that matches `outlier_rate` (to the reporter's 3-place
   rounding), and the summary's warning list matches the sources' statuses.
4. **The served week equals the report week.** The report's `week` is the
   content week from `data/history/index.json`. The served week is the saved
   week the served inputs fingerprint-match, from the index of the same build.
   A report labelled week N that served week N-1 data is not evidence for
   week N (the JEG-1172 finding).
5. The served fingerprint and the source's scoring basis are recorded.

Repeated captures of one report week count once; the newest qualifying
capture represents the week. A week whose served data has the same
fingerprint as a counted week does not count again. Weeks count together only
when the source's combos, scoring-basis statement and the report thresholds
are identical.

Synthetic receipts run through the same rules and never count as real
evidence (`tests/fixtures/divergence-evidence-audit/synthetic-four-weeks.json`
is flagged `synthetic: true` and dated 2099).

## What the committed history shows

55 committed report versions, from `f29e6e29` (2026-10-11) to `e2c191c2`
(2026-10-27). Thresholds are the same in all 55 (warn above 45% outliers or
|bias| above 5 points). Each source has one combo set and one scoring-basis
statement across all of them. The reporter's metric has not changed since it
was added (`0f4ea87f`); its one later change (`1658a3d3`, JEG-610) only added
the `exclude` resolution display.

| Report week | Committed captures | Qualifying | Counted capture (report date / build date) |
| -- | -- | -- | -- |
| 5 | 20 | 20 | `b2faef5a` (2026-10-16 / 2026-10-12 22:11 UTC) |
| 6 | 28 | 10 (CBS: 1) | `07eaea9f` (2026-10-19 / 2026-10-19 15:51 UTC) |
| 7 | 6 | 3 | `74acb3c5` (2026-10-22 / 2026-10-22 16:15 UTC) |
| 8 | 1 | 0 | none: `e2c191c2` (2026-10-27 / 2026-10-26 15:42 UTC) served week 7 |

- **Week 8** served week 7 for all seven sources. FantasyPros' served
  fingerprint (`848f4664`) is week 7's, as JEG-1172 found.
- **Weeks 6 and 7:** the earlier captures of each week still served the week
  before (18 of 28 week-6 captures; CBS in 27 of 28, because the CBS week 6
  chart reached the build only on 2026-10-19; 3 of 6 week-7 captures).
- **Source dates of the counted captures:** USA Today and FantasyPros
  2026-10-06, 10-13, 10-20; CBS and FantasyCalc Week 5, 6, 7; ESPN 10-12,
  10-18, 10-21; CBS rest of season 10-12, 10-19, 10-22; Razzball 10-11,
  10-19, 10-22.

### The historical 48% and 52%

The CBS rest of season and Razzball rates quoted on JEG-460 and JEG-952 (48%
and 52%) are the first committed capture, `f29e6e29` (week 5, built
2026-10-11 01:05 UTC; full PPR 0.483 and 0.517). That capture was superseded
the next day by later week-5 builds. Week 5 counts once, through `b2faef5a`,
where both read 42.6% in full PPR. The 48%/52% figures are not fresh evidence
and are not counted on their own.

## Value impact

Each receipt carries, per source and scoring, copied from its report: `n`,
the outlier count and rate, bias, mean absolute deviation (points), the same
statistics by position, and the five largest deviations with the player, the
source's value and the consensus. The audit checks that content, not a flag
that it existed. It does **not** carry the value of every outlier player. So
JEG-952's "mostly low-value players" cannot be measured from the receipts
alone. It can be recomputed offline from the committed fixture of each counted
build (`a7283138`, `b4134b27`, `d54c7723`, listed per capture in
`availability.json` as `recomputable_from`). This audit did not do that.

## Gaps before JEG-952 can be worked

1. **A fourth qualifying week.** A committed report whose content week equals
   every source's served week, for week 8 or later. `dist/modules/source-divergence.json`
   on main is still the 2026-10-27 copy. JEG-1172 found the Week 8 FantasyPros
   article first reached the fixture at `e55755ca` (built 2026-10-28), but no
   report from that build is committed. Committing a regenerated report is the
   publish path's job (`make sync`), not this lane's.
2. **Value impact by player.** An offline recomputation from the committed
   fixtures of the counted builds, if JEG-952 needs the low-value claim
   measured rather than quoted.
3. **Which weeks are "fresh".** JEG-952 says "post-launch". Weeks 5 to 7 are
   pre-launch. This audit counts them; if only post-launch weeks count, none
   qualifies yet. That reading is for the JEG-952 owner, not decided here.
4. **CBS rest of season's scoring basis.** JEG-1171 found a scoring-basis
   difference from the ESPN leg plausible but unproven. It does not change the
   week count; it does affect how that source's rates should be read.

## How to run

```
python3 tools/research/divergence-evidence-audit/extract_receipts.py
python3 tools/research/divergence-evidence-audit/audit.py \
    --markdown docs/research/divergence-evidence-audit/availability-matrix.md \
    --json docs/research/divergence-evidence-audit/availability.json
python3 -m unittest -v tests.test_divergence_evidence
```

The extractor needs history back to 2026-10-10 on a shallow clone:
`git fetch --shallow-since=2026-10-05 origin main`. The audit and the tests
need nothing but the committed fixtures.

## Limits

- Only reports committed to main are inventoried. CI artifacts, deploy runs
  and the live site were not read, and whether each committed copy matches
  what was deployed is not checked.
- The served weeks and source dates are matched to each report by build stamp
  (and, for the index, content week). That this is the copy the reporter read
  is inferred from the matching stamps, not proven.
- No reporter, config, resolutions, data or Makefile change. The new test is
  not wired into a Makefile list; that wiring is the CI coordinator's.

## Log

The session log is
[docs/claude-log/2026-10-29-jeg-1277-divergence-evidence-audit.md](../../claude-log/2026-10-29-jeg-1277-divergence-evidence-audit.md).
