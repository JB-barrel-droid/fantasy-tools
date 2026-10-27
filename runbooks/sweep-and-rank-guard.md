# The 12-combo sweep, the rank guard and the value check

Required before any change to value numbers (the repo CLAUDE.md requires the sweep before changing the trade-value chart). All three run against the built `dist/`, so build first.

## Build

```
export PATH=$HOME/code/fantasy-tools/.venv/bin:$PATH
make sync
```

Expected last line: `Dashboard artifacts synced to app/trade-value-chart and dist (build tv-...)`.

## 1. Rank guard (published charts keep their native order, JEG-482)

```
python3 pipelines/check_rank_guard.py --out /tmp/rank.json
```

Expected, exit 0: `rank guard: pass -- 12 chart x combo checks, 0 failed, 0 inversions -> /tmp/rank.json`.

## 2. Engine sweep (3 scorings x 4 league sizes, plus one superflex setting)

```
python3 tools/engine_dump.py --out /tmp/engine-values.json
python3 -c "import json;d=json.load(open('/tmp/engine-values.json'));print(len(d['settings']), all(s['fixedPieIndexed'] and s['indexedOrderOk'] for s in d['settings']))"
```

Expected: `wrote 13 settings -> /tmp/engine-values.json` (about 7 seconds; headless browser, needs Playwright), then `13 True`. Also read `fixedPieIndexed` in `TradeValueCurveDiagnostics` for each combo (`sourceScaleAgreement` was retired with the fit; `tests/test_source_scale_agreement_retired.py`). One setting only: `--setting ppr:12:1` (scoring:teams:superflex).

**Number-changing work:** run the sweep on `origin/main` and on your branch and diff the two JSON files at full precision. Quote the before and after for the players that move. Identical output means no number changed.

## 3. Engine against the Python reference

```
python3 pipelines/value_check.py compare --rerun-engine --strict --report /tmp/value-check.json
```

Run `make sync` first (or add `--sync`): the check reads the built `dist/`, and since JEG-1060 it exits non-zero with `dist is stale (<file> differs from <source>): run make sync first` instead of diffing an old committed engine against the current reference.

Expected: `Verdict: **agree**` and a per-source table with 0 mismatches (the count moves with the fixture). `--strict` exits 1 on any disagreement. Second-session run 2026-10-15 at e71e8262: `agree`, 715,584 values across seven sources (usatoday, fantasycalc, fantasypros, cbs, espn, cbsros, razzball), exit 0. The earlier known red (`GAP-VALUECHECK-REFERENCE-AHEAD`, JEG-560) is cleared. `--engine-json` takes the check's own dump, not the `engine_dump.py` file above (passing that one fails with an AttributeError).

## If a check is red

A failure means the code or data is wrong. Do not change the tolerance or the assertion to clear it. Every regression guard must be negative-tested: simulate the broken state and confirm the guard fails.
