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
    truncated table (row floor); it reads the stats table, not the sidebar;
  - every failure carries a named code (SOURCE_BLOCKED, SOURCE_HTTP_ERROR,
    SCHEMA_CHANGED, TRUNCATED, PPG_INCONSISTENT) that the workflow records as
    the monitored check's error_code;
  - the table is the one with Name + STD PPG, never the largest by rows (Muse's
    2026-09-21 overall PTS/G table); the PPG gate rejects a misaligned parse.
"""
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

WORKFLOW = (ROOT / ".github/workflows/razzball-supabase-sync.yml").read_text()
MIGRATION = (ROOT / "supabase/migrations/razzball_sync_pg_cron.sql").read_text()
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


def page(pos, n=None, headers=None, first=None):
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
    return (f'<html><table><tr><td>nav</td></tr></table>'
            f'<table id="neorazzstatstable" class="tablesorter" style="font-size:8pt;">'
            f'<thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>{sidebar}</html>')


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

    def test_non_200_fails_closed(self):
        with self.assertRaises(rz.PullError):
            rz.pull("2026-10-06", fetch_fn=fetcher({"WR": (403, "blocked")}))

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


def overall_table(n):
    """Razzball's 2026-09-21 addition: a larger #/Name/Team/Pos/PTS/G table."""
    rows = "".join(f"<tr><td>{i}</td><td>Overall {i}</td><td>KC</td><td>WR</td><td>1.0</td></tr>"
                   for i in range(n))
    return ('<table><thead><tr><th>#</th><th>Name</th><th>Team</th><th>Pos</th><th>PTS/G</th></tr>'
            f'</thead><tbody>{rows}</tbody></table>')


def swapped_qb_row():
    row = list(FIRST["QB"])
    i, j = LAYOUTS["QB"].index("Pass Yds"), LAYOUTS["QB"].index("Pass TD")
    row[i], row[j] = row[j], row[i]
    return row


class ErrorCodeTest(unittest.TestCase):
    def code(self, pages):
        with self.assertRaises(rz.PullError) as cm:
            rz.pull("2026-10-06", fetch_fn=fetcher(pages))
        return cm.exception.code

    def test_bot_wall_statuses_are_named_source_blocked(self):
        for status in (402, 403, 429):
            self.assertEqual("SOURCE_BLOCKED", self.code({"QB": (status, "denied")}), status)
        self.assertEqual("SOURCE_BLOCKED", self.code({"QB": (None, "curl exception")}))

    def test_empty_200_and_short_wall_page_are_source_blocked(self):
        self.assertEqual("SOURCE_BLOCKED", self.code({"RB": (200, "")}))
        self.assertEqual("SOURCE_BLOCKED", self.code({"RB": (200, "<html>Just a moment...</html>")}))

    def test_other_status_and_layout_and_floor_codes(self):
        self.assertEqual("SOURCE_HTTP_ERROR", self.code({"WR": (503, "down")}))
        hdr = [h if h != "PPR PPG" else "PPR FPG" for h in LAYOUTS["RB"]]
        self.assertEqual("SCHEMA_CHANGED", self.code({"RB": (200, page("RB", headers=hdr))}))
        self.assertEqual("TRUNCATED", self.code({"TE": (200, page("TE", n=12))}))

    def test_large_page_without_stats_table_is_schema_changed_not_blocked(self):
        big = "<html>" + "x" * 60000 + "</html>"
        self.assertEqual("SCHEMA_CHANGED", self.code({"QB": (200, big)}))

    def test_workflow_records_the_puller_code(self):
        step = script_of(find_step(WORKFLOW, "Scrape and save"))
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "razzball.log"
            log.write_text("RAZZBALL PULL FAILED [SOURCE_BLOCKED]: QB: status=403\n")
            lines = step.splitlines()
            a = next(i for i, ln in enumerate(lines) if ln.strip() == "code=SYNC_FAILED")
            b = next(i for i, ln in enumerate(lines) if ln.lstrip().startswith("[ -z"))
            snippet = "\n".join(lines[a:b + 1]).replace("/tmp/razzball.log", str(log))
            r = subprocess.run(["bash", "-c", snippet + '\necho "$code"'], capture_output=True, text=True)
            self.assertEqual("SOURCE_BLOCKED", r.stdout.strip(), r.stderr)
        self.assertIn("p_error_code", WORKFLOW)
        self.assertIn('ERROR_CODE: ${{ steps.sync.outputs.error_code }}', WORKFLOW)


