#!/usr/bin/env python3
"""Twice-weekly FantasyPros weekly-ECR refresh driver (day-agnostic).

Runs Monday 06:35 and Thursday 06:35 America/Chicago via two cron jobs that
share this script. It never touches a browser itself: the caller either
  (a) skips the download when the current week's CSVs are fresh
      (--check-fresh), or
  (b) has a browser task download the 4 position CSVs into --csv-dir first.

Then this script: stages CSVs -> loads weekly ECR into Supabase ->
rebuilds the ECR JSON files -> verifies row counts.

Usage:
  refresh_ecr_weekly.py --check-fresh [--week N] [--season 2026]
                        [--fresh-hours 12] [--with-projections]
  refresh_ecr_weekly.py [--csv-dir DIR] [--week N] [--season 2026]
                        [--fresh-hours 12] [--with-projections]

  --with-projections : also stage/load/verify the 4 weekly expert
      projections CSVs (proj_{qb,rb,wr,te}_wk{N}.csv) — the ECR feed's
      expert point projections, the expert leg of the signal pipeline.

Modes:
  --check-fresh : exit 0 (prints FRESH) if all required current-week CSVs
                  exist in data/fantasypros/ and are newer than
                  --fresh-hours; exit 3 (prints STALE) otherwise.
  default       : stage + load + build + verify.
                  Exit 0 OK, 2 BLOCKED (missing files / week mismatch /
                  verification failed), 1 unexpected failure.

Accepted --csv-dir filenames (case-insensitive):
  ECR canonical : ecr_{qb,rb,wr,te}_wk{N}.csv
  ECR server    : FantasyPros_{season}_Week_{N}_{QB,RB,WR,TE}_Rankings.csv
                  (optionally prefixed, e.g. "browser-download-...-")
  proj canonical: proj_{qb,rb,wr,te}_wk{N}.csv
  proj server   : FantasyPros_{season}_Week_{N}_{QB,RB,WR,TE}_Projections.csv

Expected weekly row counts (2026 Week 3 reference; tolerance below):
  qb 37, rb 80, wr 89, te 34 -> ~240 DB rows after name matching.
  (Week 3 was re-anchored 2026-09-22 after FP trimmed the
  weekly rankings page for Week 3; verified 2026-09-22 against FP's live
  pages — CSV counts match the live ranked universes within intraday
  expert-update drift, top-10 sets identical.)
With --with-projections, the 4 weekly projections CSVs are staged/loaded/
verified too (Week 1 player-count reference: qb 81, rb 130, wr 203, te 123).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(BASE, ".venv", "bin", "python")
PY = VENV_PY if os.path.exists(VENV_PY) else sys.executable
DATA_FP = os.path.join(BASE, "data", "fantasypros")

sys.path.insert(0, BASE)
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-football-signal/bin"))
sys.path.insert(0, os.path.join(os.path.expanduser("~"),
                                "workspace/skills/supabase-mgmt/bin"))

POSITIONS = ["qb", "rb", "wr", "te"]
# 2026 Week 3 reference CSV row counts, counted as (physical lines - 1)
# to match count_csv_rows() below (files may contain blank lines the
# loader skips, and a missing trailing newline)
# (Week 1 was 102/180/280/162; Week 2 was 101/139/226/137; FP trimmed the
# weekly page again for Week 3 — re-anchored 2026-09-22 after verifying CSVs
# against FP's live pages: QB 36 / RB 78 / WR 88 / TE 33 ranked, plus the
# export's usual empty-rank artifact rows)
BASELINE_ROWS = {"qb": 37, "rb": 80, "wr": 89, "te": 34}
ROW_TOL = 0.30          # per-file CSV rows must be within +-30% of baseline
DB_MIN_TOTAL = 220      # ecr_weekly.json keys / DB rows floor (baseline 240)
DB_MIN_FRAC = 0.80      # per-position DB rows >= 80% of that file's CSV rows
# ECR-feed expert projections CSVs (players per file, Week 1 reference)
PROJ_BASELINE = {"qb": 81, "rb": 130, "wr": 203, "te": 123}

SERVER_RE = re.compile(
    r"FantasyPros_(\d{4})_Week_(\d+)_([A-Za-z]+)_Rankings\.csv$", re.IGNORECASE)
CANON_RE = re.compile(r"ecr_(qb|rb|wr|te)_wk(\d+)\.csv$", re.IGNORECASE)
PROJ_SERVER_RE = re.compile(
    r"FantasyPros_(\d{4})_Week_(\d+)_([A-Za-z]+)_Projections\.csv$", re.IGNORECASE)
PROJ_CANON_RE = re.compile(r"proj_(qb|rb|wr|te)_wk(\d+)\.csv$", re.IGNORECASE)


def log(msg):
    print(msg, flush=True)


def check_scoring(week):
    """Non-exiting core of the scoring-mode check.

    Returns (ok: bool, detail: str). Importable by QA tooling so the same
    contract runs in the wrapper and in dashboard bundle builds.
    """
    import csv
    import statistics
    from loaders.fantasypros import read_projections_dict
    from engine.snapshot import norm

    try:
        proj = read_projections_dict(week)
    except FileNotFoundError as e:
        return False, f"projections CSVs missing for week {week}: {e}"

    rec = {}
    for pos in ("rb", "wr", "te"):
        try:
            fh = open(proj_canon_name(pos, week), newline="")
        except OSError:
            return False, f"missing {proj_canon_name(pos, week)}"
        with fh:
            for r in csv.DictReader(fh):
                try:
                    rec[norm((r.get("Player") or "").strip())] = float(
                        r.get("REC") or 0)
                except ValueError:
                    pass

    xs, ys = [], []  # receptions, residual vs locally computed half-PPR
    per_pos = {}
    for pos in ("rb", "wr", "te"):
        path = canon_name(pos, week)
        resid = []
        try:
            fh = open(path, newline="")
        except OSError:
            return False, f"missing {path}"
        with fh:
            for r in csv.DictReader(fh):
                n = norm((r.get("PLAYER NAME") or "").strip())
                p = proj.get(n)
                if not p or n not in rec:
                    continue
                try:
                    f = float((r.get("PROJ. FPTS") or "").strip())
                except (ValueError, AttributeError):
                    continue
                rh = f - p["half"]
                resid.append(rh)
                xs.append(rec[n])
                ys.append(rh)
        # Per-position sample-size floor for the scoring check. FP trimmed the
        # weekly rankings pages for Week 3 (2026-09-22; TE ranks 33 players),
        # so the old floor of 50 would block forever on complete, verified
        # data. 25 rows still gives a stable median and the pooled
        # corr(residual, receptions) runs over ~200 rows — the Standard-scored
        # defect (residual ~-0.5/rec, |c| ~ 0.65) is unmistakable at this n.
        if len(resid) < 25:
            return False, (f"only {len(resid)} joined {pos} rows (< 25); "
                           f"cannot validate scoring mode")
        per_pos[pos] = statistics.median(resid)
    pooled = statistics.median(ys)
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    c = cov / ((vx * vy) ** 0.5) if vx * vy > 0 else 0.0
    detail = (f"pooled median residual vs half-PPR {pooled:+.2f}, "
              f"corr(residual, receptions) {c:+.2f} "
              f"({', '.join(f'{p} {m:+.2f}' for p, m in per_pos.items())})")
    # A Standard-scored file sits ~-0.5/rec below half-PPR: strong negative
    # correlation. Full-PPR mirrors it positive. Either is a hard fail.
    if c < -0.4:
        return False, (f"ECR rankings CSVs look Standard-scored, not Half-PPR "
                       f"({detail}). Fix the FP page scoring and re-pull.")
    if c > 0.4:
        return False, (f"ECR rankings CSVs look Full-PPR-scored, not Half-PPR "
                       f"({detail}). Fix the FP page scoring and re-pull.")
    if abs(pooled) > 1.0:
        return False, (f"ECR rankings CSVs are not Half-PPR scored "
                       f"({detail}). Fix the FP page scoring and re-pull.")
    return True, f"Half-PPR confirmed ({detail})"


def verify_scoring(week):
    """Fail-closed scoring-mode check on the staged ECR rankings CSVs.

    The FantasyPros rankings page's scoring dropdown silently changes the
    PROJ. FPTS column. On 2026-09-17 the 06:35 pull downloaded genuinely
    Standard-scored rankings CSVs (pooled median residual vs locally computed
    half-PPR -0.63, corr(residual, receptions) -0.65 -- the half-point-ppr URL
    variants were not used), so the ECR leg correctly held on the 2026-09-16
    snapshot. A corrected re-pull at ~08:00 used the half-point-ppr URLs; this
    check confirmed Half-PPR (pooled median residual +0.12, corr +0.10) and the
    leg was rebuilt at 13:07. Do not "eyeball" the values -- run the check.

    Method: compare each rankings CSV's PROJ. FPTS against the half-PPR
    points computed locally from the granular projections CSVs (scoring-
    invariant inputs). A Half-PPR file has pooled median signed residual
    near 0 and no correlation between the residual and receptions; a
    Standard file's residual falls ~-0.5 per reception (strong negative
    correlation); Full-PPR mirrors it positive. Blocks the load on mismatch.
    """
    ok, detail = check_scoring(week)
    if not ok:
        log(f"BLOCKED: scoring check: {detail} Fix the FP page scoring "
            f"and re-pull.")
        sys.exit(2)
    log(f"scoring check: {detail}")


def current_week(season):
    from engine.week import current_week as cw
    try:
        return cw(season)
    except RuntimeError as e:
        log(f"BLOCKED: cannot detect current NFL week: {e}")
        sys.exit(2)


def canon_name(pos, week):
    return os.path.join(DATA_FP, f"ecr_{pos}_wk{week}.csv")


def proj_canon_name(pos, week):
    return os.path.join(DATA_FP, f"proj_{pos}_wk{week}.csv")


def identify(path):
    """Return (pos, week) for a recognizable ECR filename, else None."""
    base = os.path.basename(path)
    m = CANON_RE.search(base) or SERVER_RE.search(base)
    if not m:
        return None
    if m.re is CANON_RE:
        return m.group(1).lower(), int(m.group(2))
    pos = m.group(3).lower()
    return (pos, int(m.group(2))) if pos in POSITIONS else None


def identify_proj(path):
    """Return (pos, week) for a recognizable projections filename, else None."""
    base = os.path.basename(path)
    m = PROJ_CANON_RE.search(base) or PROJ_SERVER_RE.search(base)
    if not m:
        return None
    if m.re is PROJ_CANON_RE:
        return m.group(1).lower(), int(m.group(2))
    pos = m.group(3).lower()
    return (pos, int(m.group(2))) if pos in POSITIONS else None


def stage_csvs(csv_dir, week, season, with_projections=False):
    """Copy/rename the 4 position CSVs into data/fantasypros/ canonical names.
    With --with-projections, the 4 projections CSVs are staged too.
    BLOCKED (exit 2) if any position is missing or the server week mismatches."""
    if not os.path.isdir(csv_dir):
        log(f"BLOCKED: csv dir not found: {csv_dir}")
        sys.exit(2)
    found, found_proj = {}, {}
    for fn in sorted(os.listdir(csv_dir)):
        full = os.path.join(csv_dir, fn)
        ident = identify(fn)
        if ident:
            pos, w = ident
            if w != week:
                log(f"BLOCKED: {fn} is Week {w} but target week is {week}; "
                    f"refusing to stage across weeks (stale-data guard).")
                sys.exit(2)
            found[pos] = full
            continue
        if with_projections:
            pident = identify_proj(fn)
            if pident:
                pos, w = pident
                if w != week:
                    log(f"BLOCKED: {fn} is Week {w} but target week is {week}; "
                        f"refusing to stage across weeks (stale-data guard).")
                    sys.exit(2)
                found_proj[pos] = full
    missing = [p for p in POSITIONS if p not in found]
    if missing:
        log(f"BLOCKED: missing ECR CSVs for positions: {missing} in {csv_dir}")
        sys.exit(2)
    if with_projections:
        missing_p = [p for p in POSITIONS if p not in found_proj]
        if missing_p:
            log(f"BLOCKED: missing projections CSVs for positions: "
                f"{missing_p} in {csv_dir}")
            sys.exit(2)
    for pos in POSITIONS:
        dest = canon_name(pos, week)
        if os.path.abspath(found[pos]) != os.path.abspath(dest):
            shutil.copy2(found[pos], dest)
            log(f"staged {os.path.basename(found[pos])} -> {os.path.basename(dest)}")
        else:
            log(f"already canonical: {os.path.basename(dest)}")
        if with_projections:
            pdest = proj_canon_name(pos, week)
            if os.path.abspath(found_proj[pos]) != os.path.abspath(pdest):
                shutil.copy2(found_proj[pos], pdest)
                log(f"staged {os.path.basename(found_proj[pos])} -> {os.path.basename(pdest)}")
            else:
                log(f"already canonical: {os.path.basename(pdest)}")


def csvs_present(week, with_projections=False):
    ok = all(os.path.exists(canon_name(p, week)) for p in POSITIONS)
    if with_projections:
        ok = ok and all(os.path.exists(proj_canon_name(p, week))
                       for p in POSITIONS)
    return ok


def check_fresh(week, fresh_hours, with_projections=False):
    cutoff = time.time() - fresh_hours * 3600
    stale = []
    paths = [("ecr", canon_name(p, week)) for p in POSITIONS]
    if with_projections:
        paths += [("proj", proj_canon_name(p, week)) for p in POSITIONS]
    for kind, p in paths:
        if not os.path.exists(p):
            stale.append(f"{kind} {os.path.basename(p)}: missing")
        elif os.path.getmtime(p) < cutoff:
            age_h = (time.time() - os.path.getmtime(p)) / 3600
            stale.append(f"{kind} {os.path.basename(p)}: {age_h:.1f}h old")
    if stale:
        log("STALE: " + "; ".join(stale))
        return False
    log(f"FRESH: week-{week} ECR CSVs"
        + (" + projections CSVs" if with_projections else "")
        + f" newer than {fresh_hours}h")
    return True


def run_loader(week, season, with_projections=False):
    cmd = [PY, os.path.join(BASE, "loaders", "fantasypros.py"),
           "--week", str(week), "--season", str(season)]
    if not with_projections:
        cmd.append("--ecr-only")
    log("+ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    log(r.stdout[-3000:])
    if r.returncode != 0:
        log(f"BLOCKED: loader failed (exit {r.returncode}):\n{r.stderr[-2000:]}")
        sys.exit(2)
    return r.stdout


def run_build():
    cmd = [PY, os.path.join(BASE, "bin", "build_ecr_files.py")]
    log("+ " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    log(r.stdout[-2000:])
    if r.returncode != 0:
        log(f"BLOCKED: build_ecr_files failed (exit {r.returncode}):\n{r.stderr[-2000:]}")
        sys.exit(2)


def count_csv_rows(path):
    with open(path, encoding="utf-8-sig") as f:
        return sum(1 for _ in f) - 1  # minus header


def verify(week, season, with_projections=False):
    import mgmt
    problems = []
    csv_rows, db_rows = {}, {}
    rankers = mgmt.query(
        "select id, display_name from rankers where ecr_type='weekly';")
    rid_by_pos = {}
    for r in rankers:
        m = re.search(r"ECR (QB|RB|WR|TE)$", r["display_name"] or "")
        if m:
            rid_by_pos[m.group(1).lower()] = r["id"]
    for pos in POSITIONS:
        n = count_csv_rows(canon_name(pos, week))
        csv_rows[pos] = n
        base = BASELINE_ROWS[pos]
        if abs(n - base) > base * ROW_TOL:
            problems.append(f"{pos}: {n} CSV rows vs baseline {base} (tol {ROW_TOL:.0%})")
        rid = rid_by_pos.get(pos)
        dbn = 0
        if rid:
            rows = mgmt.query(
                f"select count(*) c from ranker_rankings where ranker_id='{rid}' "
                f"and season={season} and week={week};")
            dbn = rows[0]["c"] if rows else 0
        db_rows[pos] = dbn
        if dbn < n * DB_MIN_FRAC:
            problems.append(f"{pos}: {dbn} DB rows < {DB_MIN_FRAC:.0%} of {n} CSV rows")
    total_db = sum(db_rows.values())
    if total_db < DB_MIN_TOTAL:
        problems.append(f"total DB rows {total_db} < floor {DB_MIN_TOTAL}")
    wk_path = os.path.join(BASE, "data", "ecr_weekly.json")
    pos_path = os.path.join(BASE, "data", "ecr_pos.json")
    wk_keys = len(json.load(open(wk_path))) if os.path.exists(wk_path) else 0
    pos_keys = len(json.load(open(pos_path))) if os.path.exists(pos_path) else 0
    if wk_keys < DB_MIN_TOTAL:
        problems.append(f"ecr_weekly.json has {wk_keys} keys < floor {DB_MIN_TOTAL}")
    if pos_keys != wk_keys:
        problems.append(f"ecr_pos.json ({pos_keys} keys) != ecr_weekly.json ({wk_keys} keys)")
    proj_rows = {}
    if with_projections:
        for pos in POSITIONS:
            n = count_csv_rows(proj_canon_name(pos, week))
            proj_rows[pos] = n
            base = PROJ_BASELINE[pos]
            if abs(n - base) > base * ROW_TOL:
                problems.append(
                    f"proj_{pos}: {n} CSV rows vs baseline {base} (tol {ROW_TOL:.0%})")
    summary = {"week": week, "csv_rows": csv_rows, "db_rows": db_rows,
               "db_total": total_db, "ecr_weekly_keys": wk_keys,
               "proj_rows": proj_rows,
               "status": "OK" if not problems else "VERIFY_FAIL"}
    log("SUMMARY: " + json.dumps(summary))
    if problems:
        log("BLOCKED: verification failed:\n - " + "\n - ".join(problems))
        # Diagnostic hint: a uniform shortfall across ALL positions usually
        # means FP changed the weekly page depth (re-anchor BASELINE_ROWS
        # after verifying the CSVs against FP's live pages); a single-position
        # shortfall usually means a truncated/partial export.
        short = [p for p in POSITIONS
                 if csv_rows[p] < BASELINE_ROWS[p] * (1 - ROW_TOL)]
        if len(short) == len(POSITIONS):
            log("HINT: all four positions are below baseline — FP likely "
                "changed the weekly rankings page depth. Verify the CSVs "
                "against FP's live rankings pages; if they match, re-anchor "
                "BASELINE_ROWS/DB_MIN_TOTAL to the new reference and re-run.")
        sys.exit(2)
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv-dir", default=None)
    ap.add_argument("--week", type=int, default=None)
    ap.add_argument("--season", type=int, default=2026)
    ap.add_argument("--fresh-hours", type=float, default=12)
    ap.add_argument("--check-fresh", action="store_true")
    ap.add_argument("--with-projections", action="store_true",
                    help="also stage/load/verify the weekly ECR expert "
                         "projections CSVs (proj_{qb,rb,wr,te}_wkN.csv); "
                         "the projections pull is folded into this job")
    a = ap.parse_args()

    week = a.week or current_week(a.season)
    log(f"target: season {a.season} week {week}"
        + (" + projections" if a.with_projections else ""))

    if a.check_fresh:
        sys.exit(0 if check_fresh(week, a.fresh_hours, a.with_projections) else 3)

    if a.csv_dir:
        stage_csvs(a.csv_dir, week, a.season, a.with_projections)
    else:
        missing = [p for p in POSITIONS
                   if not os.path.exists(canon_name(p, week))]
        if a.with_projections:
            missing += [f"proj_{p}" for p in POSITIONS
                        if not os.path.exists(proj_canon_name(p, week))]
        if missing:
            log(f"BLOCKED: no --csv-dir and canonical CSVs missing for week "
                f"{week}: {missing}")
            sys.exit(2)
        log("no --csv-dir: using canonical CSVs in data/fantasypros/")

    if not csvs_present(week, a.with_projections):
        log(f"BLOCKED: canonical CSVs missing for week {week}")
        sys.exit(2)
    verify_scoring(week)
    run_loader(week, a.season, a.with_projections)
    run_build()
    verify(week, a.season, a.with_projections)
    log("DONE: weekly ECR refresh complete"
        + (" (ranks + projections)" if a.with_projections else ""))


if __name__ == "__main__":
    main()
