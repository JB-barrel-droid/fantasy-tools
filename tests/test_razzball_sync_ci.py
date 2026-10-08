"""Razzball ROS puller + razzball-supabase-sync.yml (moved off Muse 2026-10-06).

Pins, each negative-tested against a simulated broken state:
  - no GitHub `schedule:` (pg_cron `razzball-sync-live` owns scheduling);
  - dry triggers never write: the real step scripts run with a fake python3,
    and the saver must get --dry-run on every non-write trigger; the monitored
    check is recorded only in write mode;
  - the puller emits exactly the row shape stored in public.razzball_projections
    (raw_stats keys of the 2026-10-01 vintage), computes per-game stats as
    total / games, and copies the QB STD PPG to all three scorings;
  - it fails closed on a non-200 page, a changed header layout, and a
    truncated table (row floor); it reads the stats table, not the sidebar.
"""
import csv
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import find_step, script_of  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))
import pull_razzball_ros as rz  # noqa: E402
import save_razzball_references as saver  # noqa: E402

WORKFLOW = (ROOT / ".github/workflows/razzball-supabase-sync.yml").read_text(encoding="utf-8")
MIGRATION = (ROOT / "supabase/migrations/razzball_sync_pg_cron.sql").read_text(encoding="utf-8")
RECORD = "Record the monitored check"
RECORD_IF = "steps.cfg.outputs.mode == 'write'"

# raw_stats keys of every stored row (public.razzball_projections, vintage
# 2026-10-01, written by save_razzball_references.py from Muse's snapshot).
STORED_RAW_STATS_KEYS = {
    "pg_att", "pg_cmp", "pg_fum", "pg_int", "pg_rec", "pg_tgt", "pg_sacks",
    "pg_snaps", "pg_rec_td", "share_tgt", "pg_pass_td", "pg_rec_yds",
    "pg_rush_td", "share_rush", "pg_pass_yds", "pg_rush_att", "pg_rush_yds",
    "razzball_snapshot_date",
}

# Header layouts as published 2026-10-06.
LAYOUTS = {
    "QB": ["#", "Name", "Team", "Games", "Health", "Snaps", "Cmp", "Att", "Cmp %", "Pass Yds", "YPC",
           "YPA", "Pass TD", "Int", "Scks", "Rush", "Rush Yds", "Rush Avg", "Run TD", "Fum Lst",
           "STD PTS", "STD PPG"],
    "RB": ["#", "Name", "Team", "G", "H", "Snap", "% Tm Rush", "Rush", "Rush Yds", "Yds/ Rush", "Run TD",
           "% Tm Tgt", "Tgt", "Rec", "Rec Yds", "Yds/ Rec", "Yds/ Tgt", "Rec TD", "STD PTS",
           "1/2 PPR PTS", "PPR PTS", "STD PPG", "1/2 PPR PPG", "PPR PPG"],
    "WR": ["#", "Name", "Team", "G", "H", "Snap", "% Tm Tgt", "Tgt", "Rec", "Rec Yds", "Yds/ Rec",
           "Yds/ Tgt", "Rec TD", "Rush", "Rush Yds", "Yds/ Rush", "Run TD", "STD PTS", "1/2 PPR PTS",
           "PPR PTS", "STD PPG", "1/2 PPR PPG", "PPR PPG"],
    "TE": ["#", "Name", "Team", "G", "H", "Snap", "% Tm Tgt", "Tgt", "Rec", "Rec Yds", "Yds/ Rec",
           "Yds/ Tgt", "Rec TD", "Fum", "Fum Lost", "STD PTS", "1/2 PPR PTS", "PPR PTS", "STD PPG",
           "1/2 PPR PPG", "PPR PPG"],
}
# First rows as published 2026-10-06 (Josh Allen, Jahmyr Gibbs, Puka Nacua, Brock Bowers).
FIRST = {
    "QB": ["", "Josh Allen", "BUF", "13", "", "772", "268", "382", "70.2", "2996", "11.16", "7.84", "17.8",
           "9.2", "20.5", "95.0", "460.9", "4.9", "10.7", "1.7", "279.8", "21.5"],
    "RB": ["", "Jahmyr Gibbs", "DET", "13", "", "614", "78.1", "245", "1245.6", "5.1", "12.1", "17.1",
           "75.5", "57.9", "489", "8.4", "6.5", "2.0", "256.7", "285.7", "314.7", "19.7", "22.0", "24.2"],
    "WR": ["", "Puka Nacua", "LAR", "13", "", "723", "28.1", "135.9", "96.4", "1332", "13.8", "9.8", "6.2",
           "6.8", "38", "5.7", "0.4", "175.8", "224.0", "272.2", "13.5", "17.2", "20.9"],
    "TE": ["", "Brock Bowers", "LV", "13", "", "634", "23.3", "103.5", "79.2", "876", "11.1", "8.5", "4.9",
           "0.6", "0.3", "117.6", "157.1", "196.7", "9.0", "12.1", "15.1"],
}
N_ROWS = {"QB": 70, "RB": 110, "WR": 160, "TE": 90}


