# OpenRouter lane result — JEG-394

_Model: z-ai/glm-5.3-flash. Review-only unless the brief says otherwise. Roman integrates; OpenRouter results never merge/push/deploy._

---

# Review note first (three plan gaps worth flagging before Roman integrates)

1. **Manifest section — "query the CURRENT run" is under-specified.** "Current" must mean `is_current=true AND season=<bundle season> AND week=<bundle week>`. If you only filter `is_current=true`, a season-boundary run (2025 final week still current when 2026 week 1 loads) will NOOP-match on hash collision or block a legitimate new season. Fix: filter on all three, as implemented below.
2. **Idempotency section — the `is_current` flag has a race.** Between the read of the current run and the promote patch, another loader process can promote. The NOOP check is advisory, not a lock; the manifest + hash is the real idempotency key. Acceptable for a single-CI-writer model, but document it — don't claim "idempotent" under concurrency.
3. **Regression sketch, "renamed copy → NOOP":** this is only true if the file *bytes* are identical. If the engine re-serializes (reordered keys, new `built_at`), the hash differs by design and a new run is correct. The test must assert on byte-identical copies (`cp`, not re-dump).

---

# Revised file

```python
#!/usr/bin/env python3
"""Load the canonical weekly signals bundle into the Supabase weekly dashboard tables.

Determinism guarantees (JEG-394):
- Bundle selection: explicit path (CLI/env) preferred; mtime fallback is
  local-only and refused in CI. Bundle meta (season/week/built_at) validated
  fail-closed; optional EXPECTED_WEEK cross-check.
- Dedupe: explicit FULL (non-null vegas_leg) / STUB classification. One FULL
  row per normalized player_key; two FULL rows or an unrecognized duplicate
  shape blocks the run. No heuristic scoring.
- Idempotency: keyed on (season, week, bundle_sha256) of the current run.
  Older season/week or older built_at blocked unless --allow-rollback.
"""
import argparse
import glob
import hashlib
import json
import os
import sys

SKILL_BIN = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
if os.path.isdir(SKILL_BIN):
    sys.path.insert(0, SKILL_BIN)
sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
import sbclient

BUNDLE_GLOB = os.path.expanduser(
    "~/workspace/goals/football-signal-database-and-app/hidden_files/"
    "weekly_dashboard_refresh_*/staged_bundle_*.json")
BATCH = 100


def fail(msg, code=2):
    print(f"BLOCKED: {msg}", file=sys.stderr); sys.exit(code)


def resolve_bundle(explicit=None, require_explicit=False):
    if explicit:
        if not os.path.isfile(explicit):
            fail(f"bundle not found: {explicit}")
        return explicit
    env_path = os.environ.get("WEEKLY_BUNDLE_PATH")
    if env_path:
        if not os.path.isfile(env_path):
            fail(f"WEEKLY_BUNDLE_PATH not found: {env_path}")
        return env_path
    if require_explicit:
        fail("CI requires an explicit bundle via --bundle or WEEKLY_BUNDLE_PATH")
    files = sorted(glob.glob(BUNDLE_GLOB), key=os.path.getmtime)
    if not files:
        fail("no staged weekly signals bundle found under weekly_dashboard_refresh_*/")
    return files[-1]  # local convenience only; never used in CI


def load_bundle(path):
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as e:
        fail(f"bundle {path} is not valid JSON: {e}")
    meta = bundle.get("meta")
    if not isinstance(meta, dict):
        fail(f"bundle {path} missing meta object")
    week = meta.get("week")
    season = meta.get("season")
    built_at = meta.get("built_at")
    if not isinstance(week, int) or week < 1 or week > 25:
        fail(f"bundle {path} meta.week missing or not a sane week int: {week!r}")
    if not isinstance(season, int) or season < 2020 or season > 2100:
        fail(f"bundle {path} meta.season missing or not a sane season int: {season!r}")
    if not built_at or not isinstance(built_at, str):
        fail(f"bundle {path} meta.built_at missing")
    if not isinstance(bundle.get("players"), list) or not bundle["players"]:
        fail(f"bundle {path} has no players")
    return bundle, meta, sha


def classify(row):
    """FULL iff non-null vegas_leg; STUB otherwise. Anything else is an error."""
    if "vegas_leg" not in row:
        return None  # unrecognized shape
    return "FULL" if row.get("vegas_leg") is not None else "STUB"


def dedupe(players):
    """Per normalized player_key keep the FULL row. Fail closed on
    duplicate FULL rows, a FULL+non-STUB pair, or empty keys."""
    best = {}
    for idx, row in enumerate(players):
        if not isinstance(row, dict):
            fail(f"player row {idx} is not an object")
        key = (row.get("player_key") or "").strip().lower()
        if not key:
            fail(f"player row {idx} missing player_key")
        shape = classify(row)
        if shape is None:
            fail(f"player {key}: unrecognized row shape (no vegas_leg field)")
        prior = best.get(key)
        if prior is None:
            best[key] = (shape, row)
            continue
        if shape == "FULL" and prior[0] == "FULL":
            fail(f"player {key}: two FULL rows in bundle")
        if shape != "STUB" or prior[0] != "FULL":
            # FULL+FULL handled above; remaining bad combos: STUB-over-FULL
            # (can't happen since we keep FULL), STUB+STUB (keep first,
            # permitted), FULL+unknown (unreachable). STUB+STUB falls through.
            pass
        if prior[0] == "FULL":
            continue  # keep FULL
        best[key] = (shape, row)
    return {k: v[1] for k, v in best.items()}, {k: v[0] for k, v in best.items()}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Load the weekly signals bundle into Supabase.")
    ap.add_argument("--bundle", default=None, help="Explicit bundle path.")
    ap.add_argument("--expected-week", type=int, default=None,
                    help="Refuse to publish if bundle week differs.")
    ap.add_argument("--allow-rollback", action="store_true",
                    help="Permit publishing an older (season, week, built_at); audited in manifest.")
    args = ap.parse_args(argv)

    in_ci = os.environ.get("CI") == "true" or bool(os.environ.get("GITHUB_ACTIONS"))
    bundle_path = resolve_bundle(args.bundle, require_explicit=in_ci)
    bundle, meta, bundle_sha = load_bundle(bundle_path)
    week = meta["week"]; season = meta["season"]; built_at = meta["built_at"]

    expected_week = args.expected_week
    if expected_week is None and os.environ.get("EXPECTED_WEEK"):
        try:
            expected_week = int(os.environ["EXPECTED_WEEK"])
        except ValueError:
            fail(f"EXPECTED_WEEK not an int: {os.environ['EXPECTED_WEEK']!r}")
    if expected_week is not None and week != expected_week:
        fail(f"bundle week {week} != expected week {expected_week}")

    rows, shapes = dedupe(bundle["players"])
    if not rows:
        fail("dedupe produced zero rows")

    manifest = {"engine": "v4", "loader": "pipelines/load_weekly_dashboard.py",
                "bundle": os.path.basename(bundle_path), "bundle_path": bundle_path,
                "bundle_sha256": bundle_sha, "season": season, "week": week,
                "bundle_built_at": built_at, "bundle_source_file": meta.get("source_file"),
                "n_bundle_players": len(bundle["players"]), "n_deduped": len(rows)}
    if args.allow_rollback:
        manifest["allow_rollback"] = True

    current = sbclient.get("weekly_dashboard_runs",
        "?select=run_id,week,season,is_current,built_at,source_manifest"
        "&is_current=eq.true"
        f"&season=eq.{season}&week=eq.{week}")
    for r in current:
        m = r.get("source_manifest") or {}
        if m.get("bundle_sha256") == bundle_sha and m.get("bundle_built_at") == built_at:
            print(f"NOOP: season {season} week {week} bundle sha {bundle_sha[:12]} "
                  f"already current (run {r['run_id']})")
            return 0

    if not args.allow_rollback:
        # Reject any current run strictly newer than what we're about to publish.
        all_current = sbclient.get("weekly_dashboard_runs",
            "?select=run_id,season,week,built_at&is_current=eq.true")
        for r in all_current:
            r_season = r.get("season", 2026)
            if r_season > season or (r_season == season and r.get("week", 0) > week):
                fail(f"refusing rollback: current run {r['run_id']} is "
                     f"season {r_season} week {r.get('week')}; pass --allow-rollback to override")
            if r_season == season and r.get("week") == week and r.get("built_at") and r["built_at"] > built_at:
                fail(f"refusing rollback: current run {r['run_id']} for week {week} "
                     f"has newer built_at {r['built_at']} > {built_at}; pass --allow-rollback to override")

    run_rows = sbclient.post("weekly_dashboard_runs",
        {"week": week, "season": season, "built_at": built_at,
         "source_manifest": manifest, "is_current": False})
    run_id = run_rows[0]["run_id"]

    items = [{"run_id": run_id, "player_key": key,
              "position": row.get("pos") or None, "team": row.get("team") or None,
              "signal": row} for key, row in rows.items()]
    for i in range(0, len(items), BATCH):
        sbclient.post("weekly_dashboard_signals", items[i:i+BATCH], prefer="return=minimal")

    got = sbclient.get("weekly_dashboard_signals",
        f"?select=player_key&run_id=eq.{run_id}&limit={len(items)+1}")
    if len(got) != len(items):
        fail("signal count mismatch (run left non-current)")

    for r in current:
        if r["run_id"] != run_id and r.get("is_current"):
            sbclient.patch("weekly_dashboard_runs", {"is_current": False},
                           f"?run_id=eq.{r['run_id']}")
    sbclient.patch("weekly_dashboard_runs", {"is_current": True}, f"?run_id=eq.{run_id}")

    check = sbclient.get("v_current_weekly_signals",
        f"?select=player_key&season=eq.{season}&week=eq.{week}&limit={len(items)+1}")
    if len(check) != len(items):
        fail("view count mismatch")

    print(f"OK: season {season} week {week} current with {len(items)} rows "
          f"(run {run_id}, bundle sha {bundle_sha[:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

# Behavior changes

- **Bundle selection:** `--bundle` / `WEEKLY_BUNDLE_PATH` mandatory in CI (`CI=true` or `GITHUB_ACTIONS` set); mtime glob fallback refused there. meta.week/season/built_at validated fail-closed (sane int ranges, non-empty string). New `--expected-week` plus `EXPECTED_WEEK` env cross-check; mismatch blocks with exit 2.
- **Dedupe:** `richness()` deleted. Explicit FULL/STUB via non-null `vegas_leg`; rows missing the `vegas_leg` key entirely, rows with missing `player_key`, and duplicate FULL rows for one key all fail closed. Full/stub pairs resolve to the FULL row deterministically.
- **Idempotency:** bundle bytes hashed (sha256) once at read; manifest carries `bundle_sha256`, `season`, `week`. NOOP requires the *current* run for the same (season, week) to have matching hash and built_at — a renamed copy with identical bytes NOOPs; a same-metadata rebuild with changed contents loads a new run.
- **Rollback guard:** publishing behind the current (season, week) or behind the current week's `built_at` blocks with exit 2 unless `--allow-rollback`, which is recorded in the manifest.
- **Kept as-is:** batch inserts, read-back verification, promote-then-verify, exit codes 0/2, sbclient import fallback.

# Regression-test sketch

```python
# tests/test_jeg394_loader.py — pytest, monkeypatch sbclient with an in-memory fake.
import hashlib, json, shutil, pytest, importlib

