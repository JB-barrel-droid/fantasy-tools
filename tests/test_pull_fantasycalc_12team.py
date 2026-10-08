"""JEG-427: the CI FantasyCalc puller writes exactly the saved league setup
(12 teams, 1 QB, three scorings) in the shape save_fantasycalc_references.py
reads, and writes nothing on a partial pull.
"""
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import pull_fantasycalc_12team as P  # noqa: E402
import save_fantasycalc_references as S  # noqa: E402


def api_payload(n):
    return [{"player": {"name": f"Player {i}", "position": "WR", "maybeTeam": "SEA", "id": i},
             "value": 5000 - i} for i in range(n)]


class PullFantasyCalc12TeamTest(unittest.TestCase):
    def test_writes_the_three_files_the_saver_reads(self):
        urls = []
        with TemporaryDirectory() as tmp:
            rc = P.main(["--cache-dir", tmp, "--week", "5"],
                        fetch_fn=lambda u: (urls.append(u), api_payload(200))[1])
            self.assertEqual(0, rc)
            written = sorted(p.stem for p in Path(tmp).glob("*.json"))
            # exact contract with the saver: the three 1-QB lists plus
            # FantasyCalc's three superflex (numQbs=2) lists
            # (GAP-SUPERFLEX-PUBLISHER-VALUES; was the 1-QB three only).
            self.assertEqual(sorted({**S.FC_COMBOS, **S.FC_SUPERFLEX_COMBOS}), written)
            doc = json.loads(Path(tmp, "fantasycalc_half_12_qb1.json").read_text(encoding="utf-8"))
            self.assertEqual(200, len(doc["rows"]))
            self.assertEqual({"name", "pos", "team", "value", "fantasycalc_id"}, set(doc["rows"][0]))
            self.assertEqual(5, doc["week"])
            self.assertIsNone(doc["week_evidence"]["week_url"])
        self.assertEqual(6, len(urls))
        self.assertTrue(all("numTeams=12" in u for u in urls))
        self.assertEqual(3, sum("numQbs=1&" in u for u in urls))
        self.assertEqual(3, sum("numQbs=2&" in u for u in urls))

    def test_short_superflex_list_never_holds_the_one_qb_save(self):
        """A short numQbs=2 list (outage shape) skips the superflex lists and
        still writes the three 1-QB lists (superflex is never a stop)."""
        with TemporaryDirectory() as tmp:
            rc = P.main(["--cache-dir", tmp, "--week", "5"],
                        fetch_fn=lambda u: api_payload(40 if "numQbs=2&" in u else 200))
            self.assertEqual(0, rc)
            self.assertEqual(sorted(S.FC_COMBOS), sorted(p.stem for p in Path(tmp).glob("*.json")))

    def test_partial_pull_writes_nothing(self):
        """Negative test: one short list (the 2026-10-05 outage shape) blocks every write."""
        with TemporaryDirectory() as tmp:
            sizes = iter([200, 40, 200])
            rc = P.main(["--cache-dir", tmp, "--week", "5"], fetch_fn=lambda u: api_payload(next(sizes)))
            self.assertEqual(2, rc)
            self.assertEqual([], list(Path(tmp).glob("*.json")))


if __name__ == "__main__":
    unittest.main()