STAMP = "Updated: 2026-10-05 09:07:08 PM EST"


def page(pos, n=None, headers=None, first=None, stamp=STAMP, overall_rows=0):
    headers = headers or LAYOUTS[pos]
    first = first or FIRST[pos]
    n = N_ROWS[pos] if n is None else n
    rows = [first] + [[c if i not in (1,) else f"Player {pos}{k}" for i, c in enumerate(first)]
                      for k in range(n - 1)]
    th = "".join(f"<th>{h}</th>" for h in headers)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    sidebar = ('<table id="neorazzstatstable" class="tablesorter"><tr><th>#</th><th>Name</th><th>Team</th>'
               '<th>Pos</th><th>PTS/G</th></tr><tr><td></td><td>Sidebar Guy</td><td>KC</td><td>WR</td>'
               '<td>2.7</td></tr></table>')
    # Razzball (2026-09-21) appended an overall #/Name/Team/Pos/PTS/G table that
    # is larger than the position table and has no PPG legs; it must never win.
    overall = ""
    if overall_rows:
        overall = ('<table id="overall"><tr><th>#</th><th>Name</th><th>Team</th><th>Pos</th>'
                   '<th>PTS</th><th>PTS/G</th></tr>'
                   + "".join(f"<tr><td>{k}</td><td>Overall Guy {k}</td><td>KC</td><td>WR</td>"
                             f"<td>1</td><td>1.0</td></tr>" for k in range(overall_rows))
                   + "</table>")
    pad = "<!-- " + "x" * 20000 + " -->"
    return (f'<html><div>{stamp}</div><table><tr><td>nav</td></tr></table>'
            f'<table id="neorazzstatstable" class="tablesorter" style="font-size:8pt;">'
            f'<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>{overall}{sidebar}{pad}</html>')


def fetcher(pages):
    def f(url):
        for pos in rz.POSITIONS:
            if f"-{pos.lower()}-" in url:
                return pages.get(pos, (200, page(pos)))
        return 404, ""
    return f