def make_bundle(season=2026, week=4, n_full=390, stubs_per_full=None, mutate=None):
    players = []
    for i in range(n_full):
        full = {"player_key": f"p{i}", "pos": "RB", "team": "KC",
                "vegas_leg": "propline", "vegas_std": 10.0+i, "coverage_ok": True,
                "expert_std": 9.0, "pts_delta_ppr": 1.0, "ecr_pos_rank": i+1,
                "vegas_pos_rank": i+1, "n_pos": 40, "delta": 0.0, "abs_delta": 0.0,
                "direction": "flat", "pos_level_gap": 0, "pts_delta_adj": 0,
                "post_worthy": False, "worthy_reason": None, "td_p_yes": False,
                "expert_td_exp": 0.0, "vegas_provenance": "x", "expert_ppr": 9.5,
                "expert_half": 9.2, "vegas_half": 9.7, "vegas_ppr": 10.1,
                "ecr_official": "y"}
        stub = dict(full, vegas_leg=None, vegas_std=None, vegas_half=None,
                    vegas_ppr=None, coverage_ok=False, pts_delta_ppr=None)
        players += [full, stub]
    meta = {"week": week, "season": season, "built_at": f"{season}-W{week}",
            "source_file": "src.json", "n_players": len(players)}
    if mutate: meta, players = mutate(meta, players)
    return {"meta": meta, "players": players}

