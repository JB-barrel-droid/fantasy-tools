"""Browser port of the value-above-waivers translation == the server (JEG-332 / JEG-364).

Decision league-settings-001: the backend saves one league setup per scoring
(12 teams, standard roster); the browser derives every other team count,
roster and bench from it. That only holds if the browser runs the SAME
arithmetic as pipelines/vorp_translation/unified.py. This test runs both on
identical inputs and requires equality:

  * counts, waiver methods, rounded values: EXACTLY equal (tolerance 0);
  * any unrounded float: within TOL = 1e-9 (there are none today -- every
    reported number is rounded on both sides -- the tolerance is a backstop).

Inputs are the saved 12-team native values of every published source
(cbs, fantasypros, usatoday, fantasycalc) x 3 scorings, run at 8/10/12/14
teams, bench 0-14, flex 0-5, non-default dedicated slots, superflex, plus
synthetic edge vectors (exact rounding ties, thin coverage, empty position).

The 12-team default must also reproduce what is SAVED in the fixture for
every source whose stored translation is current (see KNOWN_STALE_STORED).

Discrimination: test_guard_catches_broken_ports mutates a copy of
value-model.js in three realistic ways and requires this comparison to fail
on each. A parity test that cannot fail is worse than none.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))
sys.path.insert(0, str(REPO))

from pipelines.vorp_translation import unified  # noqa: E402

VALUE_MODEL = REPO / "app" / "trade-value-chart" / "assets" / "value-model.js"
DRIVER = REPO / "tests" / "vorp_translation_parity_driver.js"
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"
SOURCES = ("cbs", "fantasypros", "usatoday", "fantasycalc")
SCORINGS = ("standard", "half_ppr", "ppr")
TOL = 1e-9

# Sources whose STORED 12-team values are known not to be the current
# translation of their stored natives (risk register JEG332-STORED-DRIFT).
# For these the saved-value check reports instead of failing; JS == Python is
# still required for them like every other source.
#  - usatoday: 3 players differ by up to 1.6 and 6 more are stored as
#    translated though the stored natives put them at/below the waiver line
#    (natives refreshed after the Supabase translation was written).
#  - fantasycalc: the 2026-10-04 multi-team refresh rewrote `reindexed` with
#    the quantile pie (e.g. Brock Purdy full 10.14 vs translation 8.2) but
#    kept the old `translation: vorp-supabase` provenance block.
KNOWN_STALE_STORED = {"usatoday", "fantasycalc"}

ROSTER_SHAPES = [
    # (label, slots, flex_eligible)
    ("qb2", {"QB": 2, "RB": 2, "WR": 3, "TE": 1}, None),
    ("rb3", {"QB": 1, "RB": 3, "WR": 3, "TE": 1}, None),
    ("wr4", {"QB": 1, "RB": 2, "WR": 4, "TE": 1}, None),
    ("te2", {"QB": 1, "RB": 2, "WR": 3, "TE": 2}, None),
    ("deep", {"QB": 2, "RB": 3, "WR": 4, "TE": 2}, None),
    ("max5", {"QB": 5, "RB": 5, "WR": 5, "TE": 5}, None),
    ("superflex", None, ["QB", "RB", "WR", "TE"]),
]


def _load_ranked(source, scoring):
    ranked, key_by_name = unified.load_native_values(source, scoring, 12)
    return {pos: [(key_by_name[unified.norm_player_name(n)], n, v) for n, v in rows]
            for pos, rows in ranked.items()}


def _real_vectors():
    vectors = []
    for source in SOURCES:
        for scoring in SCORINGS:
            ranked = _load_ranked(source, scoring)
            base = {"source": source, "scoring": scoring, "ranked_keyed": ranked}
            for teams in (8, 10, 12, 14):
                for bench in (0, 3, 6, 9, 14):
                    for flex in (0, 1, 2, 5):
                        vectors.append({**base, "teams": teams, "bench_per_team": bench,
                                        "flex_count": flex, "slots": None,
                                        "flex_eligible": None})
                for label, slots, elig in ROSTER_SHAPES:
                    vectors.append({**base, "teams": teams, "bench_per_team": 6,
                                    "flex_count": 1, "slots": slots,
                                    "flex_eligible": elig, "shape": label})
    return vectors


def _synthetic_vectors():
    def keyed(pos, values):
        return [(f"{pos.lower()}{i}", f"{pos} {i}", float(v)) for i, v in enumerate(values)]
    vectors = []
    # Exact rounding ties: vorp*scale lands on x.x5 / x.25 values where
    # Python's round-half-even and JS toFixed disagree.
    tie = {"QB": keyed("QB", [26.0, 13.25, 12.75, 3.0, 2.0, 1.0] + [0.5] * 30),
           "RB": keyed("RB", [71.0, 40.25, 30.75, 20.125] + [1.0] * 60),
           "WR": keyed("WR", [56.0, 30.25, 10.75] + [1.0] * 90),
           "TE": keyed("TE", [31.0, 1.125, 0.375] + [1.0] * 20)}
    vectors.append({"label": "ties", "ranked_keyed": tie, "teams": 1,
                    "bench_per_team": 0, "flex_count": 0, "slots": None, "flex_eligible": None})
    # Thin coverage: fewer players than rostered -> insufficient_coverage.
    thin = {"QB": keyed("QB", [30, 20, 10]), "RB": keyed("RB", [60, 50, 40, 30]),
            "WR": keyed("WR", [50, 45, 40, 35, 30]), "TE": keyed("TE", [20, 10])}
    vectors.append({"label": "thin", "ranked_keyed": thin, "teams": 12,
                    "bench_per_team": 6, "flex_count": 1, "slots": None, "flex_eligible": None})
    # Empty position + all-equal values (zero VORP everywhere at RB).
    empty = {"QB": [], "RB": keyed("RB", [10] * 40), "WR": keyed("WR", range(80, 0, -1)),
             "TE": keyed("TE", range(30, 0, -1))}
    vectors.append({"label": "empty", "ranked_keyed": empty, "teams": 10,
                    "bench_per_team": 6, "flex_count": 2, "slots": None, "flex_eligible": None})
    return vectors


def _python(vector):
    try:
        return unified.translate_ranked(vector["ranked_keyed"], vector["teams"],
                                        vector["bench_per_team"], vector["flex_count"],
                                        slots=vector["slots"],
                                        flex_eligible=vector["flex_eligible"])
    except (ValueError, SystemExit) as error:
        return {"error": str(error)}


def _js(vectors, model_path=VALUE_MODEL):
    payload = {"vectors": [{
        "ranked": {pos: [[k, v] for k, _n, v in rows] for pos, rows in vec["ranked_keyed"].items()},
        "teams": vec["teams"], "bench_per_team": vec["bench_per_team"],
        "flex_count": vec["flex_count"], "slots": vec["slots"],
        "flex_eligible": vec["flex_eligible"],
    } for vec in vectors]}
    proc = subprocess.run(["node", str(DRIVER), str(model_path)], input=json.dumps(payload),
                          capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise AssertionError(f"node driver failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)["results"]


def _num_diff(a, b):
    if isinstance(a, bool) or isinstance(b, bool) or isinstance(a, str) or isinstance(b, str):
        return 0.0 if a == b else float("inf")
    return abs(float(a) - float(b))


def compare(py, js):
    """Return (mismatch strings, max abs numeric diff, numbers compared)."""
    problems, max_diff, n = [], 0.0, 0
    if "error" in py or "error" in js:
        if ("error" in py) != ("error" in js):
            problems.append(f"one side raised: py={py.get('error')} js={js.get('error')}")
        return problems, max_diff, n
    if set(py["positions"]) != set(js["positions"]):
        problems.append(f"positions {sorted(py['positions'])} vs {sorted(js['positions'])}")
    for pos, pstats in py["positions"].items():
        jstats = js["positions"].get(pos, {})
        for field, pval in pstats.items():
            n += 1
            d = _num_diff(pval, jstats.get(field, "<missing>"))
            if d > 0:
                problems.append(f"{pos}.{field}: py={pval} js={jstats.get(field)}")
            if d != float("inf"):
                max_diff = max(max_diff, d)
    pkeys, jkeys = set(py["translated"]), set(js["translated"])
    if pkeys != jkeys:
        problems.append(f"translated sets differ: py-only={sorted(pkeys - jkeys)[:5]} "
                        f"js-only={sorted(jkeys - pkeys)[:5]}")
    for key in pkeys & jkeys:
        for field in ("pos", "native", "vorp", "translated"):
            n += 1
            d = _num_diff(py["translated"][key][field], js["translated"][key][field])
            if d > 0:
                problems.append(f"{key}.{field}: py={py['translated'][key][field]} "
                                f"js={js['translated'][key][field]}")
            if d != float("inf"):
                max_diff = max(max_diff, d)
    return problems, max_diff, n


def run_parity(vectors, model_path=VALUE_MODEL):
    js_results = _js(vectors, model_path)
    failures, max_diff, numbers = [], 0.0, 0
    for vec, js in zip(vectors, js_results):
        problems, d, n = compare(_python(vec), js)
        max_diff, numbers = max(max_diff, d), numbers + n
        if problems:
            label = vec.get("label") or (f"{vec['source']}/{vec['scoring']}/{vec['teams']}t/"
                                         f"b{vec['bench_per_team']}/f{vec['flex_count']}/"
                                         f"{vec.get('shape', 'std')}")
            failures.append(f"{label}: {problems[:3]}")
    return failures, max_diff, numbers, js_results


class VorpTranslationJsParity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = _real_vectors() + _synthetic_vectors()

    def test_js_equals_python_on_every_vector(self):
        failures, max_diff, numbers, js_results = run_parity(self.vectors)
        print(f"\n[JEG-332 parity] vectors={len(self.vectors)} numbers_compared={numbers} "
              f"max_abs_diff={max_diff} failures={len(failures)}")
        self.assertEqual(failures, [], "\n".join(failures[:20]))
        self.assertEqual(max_diff, 0.0)
        self.assertGreater(numbers, 100000)
        versions = {r.get("version") for r in js_results if "version" in r}
        self.assertEqual(versions, {"unified-py-jeg62/1"})
        # The synthetic tie vector really exercises the half-even branch.
        tie = next(r for v, r in zip(self.vectors, js_results) if v.get("label") == "ties")
        self.assertTrue(any(str(t["translated"]).endswith(("2", "4", "6", "8", "0"))
                            for t in tie["translated"].values()))

    def test_12_team_default_reproduces_saved_values(self):
        fixture = json.loads(FIXTURE.read_text())
        pk = fixture["player_keys"]
        vectors = [v for v in _real_vectors()
                   if v["teams"] == 12 and v["bench_per_team"] == 6
                   and v["flex_count"] == 1 and v["slots"] is None and v["flex_eligible"] is None]
        self.assertEqual(len(vectors), len(SOURCES) * len(SCORINGS))
        js_results = _js(vectors)
        exact_combos = 0
        report = []
        for vec, js in zip(vectors, js_results):
            source = vec["source"]
            combo_key = unified.resolve_combo_key(fixture["sources"][source], vec["scoring"], 12)
            combo = fixture["sources"][source]["combos"][combo_key]
            saved = combo["reindexed"]
            py = _python(vec)
            js_mis, py_mis, js_hits = set(), set(), 0
            for slug, value in saved.items():
                key = str(pk.get(slug))
                jt, pt = js["translated"].get(key), py["translated"].get(key)
                if jt is not None:
                    js_hits += 1
                    if jt["translated"] != value:
                        js_mis.add(slug)
                if (pt is not None) and pt["translated"] != value:
                    py_mis.add(slug)
            # The browser never drifts from the stored values where the server does not.
            self.assertEqual(js_mis, py_mis, f"{source}/{combo_key}")
            stored_n = (combo.get("translation") or {}).get("n_translated")
            if source in KNOWN_STALE_STORED:
                report.append(f"{source}/{combo_key}: stored-vs-recomputed differ on "
                              f"{len(js_mis)} players; stored n_translated={stored_n}, "
                              f"recomputed={js_hits} (known: JEG332-STORED-DRIFT)")
                continue
            self.assertEqual(js_mis, set(), f"{source}/{combo_key}: JS != saved for {sorted(js_mis)[:5]}")
            self.assertEqual(js_hits, stored_n, f"{source}/{combo_key}: translated count")
            exact_combos += 1
        print("\n[JEG-332 saved-value check] exact combos:", exact_combos)
        for line in report:
            print("  ", line)
        self.assertGreaterEqual(exact_combos, 6)

    def test_guard_catches_broken_ports(self):
        """Negative test: each realistic port bug must make the comparison fail."""
        source = VALUE_MODEL.read_text()
        mutations = {
            # apportion ties settled by the LAST position (Python max keeps the first)
            "apportion-tie-last": ("if (score > bestScore)", "if (score >= bestScore)"),
            # dedicated slots ignore the roster steppers
            "slots-ignored": ("var slots = opts.slots || TRANSLATION_REF_SLOTS;",
                              "var slots = TRANSLATION_REF_SLOTS;"),
            # flex weighted by raw value, forgetting the waiver estimate
            "flex-no-waiver": ("Math.max(0.0, p.value - waiver)", "Math.max(0.0, p.value)"),
            # JS toFixed rounding instead of Python round-half-even
            "round-toFixed": ("if (Number.isInteger(twice) && twice % 2 === 1) {",
                              "if (false) {"),
        }
        vectors = [v for v in self.vectors
                   if v.get("label") == "ties"
                   or (v.get("source") == "cbs" and v.get("scoring") == "ppr")]
        with tempfile.TemporaryDirectory() as tmp:
            for name, (old, new) in mutations.items():
                self.assertEqual(source.count(old), 1, f"mutation anchor for {name} moved")
                broken = Path(tmp) / f"value-model-{name}.js"
                broken.write_text(source.replace(old, new))
                failures, _d, _n, _r = run_parity(vectors, broken)
                print(f"\n[JEG-332 negative test] {name}: {len(failures)} failing vectors")
                self.assertGreater(len(failures), 0, f"mutation {name} was NOT caught")
            intact = Path(tmp) / "value-model-intact.js"
            shutil.copy(VALUE_MODEL, intact)
            self.assertEqual(run_parity(vectors, intact)[0], [])


if __name__ == "__main__":
    unittest.main()