class PullerTest(unittest.TestCase):
    def test_real_layouts_parse_to_stored_shape(self):
        snap = rz.pull("2026-10-06", fetch_fn=fetcher({}))
        self.assertEqual(snap["summary"]["by_pos"], N_ROWS)
        self.assertEqual(snap["review_count"], 0)
        self.assertNotIn("Sidebar Guy", {r["player_name"] for r in snap["rows"]})
        by = {r["player_name"]: r for r in snap["rows"]}
        allen, gibbs, bowers = by["Josh Allen"], by["Jahmyr Gibbs"], by["Brock Bowers"]
        self.assertEqual((allen["rz_std_ppg"], allen["rz_half_ppr_ppg"], allen["rz_ppr_ppg"]), (21.5, 21.5, 21.5))
        self.assertEqual(allen["pg_att"], round(382 / 13, 4))
        self.assertEqual(allen["pg_fum"], round(1.7 / 13, 4))
        self.assertEqual(allen["share_rush"], 0)
        self.assertEqual((gibbs["rz_std_ppg"], gibbs["rz_half_ppr_ppg"], gibbs["rz_ppr_ppg"]), (19.7, 22.0, 24.2))
        self.assertEqual(gibbs["pg_rush_att"], round(245 / 13, 4))
        self.assertEqual(gibbs["share_rush"], 78.1)
        self.assertEqual(bowers["pg_fum"], round(0.3 / 13, 4))  # Fum Lost, not Fum
        self.assertEqual(gibbs["player_norm"], "jahmyr gibbs")
        # The saver turns each row into exactly the stored raw_stats key set.
        for row in (allen, gibbs, bowers, by["Puka Nacua"]):
            raw = {k for k in row if k not in saver.PER_GAME_FIELDS
                   and k not in saver.IDENTITY_FIELDS and k not in saver.COLUMN_FIELDS}
            self.assertEqual(STORED_RAW_STATS_KEYS, raw)

    def test_non_200_fails_closed_as_source_blocked(self):
        for status in (402, 403, 429, None):
            with self.assertRaises(rz.PullError) as cm:
                rz.pull("2026-10-06", fetch_fn=fetcher({"WR": (status, "blocked")}))
            self.assertEqual("SOURCE_BLOCKED", cm.exception.code, status)

    def test_empty_200_is_source_blocked(self):
        # Razzball answers a request without browser headers with an empty 200.
        with self.assertRaises(rz.PullError) as cm:
            rz.pull("2026-10-06", fetch_fn=fetcher({"QB": (200, "")}))
        self.assertEqual("SOURCE_BLOCKED", cm.exception.code)

    def test_vintage_is_the_page_stamp_not_the_run_date(self):
        snap = rz.pull(None, fetch_fn=fetcher({}))
        self.assertEqual("2026-10-05", snap["vintage_date"])
        self.assertEqual({"2026-10-05"}, {r["razzball_snapshot_date"] for r in snap["rows"]})
        # the OLDEST page bounds the freshness
        old = page("TE", stamp="Updated: 2026-10-02 08:00:00 AM EDT")
        snap = rz.pull(None, fetch_fn=fetcher({"TE": (200, old)}))
        self.assertEqual("2026-10-02", snap["vintage_date"])

    def test_missing_stamp_fails_closed(self):
        with self.assertRaises(rz.PullError) as cm:
            rz.pull(None, fetch_fn=fetcher({"RB": (200, page("RB", stamp=""))}))
        self.assertEqual("SOURCE_LAYOUT", cm.exception.code)

    def test_overall_table_never_beats_the_ppg_table(self):
        snap = rz.pull("2026-10-06", fetch_fn=fetcher({"QB": (200, page("QB", overall_rows=300))}))
        self.assertEqual(N_ROWS["QB"], snap["summary"]["by_pos"]["QB"])
        self.assertNotIn("Overall Guy 1", {r["player_name"] for r in snap["rows"]})

    def test_ppg_gate_catches_shifted_columns(self):
        shifted = list(FIRST["RB"])
        shifted[9], shifted[10] = shifted[10], shifted[9]  # Rush Yds <-> Yds/Rush
        pages = {"RB": (200, page("RB", first=shifted))}
        with self.assertRaises(rz.PullError) as cm:
            rz.pull("2026-10-06", fetch_fn=fetcher(pages))
        self.assertEqual("PPG_GATE", cm.exception.code)

    def test_broken_state_without_ppg_gate_accepts_shifted_columns(self):
        shifted = list(FIRST["RB"])
        shifted[9], shifted[10] = shifted[10], shifted[9]
        orig = rz.PPG_MAX_BAD
        rz.PPG_MAX_BAD = (10**6, 1.0)
        try:
            snap = rz.pull("2026-10-06", fetch_fn=fetcher({"RB": (200, page("RB", first=shifted))}))
        finally:
            rz.PPG_MAX_BAD = orig
        self.assertEqual(N_ROWS["RB"], snap["summary"]["by_pos"]["RB"])  # what the gate rejects

    def test_csv_is_muse_schema(self):
        muse_header = (ROOT / "data/inputs/razzball_projections.csv").open(encoding="utf-8").readline().strip()
        self.assertEqual(muse_header, ",".join(rz.CSV_COLUMNS))
        snap = rz.pull("2026-10-06", fetch_fn=fetcher({}))
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "r.csv"
            rz.write_csv(snap, out)
            rows = list(csv.DictReader(out.open(encoding="utf-8")))
        self.assertEqual(snap["row_count"], len(rows))
        allen = next(r for r in rows if r["player"] == "Josh Allen")
        self.assertEqual(("josh allen", "QB", "BUF", "21.5", "21.5", "21.5", "2026-10-06"),
                         (allen["player_norm"], allen["pos"], allen["team"], allen["rz_std_ppg"],
                          allen["rz_half_ppr_ppg"], allen["rz_ppr_ppg"], allen["razzball_snapshot_date"]))

    def test_layout_change_fails_closed(self):
        hdr = [h if h != "PPR PPG" else "PPR FPG" for h in LAYOUTS["RB"]]
        with self.assertRaises(rz.PullError):
            rz.pull("2026-10-06", fetch_fn=fetcher({"RB": (200, page("RB", headers=hdr))}))

    def test_truncated_table_fails_closed(self):
        with self.assertRaises(rz.PullError):
            rz.pull("2026-10-06", fetch_fn=fetcher({"TE": (200, page("TE", n=12))}))

    def test_broken_state_without_row_floor_accepts_truncation(self):
        # Simulated regression: floors removed -> the truncated pull "succeeds".
        orig, orig_total = dict(rz.ROW_FLOORS), rz.TOTAL_FLOOR
        rz.ROW_FLOORS.update({p: 0 for p in rz.ROW_FLOORS})
        rz.TOTAL_FLOOR = 0
        try:
            snap = rz.pull("2026-10-06", fetch_fn=fetcher({"TE": (200, page("TE", n=12))}))
        finally:
            rz.ROW_FLOORS.update(orig)
            rz.TOTAL_FLOOR = orig_total
        self.assertEqual(snap["summary"]["by_pos"]["TE"], 12)  # what the floor test rejects

    def test_non_numeric_ppg_is_reviewed_not_zero_filled(self):
        clean, review = rz.build_rows("RB", LAYOUTS["RB"], [FIRST["RB"][:-1] + ["-"]], "2026-10-06")
        self.assertEqual(clean, [])
        self.assertEqual(review[0]["reason"], "missing_or_non_numeric_ppg")