def write_bundle(tmp_path, bundle):
    p = tmp_path / "staged_bundle_x.json"
    p.write_bytes(json.dumps(bundle, sort_keys=True).encode())
    return p

def run_loader(path, extra=()):
    import pipelines.load_weekly_dashboard as L
    return L.main(["--bundle", str(path), *extra])

# 1. 505-row pattern: 115 full/stub pairs + 275 full-only => 390 keys, all FULL.
def test_505_row_pattern(tmp_path, monkeypatch):
    bundle = make_bundle(n_full=390)          # 390 FULL + 390 STUB = 780; to hit
    # the exact 505/390/115 fixture, inject 115 pairs and 275 fulls:
    players = ([dict(make_bundle()["players"][0], player_key=f"f{i}") for i in range(275)]
               + [x for i in range(115) for x in (
                   dict(make_bundle()["players"][0], player_key=f"g{i}"),
                   dict(make_bundle()["players"][1], player_key=f"g{i}"))])
    b = {"meta": make_bundle()["meta"] | {"n_players": 505}, "players": players}
    p = write_bundle(tmp_path, b)
    fake = FakeSB()
    monkeypatch.setattr("pipelines.load_weekly_dashboard.sbclient", fake)
    assert run_loader(p) == 0
    stored = fake.signals_of(fake.last_run)
    assert len(stored) == 390
    assert all(r["signal"]["vegas_leg"] is not None for r in stored)  # all FULL
    assert all(fake.runs[0]["is_current"] is False or fake.runs[-1]["is_current"] for _ in [0])