class TableAndGateTest(unittest.TestCase):
    def test_overall_table_never_wins_on_row_count(self):
        qb = page("QB").replace("</html>", overall_table(500) + "</html>")
        snap = rz.pull("2026-10-06", fetch_fn=fetcher({"QB": (200, qb)}))
        self.assertEqual(snap["summary"]["by_pos"]["QB"], N_ROWS["QB"])
        self.assertNotIn("Overall 1", {r["player_name"] for r in snap["rows"]})

    def test_broken_picker_largest_by_rows_would_take_the_wrong_table(self):
        # Simulated regression: pick by Name + row count only (no STD PPG rule).
        qb = page("QB").replace("</html>", overall_table(500) + "</html>")
        wrong = max((t for t in rz.parse_tables(qb) if "Name" in t[0]), key=lambda t: len(t[1]))
        self.assertNotIn("STD PPG", wrong[0])  # the table the real rule refuses
        self.assertIn("STD PPG", rz.parse_table(qb)[0])

    def test_misaligned_columns_fail_the_ppg_gate(self):
        with self.assertRaises(rz.PullError) as cm:
            rz.pull("2026-10-06", fetch_fn=fetcher({"QB": (200, page("QB", first=swapped_qb_row()))}))
        self.assertEqual("PPG_INCONSISTENT", cm.exception.code)

    def test_broken_state_without_ppg_gate_accepts_misaligned_columns(self):
        orig = rz.ppg_gate
        rz.ppg_gate = lambda rows: []
        try:
            snap = rz.pull("2026-10-06", fetch_fn=fetcher({"QB": (200, page("QB", first=swapped_qb_row()))}))
        finally:
            rz.ppg_gate = orig
        self.assertEqual(snap["summary"]["by_pos"]["QB"], N_ROWS["QB"])  # what the gate rejects

    def test_real_layouts_pass_the_gate_and_stamp_is_recorded(self):
        stamped = page("QB").replace("<html>", "<html>Updated 2026-10-06 08:15:00 AM EDT ", 1)
        snap = rz.pull("2026-10-07", fetch_fn=fetcher({"QB": (200, stamped)}))
        self.assertEqual([], snap["summary"]["ppg_outliers"])
        self.assertEqual("2026-10-06 08:15:00 AM EDT", snap["page_stamps"]["QB"])
        self.assertEqual("unknown", snap["page_stamps"]["RB"])
        self.assertEqual("2026-10-07", snap["vintage_date"])


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
        outs = dict(line.split("=", 1) for line in out.read_text().split() if "=" in line)
        ctx["steps.cfg.outputs.mode"] = outs["mode"]
        r = subprocess.run(["bash", "-e", "-c", render(script_of(find_step(text, "Scrape and save")), ctx)],
                           cwd=td, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr + r.stdout
        return [line.split() for line in (td / "calls").read_text().splitlines()]


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

    def test_migration(self):
        self.assertIn("'razzball-sync-live'", MIGRATION)
        self.assertIn("dispatch_gha_workflow('razzball-supabase-sync.yml', '{\"mode\": \"write\"}'::jsonb)", MIGRATION)
        self.assertIn('"p_check_id": "razzball_projections_sync"', WORKFLOW)
        self.assertIn("'razzball_projections_sync'", MIGRATION)


if __name__ == "__main__":
    unittest.main()
