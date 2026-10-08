"""chore/retire-extras (2026-10-08): three producer-less leftovers stay retired.

Jeremy retired them because they had no producer and only ever showed as
permanent stale warnings:

1. Player news (assets/player-news.json, news.generated_at 2026-09-20; its
   inputs lived only in a local raw folder) and the news.trade_values_published_at
   freshness item that came from the same file.
2. The source-value lineage audit (dist/modules/source-value-lineage.json,
   `make monitor-lineage`, scrape_live_source_pages.py) and the two monitor
   views derived from it (vorp-view.json, adj-view.json). The chart's saved
   VORP views (vorp_views inside comparison-sources-data.json) are unrelated
   and stay.

Git history keeps everything; the last commit carrying all of it is aefb8f7.
Each test fails on that commit (the retired thing is present there).
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RETIRED_FILES = (
    "data/fixtures/current/player-news.json",
    "app/trade-value-chart/assets/player-news.json",
    "dist/assets/player-news.json",
    "pipelines/ingest_player_news.py",
    "pipelines/build_source_value_lineage.py",
    "pipelines/build_view_artifacts.py",
    "pipelines/scrape_live_source_pages.py",
    "pipelines/validate_imputed_vorps.py",
    "dist/modules/source-value-lineage.json",
    "dist/modules/vorp-view.json",
    "dist/modules/adj-view.json",
    "dist/modules/live-page-scrape.json",
)
RETIRED_ARTIFACTS = ("player-news.json", "source-value-lineage.json", "vorp-view.json",
                     "adj-view.json", "live-page-scrape.json")


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


class RetiredExtrasTest(unittest.TestCase):
    def test_retired_files_are_gone(self):
        present = [rel for rel in RETIRED_FILES if (ROOT / rel).exists()]
        self.assertEqual([], present)

    def test_monitor_surfaces_do_not_list_retired_artifacts(self):
        spec = json.loads(read("modules/surfaces.json"))
        ids = {s["id"] for s in spec["surfaces"]}
        urls = " ".join(s["url"] for s in spec["surfaces"])
        self.assertEqual(set(), ids & {"player-news", "vorp-view", "adj-view", "source-value-lineage"})
        for name in RETIRED_ARTIFACTS:
            self.assertNotIn(name, urls)

    def test_pages_do_not_fetch_retired_artifacts(self):
        for rel in ("modules/status.html", "modules/dashboard.html",
                    "app/trade-value-chart/index.html",
                    "app/trade-value-chart/assets/product-data.js",
                    "app/trade-value-chart/assets/comparison-dashboard.js"):
            text = read(rel)
            for name in RETIRED_ARTIFACTS:
                self.assertNotIn(name, text, f"{rel} still reads {name}")

    def test_build_and_ci_do_not_run_retired_producers(self):
        makefile = read("Makefile")
        self.assertIsNone(re.search(r"(?m)^(monitor-lineage|source-news):", makefile))
        for rel in ("Makefile", ".github/workflows/pages.yml", ".github/workflows/preview.yml",
                    "pipelines/sync_dashboard_artifacts.py"):
            text = read(rel)
            for producer in ("build_source_value_lineage", "build_view_artifacts",
                             "scrape_live_source_pages", "ingest_player_news", "player-news.json"):
                self.assertNotIn(producer, text, f"{rel} still runs/copies {producer}")


if __name__ == "__main__":
    unittest.main()