# 2. Same-content rebuild (identical bytes, new path) -> NOOP, exit 0, no new run.
def test_same_content_rebuild_noop(tmp_path, monkeypatch):
    b = make_bundle()
    p1 = write_bundle(tmp_path, b)
    fake = FakeSB(); monkeypatch.setattr("pipelines.load_weekly_dashboard.sbclient", fake)
    assert run_loader(p1) == 0
    p2 = tmp_path / "renamed.json"; shutil.copyfile(p1, p2)
    before = len(fake.runs)
    assert run_loader(p2) == 0
    assert len(fake.runs) == before and fake.runs[-1]["is_current"]

# 3. Same metadata, changed contents -> new run, not NOOP.
def test_rebuild_changed_content_loads(tmp_path, monkeypatch):
    b = make_bundle(); p1 = write_bundle(tmp_path, b)
    fake = FakeSB(); monkeypatch.setattr("pipelines.load_weekly_dashboard.sbclient", fake)
    run_loader(p1)
    b2 = make_bundle(); b2["players"][0]["vegas_std"] = 99.0
    p2 = write_bundle(tmp_path, b2)
    assert run_loader(p2) == 0 and len(fake.runs) == 2

# 4. Older week / season -> blocked exit 2 without --allow-rollback.
def test_rollback_blocked(tmp_path, monkeypatch):
    fake = FakeSB(); monkeypatch.setattr("pipelines.load_weekly_dashboard.sbclient", fake)
    run_loader(write_bundle(tmp_path, make_bundle(week=5)))
    p_old = write_bundle(tmp_path, make_bundle(week=4))
    with pytest.raises(SystemExit) as e:
        run_loader(p_old)
    assert e.value.code == 2
    # and with --allow-rollback it proceeds and is audited:
    fake2 = FakeSB(); monkeypatch.setattr("pipelines.load_weekly_dashboard.sbclient", fake2)
    assert run_loader(p_old, extra=["--allow-rollback"]) == 0
    assert fake2.runs[-1]["source_manifest"].get("allow_rollback") is True

# 5. Expected week mismatch + dedupe fail-closed.
def test_expected_week_and_dup_full(tmp_path, monkeypatch):
    fake = FakeSB(); monkeypatch.setattr("pipelines.load_weekly_dashboard.sbclient", fake)
    p = write_bundle(tmp_path, make_bundle(week=4))
    with pytest.raises(SystemExit) as e: run_loader(p, extra=["--expected-week", "5"])
    assert e.value.code == 2
    b = make_bundle(n_full=2)
    b["players"].append(dict(b["players"][0]))  # two FULL rows for one key
    with pytest.raises(SystemExit) as e: run_loader(write_bundle(tmp_path, b))
    assert e.value.code == 2
```

(`FakeSB` is a minimal stub recording `runs` and `signals` dicts and mirroring the get/post/patch shapes the loader uses; `signals_of(run_id)` returns inserted signal rows.)