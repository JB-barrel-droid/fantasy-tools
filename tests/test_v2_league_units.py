"""League workspace units (JEG-1021): workspace store, team summary, table sort, trade opportunities.

The checks live in tests/league_harness.cjs (pure Node, no browser) and run against the frozen fixture leagues in
tests/fixtures/league/ (2, 4, 20 teams and a partial league). Every guard is proven: test_checks_fail_on_broken_builds copies the
modules, breaks one rule at a time, and requires the harness to name the check that catches it.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "v2"
HARNESS = ROOT / "tests" / "league_harness.cjs"
FIXTURES = ROOT / "tests" / "fixtures" / "league"
MODULES = ["workspace.js", "table-sort.js", "team-summary.js", "opportunities.js", "finder.js"]

REQUIRED = [
    "test_workspace_create", "test_workspace_corrupt", "test_workspace_versioned", "test_team_add_remove", "test_team_reorder", "test_clear_league",
    "test_share_link_encode", "test_share_link_decode", "test_export_import", "test_store_my_roster", "test_store_status_and_debounce",
    "test_sort_core", "test_summary_roster_value", "test_summary_ranks_fund", "test_summary_ranks_market", "test_summary_ranks_dense",
    "test_summary_strengths", "test_summary_weaknesses", "test_summary_undervalued", "test_summary_overvalued", "test_summary_gap_noise",
    "test_summary_1_team", "test_summary_2team_equals_20team", "test_summary_partial", "test_summary_k_def_counted",
    "test_summary_headline_independent_of_sort", "test_sort_numeric_asc_desc", "test_sort_blanks_last", "test_sort_rank_unchanged",
    "test_sort_tiebreak", "test_opportunities_columns", "test_opportunities_fit_label", "test_opportunities_fit_label_rows",
    "test_opportunities_rank", "test_opportunities_tier_before_edge", "test_opportunities_1_opponent", "test_opportunities_partial",
    "test_multi_trade_cache", "test_opportunities_filters", "test_opportunities_cap_and_headline",
    "test_summary_ranks_proj", "test_summary_disagree_list", "test_summary_allocation_wording", "test_summary_proj_partial", "test_summary_disagree_charts_key", "test_opportunities_proj_agreement",
]


def run_harness(modules_dir: Path) -> dict:
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", str(HARNESS), str(modules_dir), str(FIXTURES)], capture_output=True, text=True, timeout=300)
    if out.returncode != 0:
        raise AssertionError(f"harness crashed: {out.stderr[-1500:]}")
    return json.loads(out.stdout)


def mutated(changes: dict[str, tuple[str, str]]):
    """A temp dir with the modules, one source file edited. changes: {file: (old, new)}; a stale anchor fails loudly."""
    tmp = tempfile.TemporaryDirectory()
    for name in MODULES:
        shutil.copy2(APP / name, Path(tmp.name) / name)
    for name, (old, new) in changes.items():
        path = Path(tmp.name) / name
        text = path.read_text(encoding="utf-8")
        if old not in text:
            tmp.cleanup()
            raise AssertionError(f"mutation anchor is stale in {name}: {old[:70]!r}")
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
    return tmp


# name -> (file, old, new, the checks that must fail)
MUTATIONS = {
    "strength rule inverted (below the median counts)": ("team-summary.js", "const valueLow = med !== null && shown(sum) < shown(med);",
        "const valueLow = med !== null && shown(sum) > shown(med);", {"test_summary_strengths", "test_summary_weaknesses"}),
    "noise floor 1.0 instead of 2.0": ("team-summary.js", "const NOISE_FLOOR = 2.0;", "const NOISE_FLOOR = 1.0;", {"test_summary_gap_noise"}),
    "ranks skip numbers after a tie": ("team-summary.js", "items.forEach(i => out.set(i.id, distinct.indexOf(shown(valueOf(i))) + 1));",
        "items.forEach(i => out.set(i.id, items.filter(j => shown(valueOf(j)) > shown(valueOf(i))).length + 1));", {"test_summary_ranks_dense"}),
    "roster value is the starters only": ("team-summary.js", "rosterValue: lineup.total,", "rosterValue: lineup.starterValue,", {"test_summary_roster_value"}),
    "a player listed as both under and over": ("team-summary.js", "else if (gap < -floor) over.push(item);",
        "if (Math.abs(gap) > floor) over.push(item);", {"test_summary_overvalued"}),
    "disagreement floor 1.0 instead of 2.0": ("team-summary.js", "const DISAGREE_FLOOR = 2.0;", "const DISAGREE_FLOOR = 1.0;", {"test_summary_disagree_list"}),
    "projections view built from any one projected player": ("team-summary.js", "rows.filter(r => POSITIONS.includes(r.pos)).every(r => r.values && finite(r.values[PROJ_KEY]))", "rows.some(r => r.values && finite(r.values[PROJ_KEY]))", {"test_summary_proj_partial"}),
    "disagreement reads DDF Value instead of the charts": ("team-summary.js", "const charts = finite(v[CHARTS_KEY]) ? v[CHARTS_KEY] : v[OUR_KEY];", "const charts = v[OUR_KEY];", {"test_summary_disagree_charts_key"}),
    "disagreement column sorts unsigned": ("team-summary.js", "list.slice().sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))[0].gap", "Math.abs(list.slice().sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))[0].gap)", {"test_summary_disagree_charts_key"}),
    "projections edge direction flipped": ("opportunities.js", "const projEdge = projGive !== null && projRecv !== null ? projRecv - projGive : null;", "const projEdge = projGive !== null && projRecv !== null ? projGive - projRecv : null;", {"test_opportunities_proj_agreement"}),
    "level counts as agreement": ("opportunities.js", "if (projEdge >= 0.05) return true;", "if (projEdge >= 0) return true;", {"test_opportunities_proj_agreement"}),
    "a missing projection counts as 0": ("opportunities.js", "const sumAll = (list, key) => list.reduce((n, r) => (n === null || !r.values || !finite(r.values[key]) ? null : n + r.values[key]), 0);", "const sumAll = (list, key) => list.reduce((n, r) => n + (r.values && finite(r.values[key]) ? r.values[key] : 0), 0);", {"test_opportunities_proj_agreement"}),
    "disagreement sign inverted": ("team-summary.js", "const gap = proj - charts;", "const gap = charts - proj;", {"test_summary_disagree_list"}),
    "projections rank taken from the DDF value": ("team-summary.js", "const pr = denseRanks(projTeams, r => r.proj.rosterValue);", "const pr = denseRanks(projTeams, r => r.fund.rosterValue);", {"test_summary_ranks_proj"}),
    "allocation wording dropped": ("team-summary.js", "`${pos} allocation ${med !== null ? \"above the league median\" : \"at or above the expected depth\"} (", "`${pos} (", {"test_summary_allocation_wording"}),
    "market rank taken from the DDF value": ("team-summary.js", "const m = denseRanks(marketTeams, r => r.market.rosterValue);",
        "const m = denseRanks(marketTeams, r => r.fund.rosterValue);", {"test_summary_ranks_market"}),
    "blank values sort first when descending": ("table-sort.js", "return ab === bb ? chain(a, b) : ab ? 1 : -1;   // blanks last",
        "return ab === bb ? chain(a, b) : (ab ? 1 : -1) * sign;   // blanks last", {"test_sort_core", "test_sort_blanks_last", "test_sort_numeric_asc_desc"}),
    "sort direction reversed": ("table-sort.js", 'const sign = state.dir === "desc" ? -1 : 1;', 'const sign = state.dir === "desc" ? 1 : -1;', {"test_sort_core", "test_sort_numeric_asc_desc"}),
    "tie-break chain flips with the direction": ("table-sort.js", "const c = compareValues(x, y, tie.type || \"number\") * (tie.dir === \"desc\" ? -1 : 1);",
        "const c = compareValues(x, y, tie.type || \"number\") * (tie.dir === \"desc\" ? -1 : 1) * sign;", {"test_sort_tiebreak", "test_sort_core"}),
    "fit tier ignored in the ranking": ("opportunities.js", "return a.tier - b.tier || shown(b.edge)", "return shown(b.edge)", {"test_opportunities_rank", "test_opportunities_tier_before_edge"}),
    "overall fit ignores the finder's label": ("opportunities.js", "if (fit && fit.label) return fit.label;", 'if (fit && fit.label) return "natural";', {"test_opportunities_fit_label", "test_opportunities_fit_label_rows"}),
    "cache ignores the values": ("opportunities.js", 'const rowSig = r => `${r.player_key}:${[OUR_KEY, "ddf_value_projections"].concat(["usatoday", "fantasycalc", "fantasypros", "cbs"]).map(k => (r.values && finite(r.values[k]) ? r.values[k].toFixed(3) : "-")).join(",")}:${r.pos}`;',
        'const rowSig = r => `${r.player_key}:${r.pos}`;', {"test_multi_trade_cache"}),
    "capture is not the finder edge": ("opportunities.js", "edge: t.edge, edgePct", "edge: t.edge + 0.7, edgePct", {"test_opportunities_1_opponent"}),
    "opponents not capped": ("opportunities.js", "const run = eligible.slice(0, MAX_OPPONENTS);", "const run = eligible;", {"test_opportunities_cap_and_headline"}),
    "a rename recomputes the pairing": ("opportunities.js", "const key = `${mineSig}#${sigOf(rowsFor(opp.entries, ctx.rowsByKey))}#${cSig}`;",
        "const key = `${mineSig}#${sigOf(rowsFor(opp.entries, ctx.rowsByKey))}#${cSig}#${opp.name}`;", {"test_multi_trade_cache"}),
    "corrupt storage read as empty": ("workspace.js", 'try { data = JSON.parse(text); } catch (error) { return {status: "corrupt", workspace: null}; }',
        'try { data = JSON.parse(text); } catch (error) { return {status: "empty", workspace: null}; }', {"test_workspace_corrupt"}),
    "unknown storage version accepted": ("workspace.js", 'if (data.v !== VERSION) return {status: "version", workspace: null};', "", {"test_workspace_versioned"}),
    "removing my team keeps the mark": ("workspace.js", "myTeamId: ws.myTeamId === id ? null : ws.myTeamId});", "myTeamId: ws.myTeamId});", {"test_team_add_remove"}),
    "clearing the league keeps my team's mark": ("workspace.js", "touch({...ws, teams: [], myTeamId: null})", "touch({...ws, teams: []})", {"test_clear_league"}),
    "reorder swaps the wrong way": ("workspace.js", "[teams[from], teams[to]] = [teams[to], teams[from]];", "[teams[from], teams[to]] = [teams[from], teams[to]];", {"test_team_reorder"}),
    "my-roster listeners fire on every change": ("workspace.js", "if (was !== now || before.myTeamId !== ws.myTeamId) mineListeners",
        "if (true) mineListeners", {"test_store_my_roster"}),
    "oversized share link not trimmed": ("workspace.js", "if (full.length <= SHARE_LIMIT) return", "if (true) return", {"test_share_link_encode"}),
    "import accepts a file with no teams": ("workspace.js", "if (!isObject(data) || !data.id || !data.name || !Array.isArray(data.teams))", "if (!isObject(data))", {"test_export_import"}),
}


class LeagueUnitTest(unittest.TestCase):
    def test_all_checks_pass_on_the_real_modules(self):
        result = run_harness(APP)
        self.assertEqual(result["failures"], [])
        self.assertFalse(set(REQUIRED) - set(result["ran"]), f"checks missing from the harness: {sorted(set(REQUIRED) - set(result['ran']))}")

    def test_checks_fail_on_broken_builds(self):
        for name, (file, old, new, expect) in MUTATIONS.items():
            with self.subTest(mutation=name):
                tmp = mutated({file: (old, new)})
                try:
                    failed = {f["name"] for f in run_harness(Path(tmp.name))["failures"]}
                finally:
                    tmp.cleanup()
                self.assertTrue(failed & expect, f"not caught: {name} (failed: {sorted(failed)})")


if __name__ == "__main__":
    unittest.main()