def render(script, ctx):
    return re.sub(r"\$\{\{\s*([^}]+?)\s*\}\}", lambda m: ctx.get(m.group(1).strip(), ""), script)


def python_calls(text, ref_name, inputs=None):
    inputs = inputs or {}
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out = td / "out.txt"
        out.write_text("")
        ctx = {"github.event.inputs.mode": inputs.get("mode", "")}
        (td / "bin").mkdir()
        fake = td / "bin" / "python3"
        fake.write_text(f'#!/bin/bash\necho "$@" >> {td}/calls\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = {"PATH": f"{td / 'bin'}:/usr/bin:/bin", "HOME": str(td),
               "GITHUB_REF_NAME": ref_name, "GITHUB_OUTPUT": str(out)}
        r = subprocess.run(["bash", "-e", "-c", render(script_of(find_step(text, "Resolve mode")), ctx)],
                           cwd=td, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        outs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").split() if "=" in line)
        ctx["steps.cfg.outputs.mode"] = outs["mode"]
        r = subprocess.run(["bash", "-e", "-c", render(script_of(find_step(text, "Scrape and save")), ctx)],
                           cwd=td, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr + r.stdout
        return [line.split() for line in (td / "calls").read_text(encoding="utf-8").splitlines()]


def error_code_for(text, pull_stderr):
    """Run the real 'Scrape and save' script with a puller that fails with
    `pull_stderr`; return the error_code it publishes (and its exit code)."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        out = td / "out.txt"
        out.write_text("")
        (td / "bin").mkdir()
        fake = td / "bin" / "python3"
        fake.write_text(f"#!/bin/bash\necho '{pull_stderr}' >&2\nexit 1\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = {"PATH": f"{td / 'bin'}:/usr/bin:/bin", "HOME": str(td), "GITHUB_OUTPUT": str(out)}
        ctx = {"steps.cfg.outputs.mode": "dry"}
        r = subprocess.run(["bash", "-e", "-c", render(script_of(find_step(text, "Scrape and save")), ctx)],
                           cwd=td, env=env, capture_output=True, text=True)
        outs = dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").split() if "=" in line)
        return outs.get("error_code"), r.returncode, r.stdout


def saver_call(calls):
    return next(c for c in calls if c[0] == "pipelines/save_razzball_references.py")


def static_problems(text):
    problems = []
    if re.search(r"^\s*schedule:\s*$", text, re.M):
        problems.append("GitHub schedule present: pg_cron must be the only scheduler owner")
    block = find_step(text, RECORD)
    if block is None or RECORD_IF not in block:
        problems.append("monitored check must be recorded only in write mode")
    return problems


class WorkflowTest(unittest.TestCase):
    def test_real_workflow(self):
        self.assertEqual([], static_problems(WORKFLOW))
        for ref, inputs in (("razzball/dry-1", {}), ("main", {}), ("main", {"mode": "dry"}),
                            ("main", {"mode": "Write"})):
            calls = python_calls(WORKFLOW, ref, inputs)
            self.assertEqual("pipelines/pull_razzball_ros.py", calls[0][0])
            self.assertIn("--dry-run", saver_call(calls), (ref, inputs))
        for ref, inputs in (("razzball/write-1", {}), ("main", {"mode": "write"})):
            self.assertNotIn("--dry-run", saver_call(python_calls(WORKFLOW, ref, inputs)))

    def test_a_github_schedule_is_caught(self):
        mutated = WORKFLOW.replace("on:\n  workflow_dispatch:",
                                   'on:\n  schedule:\n    - cron: "20 11 * * *"\n  workflow_dispatch:', 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertTrue(any("schedule" in p for p in static_problems(mutated)))

    def test_dropping_the_dry_run_flag_is_caught(self):
        mutated = WORKFLOW.replace('|| flag="--dry-run"', '|| flag=""', 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertNotIn("--dry-run", saver_call(python_calls(mutated, "razzball/dry-1")))

    def test_write_by_default_is_caught(self):
        mutated = WORKFLOW.replace("mode=dry\n", "mode=write\n", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertNotIn("--dry-run", saver_call(python_calls(mutated, "main")))

    def test_recording_in_dry_mode_is_caught(self):
        mutated = WORKFLOW.replace(" && " + RECORD_IF, "", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertIn("monitored check must be recorded only in write mode", static_problems(mutated))

    def test_named_error_codes_reach_the_monitored_check(self):
        for code in ("SOURCE_BLOCKED", "SOURCE_LAYOUT", "SOURCE_TRUNCATED", "PPG_GATE"):
            got, rc, out = error_code_for(WORKFLOW, f"RAZZBALL PULL FAILED [{code}]: boom")
            self.assertEqual((code, 1), (got, rc))
            self.assertIn("::error title=razzball rc=1::", out)  # annotation the CI proof reads
        got, _, _ = error_code_for(WORKFLOW, "some saver crash")
        self.assertEqual("SYNC_FAILED", got)

    def test_dropping_the_code_extraction_is_caught(self):
        mutated = WORKFLOW.replace('[ -n "$pulled" ] && code=$pulled', ":", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        got, _, _ = error_code_for(mutated, "RAZZBALL PULL FAILED [SOURCE_BLOCKED]: boom")
        self.assertNotEqual("SOURCE_BLOCKED", got)

    def test_migration(self):
        self.assertIn("'razzball-sync-live'", MIGRATION)
        self.assertIn("dispatch_gha_workflow('razzball-supabase-sync.yml', '{\"mode\": \"write\"}'::jsonb)", MIGRATION)
        self.assertIn('"p_check_id": "razzball_projections_sync"', WORKFLOW)
        self.assertIn("'razzball_projections_sync'", MIGRATION)


if __name__ == "__main__":
    unittest.main()
