"""JEG-207 review fix: the Option C group-VORP loader must read the real
JEG-206 artifact and fail closed -- never invent placeholder values.

Regression: the first JEG-207 build looked for `data/ddf-group-vorps.json`
(a path JEG-206 never writes) and expected `{"groups": {"QB|Starter": f}}`
(a shape JEG-206 never emits). Both misses silently fell through to
invented placeholder numbers that flowed into alloc_factor and
imputed_vorp on the dashboard. This test pins the real contract:
dist/modules/ddf-group-vorps.json with JEG-206's list shape, and
({}, False) for every malformed variant -- the value columns then emit
nulls, never guesses.
"""
import importlib.util
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_source_value_lineage",
        REPO / "pipelines" / "build_source_value_lineage.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _jeg206_doc(totals):
    return {
        "schema": "trade-value-ddf-groups-v1",
        "groups": [
            {"position": pos, "role": role, "total_vorp": totals[f"{pos}|{role.capitalize()}"],
             "n_players": 10}
            for pos in ("QB", "RB", "WR", "TE") for role in ("starter", "bench")
        ],
    }


class GroupVorpLoaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()
        cls.totals = {
            "QB|Starter": 148.84, "QB|Bench": 26.27,
            "RB|Starter": 995.91, "RB|Bench": 175.75,
            "WR|Starter": 975.04, "WR|Bench": 172.07,
            "TE|Starter": 145.73, "TE|Bench": 23.38,
        }

    def _run_with_repo(self, repo_path):
        real_repo = self.b.REPO
        self.b.REPO = str(repo_path)
        try:
            return self.b._load_ddf_group_vorps()
        finally:
            self.b.REPO = real_repo

    def _write_artifact(self, tmp, doc):
        d = Path(tmp) / "dist" / "modules"
        d.mkdir(parents=True)
        (d / "ddf-group-vorps.json").write_text(json.dumps(doc))

    def test_reads_real_jeg206_shape(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._write_artifact(tmp, _jeg206_doc(self.totals))
            got, available = self._run_with_repo(tmp)
        self.assertTrue(available)
        self.assertEqual(got, self.totals)

    def test_missing_file_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            got, available = self._run_with_repo(tmp)
        self.assertFalse(available)
        self.assertEqual(got, {})

    def test_old_dict_shape_rejected(self):
        # The first JEG-207 build expected {"groups": {"QB|Starter": f}};
        # JEG-206 emits a list. A dict-shaped file must not parse.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            self._write_artifact(tmp, {"groups": dict(self.totals)})
            got, available = self._run_with_repo(tmp)
        self.assertFalse(available)
        self.assertEqual(got, {})

    def test_partial_groups_rejected(self):
        import tempfile
        doc = _jeg206_doc(self.totals)
        doc["groups"] = doc["groups"][:7]  # drop TE|Bench
        with tempfile.TemporaryDirectory() as tmp:
            self._write_artifact(tmp, doc)
            got, available = self._run_with_repo(tmp)
        self.assertFalse(available)
        self.assertEqual(got, {})

    def test_non_numeric_value_rejected(self):
        import tempfile
        doc = _jeg206_doc(self.totals)
        doc["groups"][0]["total_vorp"] = "many"
        with tempfile.TemporaryDirectory() as tmp:
            self._write_artifact(tmp, doc)
            got, available = self._run_with_repo(tmp)
        self.assertFalse(available)
        self.assertEqual(got, {})

    def test_wrong_path_never_read(self):
        # JEG-206 never writes data/ddf-group-vorps.json; a file there
        # must be ignored even if it carries plausible numbers.
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "data"
            d.mkdir(parents=True)
            (d / "ddf-group-vorps.json").write_text(
                json.dumps(_jeg206_doc(self.totals)))
            got, available = self._run_with_repo(tmp)
        self.assertFalse(available)
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main()
