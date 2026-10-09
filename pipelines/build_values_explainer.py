#!/usr/bin/env python3
"""Build the values explainer: one self-contained HTML page showing how every
source's values are made, with the chart engine's own numbers.

    python3 pipelines/build_values_explainer.py [--out output/values-explainer/index.html]
    make values-explainer

Steps:
  1. `make sync`'s builder regenerates dist/ from app/ and the fixtures.
  2. dist/ is served locally and the chart engine is loaded headless
     (Playwright Chromium, hermetic: no outside hosts).
  3. app/values-explainer/extract.js reads the engine through its read-only
     accessors at the default setting (12 teams, Full PPR, standard roster),
     in all three views, plus a few other settings for the sensitivity table.
  4. The bundle is trimmed, stamped with the commit, build tag, logic-file
     hashes and the open math-review items, and written into
     app/values-explainer/template.html.

Nothing here computes a chart value. Every number on the page is the engine's,
except labelled sums, ratios and the two-tier reconstruction (which reports how
closely it reproduces the engine).

The narrative in the template was written against the logic files listed in
app/values-explainer/reviewed.json. When their hashes no longer match, the page
says which files changed so the explanation gets re-checked (CLAUDE.md,
"Values explainer").
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import http.server
import json
import re
import socketserver
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP = ROOT / "app" / "values-explainer"
DEFAULT_OUT = ROOT / "output" / "values-explainer" / "index.html"
PAGE = "modules/math-inspector.html"
HERMETIC_ARGS = ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE 127.0.0.1, EXCLUDE localhost"]

# The files whose logic the page explains. A hash change here flags the
# narrative for review.
LOGIC_FILES = [
    "app/trade-value-chart/assets/value-model.js",
    "app/trade-value-chart/assets/curve-widget.js",
    "pipelines/vorp_translation/unified.py",
    "pipelines/twotier_reference.py",
    "pipelines/build_ddf_two_tier_leg.py",
    "pipelines/build_adjustment_inputs.py",
    "pipelines/build_imputed_vorps.py",
    "pipelines/build_reweighted_values.py",
    "pipelines/reindex_comparison_section.py",
    "docs/methodology.md",
]
SETTINGS = [["ppr", 8], ["ppr", 10], ["ppr", 12], ["ppr", 14], ["half_ppr", 12], ["standard", 12]]
POS = ("QB", "RB", "WR", "TE")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return ""


def build_tag() -> str:
    for p in (DIST / "index.html", DIST / "modules" / "status.html"):
        if p.exists():
            m = re.search(r"tv-\d{8}-\d{4}-[0-9a-f]{7}", p.read_text(errors="ignore"))
            if m:
                return m.group(0)
    return ""


def math_review_items() -> list[dict]:
    path = ROOT / "docs" / "math-review-agenda.md"
    if not path.exists():
        return []
    items = []
    for m in re.finditer(r"^## (MR-\d+) - (.+)$", path.read_text(), re.M):
        items.append({"id": m.group(1), "title": m.group(2).strip()})
    return items


def extract() -> dict:
    from playwright.sync_api import sync_playwright

    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(DIST)))
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    script = (APP / "extract.js").read_text()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=HERMETIC_ARGS)
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            page.goto(f"http://127.0.0.1:{port}/{PAGE}", wait_until="load")
            page.wait_for_function(
                "window.TradeValueCurveControls && window.TradeValueCurveControls.isReady()", timeout=120000)
            data = page.evaluate(script, {"settings": SETTINGS})
            browser.close()
    finally:
        srv.shutdown()
    return data


def r(x, nd=3):
    return None if x is None else round(float(x), nd)


def trim(raw: dict) -> dict:
    """Keep what the page draws; round floats so the page stays small."""
    insp = raw["inspection"]
    views = {v: {s: {k: r(val) for k, val in m.items()} for s, m in series.items()}
             for v, series in raw["views"].items()}
    published = {}
    for key, p in insp["published"].items():
        d = p.get("derivation") or {}
        t = (d.get("translation") or {})
        vw = p.get("views") or {}
        published[key] = {
            "native": {k: r(v, 2) for k, v in (p.get("native") or {}).items()},
            "peers": p.get("peers"),
            "modes": {"indexed": p["indexed"]["mode"], "vorp": p["vorp"]["mode"], "adj": p["adj"]["mode"]},
            "factor": d.get("factor"), "basis": d.get("basis"), "shared": d.get("shared"),
            "positions": t.get("positions"),
            "translated": t.get("translated"),
            "waiver": d.get("waiver"),
            "savedIndexTotal": p.get("savedIndexTotal"),
            "derivedVorp": {k: r(v) for k, v in (vw.get("vorp") or {}).items()},
            "derivedAdj": {k: r(v) for k, v in (vw.get("adj") or {}).items()},
            "vorpScale": vw.get("vorpScale"), "total": vw.get("total"),
            "groups": vw.get("groups"), "budgets": vw.get("budgets"),
            "roles": vw.get("roles"),
        }
    two = {}
    for src, t in raw["twoTier"].items():
        if "error" in t:
            two[src] = t
            continue
        two[src] = {**{k: v for k, v in t.items() if k not in ("values", "starters", "bench")},
                    "values": {k: r(v) for k, v in t["values"].items()},
                    "starters": t["starters"], "bench": t["bench"]}
    adj_inputs = json.loads((ROOT / "app/trade-value-chart/assets/adjustment-inputs.json").read_text())
    baked = {src: e.get("diagnostics") for src, e in adj_inputs.get("sources", {}).items()}
    return {
        "setting": insp["setting"], "versions": insp["versions"], "labels": insp["labels"],
        "seriesKeys": insp["seriesKeys"], "publishedKeys": insp["publishedKeys"],
        "anchorRoles": insp["anchor"]["roles"], "batch": insp["batch"],
        "fixedPie": insp["fixedPie"], "diagnostics": raw["diagnostics"],
        "viewInvariants": {"indexed": raw["diagnostics"].get("viewInvariants"),
                           "vorp": raw.get("viewInvariants_vorp"), "adj": raw.get("viewInvariants_adj")},
        "info": raw["info"], "composite": raw["composite"],
        "compositeByView": {v: raw.get("composite_" + v) for v in ("indexed", "vorp", "adj")},
        "adjustmentWeights": raw["adjustmentWeights"], "bakedCells": baked,
        "adjustmentInputsVersion": adj_inputs.get("version"),
        "positionWeights": raw["positionWeights"], "zones": raw["zones"],
        "players": raw["players"], "views": views, "published": published,
        "twoTier": two,
        "rawVorp": {k: {**{kk: vv for kk, vv in v.items() if kk != "raw"},
                        "raw": {pk: r(pv) for pk, pv in v["raw"].items() if pv > 0}}
                    for k, v in raw.get("rawVorp", {}).items()}, "sensitivity": raw["sensitivity"], "restored": raw["restored"],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--data-out", type=Path, default=None, help="also write the data bundle as JSON")
    ap.add_argument("--skip-sync", action="store_true", help="use the dist/ already built")
    ap.add_argument("--mark-reviewed", action="store_true",
                    help="record the current logic-file hashes as reviewed (after re-checking the narrative)")
    args = ap.parse_args(argv)

    if not args.skip_sync:
        subprocess.run([sys.executable, str(ROOT / "pipelines" / "sync_dashboard_artifacts.py")],
                       cwd=ROOT, check=True, capture_output=True)
    data = trim(extract())
    if args.mark_reviewed:
        (APP / "reviewed.json").write_text(json.dumps({
            "reviewed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "commit": git("rev-parse", "--short", "HEAD"),
            "hashes": {f: sha(ROOT / f) for f in LOGIC_FILES if (ROOT / f).exists()},
        }, indent=2) + "\n")
    reviewed = json.loads((APP / "reviewed.json").read_text()) if (APP / "reviewed.json").exists() else {}
    hashes = {f: sha(ROOT / f) for f in LOGIC_FILES if (ROOT / f).exists()}
    data["meta"] = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git("rev-parse", "--short", "HEAD"),
        "commit_date": git("log", "-1", "--format=%cI"),
        "commit_subject": git("log", "-1", "--format=%s"),
        "build_tag": build_tag(),
        "logic_hashes": hashes,
        "reviewed": reviewed,
        "logic_changed": sorted(f for f, h in hashes.items() if reviewed.get("hashes", {}).get(f) != h),
        "math_review": math_review_items(),
    }
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = (APP / "template.html").read_text().replace("/*__VALUES_DATA__*/null", blob)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html)
    if args.data_out:
        args.data_out.parent.mkdir(parents=True, exist_ok=True)
        args.data_out.write_text(json.dumps(data, indent=1))
    print(f"values explainer -> {args.out} ({len(html) // 1024} KB, commit {data['meta']['commit']}, "
          f"logic changed since review: {data['meta']['logic_changed'] or 'none'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
