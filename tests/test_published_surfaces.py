"""JEG-424: every required backend -> frontend surface must be in the built
site with the content its page needs.

The consolidation watcher shipped for days reading a JSON file nothing
published (and a Supabase table anon cannot read). This test reads the same
spec as modules/status.html and fails `make validate` (the deploy gate) when a
required surface is missing, unparseable or below its minimum content.
Freshness is checked live by the status page, not here: build-time dist
timestamps are whatever the last producer wrote.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
SPEC = json.loads((ROOT / "modules" / "surfaces.json").read_text())


def count_at(doc, path):
    v = doc.get(path) if path else doc
    return len(v) if isinstance(v, (list, dict)) else None


def problems(dist_root, surfaces):
    out = []
    for s in surfaces:
        if not s.get("required"):
            continue
        f = dist_root / s["url"]
        if not f.is_file():
            out.append(f"{s['id']}: {s['url']} not in the built site")
            continue
        try:
            doc = json.loads(f.read_text())
        except ValueError:
            out.append(f"{s['id']}: {s['url']} is not valid JSON")
            continue
        n = count_at(doc, s.get("count_path"))
        if s.get("min_count") is not None and (n is None or n < s["min_count"]):
            out.append(f"{s['id']}: {s.get('count_path')}={n} < {s['min_count']}")
    return out


class PublishedSurfacesTest(unittest.TestCase):
    def test_spec_is_well_formed(self):
        ids = [s["id"] for s in SPEC["surfaces"]]
        self.assertEqual(len(ids), len(set(ids)))
        for s in SPEC["surfaces"]:
            for key in ("id", "page", "label", "url", "backend", "meaning", "required"):
                self.assertIn(key, s, s.get("id"))
            if not s["required"]:
                self.assertTrue(s.get("known_gap"), f"{s['id']}: optional surfaces must name the gap")

    def test_status_page_and_spec_are_published(self):
        self.assertTrue((DIST / "modules" / "status.html").is_file())
        self.assertEqual(SPEC, json.loads((DIST / "modules" / "surfaces.json").read_text()))

    def test_every_required_surface_is_in_the_built_site(self):
        self.assertEqual([], problems(DIST, SPEC["surfaces"]))

    def test_guard_catches_a_missing_surface(self):
        """Negative test: the pre-JEG-424 site had no consolidated-values.json."""
        import tempfile, shutil
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp)
            for s in SPEC["surfaces"]:
                src = DIST / s["url"]
                if src.is_file():
                    (fake / s["url"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, fake / s["url"])
            (fake / "consolidated-values.json").unlink()
            self.assertTrue(any(p.startswith("consolidation:") for p in problems(fake, SPEC["surfaces"])))
            (fake / "consolidated-values.json").write_text('{"rows": []}')
            self.assertTrue(any("rows=0" in p for p in problems(fake, SPEC["surfaces"])))


if __name__ == "__main__":
    unittest.main()
