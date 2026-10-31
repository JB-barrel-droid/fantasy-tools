"""Dump the engine context league-wide Trade opportunities ran on, for one checkout (JEG-1188).

Serves the checkout's dist the way the league render tests do (tests/test_v2_finder_render._built_dist: CBS held by
tests._holds.pin_holds_in_dist, the v2 page built from that checkout's app/v2), pins the page clock to the data week
(tests/_render_env.pin_data_week_script), seeds tests/fixtures/league/fixture-20team.json and drives the page with
tools/jeg1188/page_driver.cjs (jsdom, no browser). Writes a frozen context: the page's own count and trade ids, and the
engine rows of the rostered players only, with provenance.

Run it from this checkout against any older checkout (a `git worktree add --detach <dir> <rev>`). The older checkout
needs a sync first (`python3 pipelines/sync_dashboard_artifacts.py` there, as `make sync` / _render_env.ensure_built do);
that rewrites a few timestamped files in that worktree, never this one.

  python3 tools/jeg1188/dump_context.py --root <checkout> --jsdom <dir with node_modules/jsdom> --out <ctx.json> [--team 0]
"""
from __future__ import annotations

import argparse
import functools
import http.server
import json
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent


def fixture_today(root: Path) -> str:
    code = ("import sys; sys.path.insert(0, '.'); sys.path.insert(0, 'pipelines'); "
            "from tests.test_week_history import _fixture_today; print(_fixture_today())")
    return subprocess.run([sys.executable, "-c", code], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def build_served(root: Path, out: Path) -> None:
    code = ("import shutil, sys; from pathlib import Path; sys.path.insert(0, '.'); sys.path.insert(0, 'pipelines'); "
            "import build_v2_page; from tests._holds import pin_holds_in_dist; out = Path(sys.argv[1]); "
            "shutil.copytree('dist', out, ignore=shutil.ignore_patterns('v2')); pin_holds_in_dist(out); build_v2_page.build(out)")
    subprocess.run([sys.executable, "-c", code, str(out)], cwd=root, check=True, capture_output=True, text=True)


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", required=True, type=Path)
    ap.add_argument("--jsdom", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--team", default="0")
    ap.add_argument("--label", default="")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if not (root / "build" / "engine" / "index.html").exists():
        raise SystemExit(f"{root} is not synced: run python3 pipelines/sync_dashboard_artifacts.py there first")
    today = fixture_today(root)
    fx = root / "tests" / "fixtures" / "league" / "fixture-20team.json"
    with tempfile.TemporaryDirectory() as tmp:
        served = Path(tmp) / "dist"
        build_served(root, served)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *a):
                pass

        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(served))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            raw = Path(tmp) / "ctx.json"
            try:
                proc = subprocess.run(["node", str(HERE / "page_driver.cjs"), str(args.jsdom), f"http://127.0.0.1:{server.server_address[1]}/v2/",
                                       str(fx), args.team, today, str(raw)], capture_output=True, text=True, timeout=1800)
            finally:
                server.shutdown()
            if proc.returncode != 0:
                raise SystemExit(proc.stderr[-2000:])
            ctx = json.loads(raw.read_text(encoding="utf-8"))
        data = json.loads((served / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
    rostered = {str(e["key"]) for t in ctx["workspace"]["teams"] for e in t["entries"]}
    # Only what the search reads is kept; ddfByVersion (per-version history) is large and unused by finder.js / opportunities.js.
    ctx["rows"] = [{k: v for k, v in r.items() if k != "ddfByVersion"} for r in ctx["rows"] if str(r["player_key"]) in rostered]
    rev = git(root, "rev-parse", "HEAD")
    ctx = {"provenance": {
        "label": args.label, "revision": rev, "revision_date": git(root, "show", "-s", "--format=%cI", rev),
        "revision_subject": git(root, "show", "-s", "--format=%s", rev), "data_built_at": data.get("built_at"),
        "page_clock_pin": today, "fixture": "tests/fixtures/league/fixture-20team.json", "team_index": args.team,
        "served_as": "dist with CBS held (tests._holds.pin_holds_in_dist), v2 page built from the same checkout's app/v2",
        "driver": "tools/jeg1188/page_driver.cjs (jsdom 24.1.3, no browser)", "package_size": "page default, up to 2-for-2",
        "rows_kept": "rostered fixture players only, ddfByVersion dropped"}, **ctx}
    args.out.write_text(json.dumps(ctx, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({"out": str(args.out), "revision": rev[:10], "page": {"total": ctx["page"]["total"], "counts": ctx["page"]["counts"]}}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
