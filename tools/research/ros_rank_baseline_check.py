#!/usr/bin/env python3
"""JEG-1251: can the captured DDF baseline (published_<s>.txt) be rebuilt from stored files?

Research only. The study's baseline is the `value` field the DDF connector's get_values
returned on 2026-10-29 01:3x UTC (as_of 2026-10-28, 12 teams, 1QB). In the code that
serves it (supabase/functions/get-values/index.ts) that field is ddfByVersion.blended.value
from value-model.js runValuePipeline: under JEG-1073 the equal-weight mean of the Adjusted
values of the trade charts included that week (FantasyCalc, an observed-trade estimate,
plus the USA Today, FantasyPros and CBS publisher charts), not a publisher-only average and
not a raw chart value. The capture did not record which charts were included.

This check reruns that recipe offline with the repo's headless edge runner
(tests/_edge_pipeline_runner.cjs) on the site bundle committed at BUNDLE_COMMIT, the last
automated comparison rebuild before the capture, and compares it with the capture by
player_key. It needs node and git history back to BUNDLE_COMMIT. No network, no Supabase.
Writes docs/research/data/jeg1198/ros_rank_baseline_check_out.json only.
"""
import json
import re
import statistics as st
import subprocess
import sys
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
W = REPO / "docs/research/data/jeg1198"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ros_rank_keys as K  # noqa: E402

BUNDLE_COMMIT = "cbaac75"  # "Automated comparison rebuild ... + players.json bake", 2026-10-29 00:08 UTC
BUNDLE_PATH = "app/trade-value-chart"
SCORINGS = ["ppr", "half_ppr", "standard"]


def export_bundle(dst):
    tar = subprocess.run(["git", "-C", str(REPO), "archive", BUNDLE_COMMIT, BUNDLE_PATH],
                         capture_output=True, check=True).stdout
    tarfile.open(fileobj=BytesIO(tar)).extractall(dst, filter="data")
    full = subprocess.run(["git", "-C", str(REPO), "rev-parse", BUNDLE_COMMIT],
                          capture_output=True, text=True, check=True).stdout.strip()
    return Path(dst) / BUNDLE_PATH, full


def main():
    out = {"recipe": __doc__.split("Research only. ")[1].split("This check")[0].strip().replace("\n", " "),
           "bundle_commit": None, "scorings": {}}
    with tempfile.TemporaryDirectory() as tmp:
        try:
            bundle, full = export_bundle(tmp)
        except subprocess.CalledProcessError:
            sys.exit(f"needs git history to {BUNDLE_COMMIT}: git fetch --depth=200 origin main")
        out["bundle_commit"] = full
        out["bundle_sha256"] = {f: K.sha256(bundle / f) for f in
                                ["assets/comparison-sources-data.json", "assets/value-model.js", "index.html"]}
        for s in SCORINGS:
            run = subprocess.run(["node", "--experimental-strip-types", str(REPO / "tests/_edge_pipeline_runner.cjs"),
                                  "--scoring", s, "--teams", "12", "--superflex", "0", "--dist", str(bundle) + "/"],
                                 capture_output=True, text=True, check=True, cwd=REPO)
            rebuilt = {int(k): v for k, v in json.loads(run.stdout).items()}
            cap = {}
            for line in open(W / f"published_{s}.txt"):
                if line.strip():
                    name, pos, v = line.strip().split("|")
                    K.put(cap, name, pos, f"published_{s}", (name, float(v)))
            gaps = []
            for k, (name, v) in cap.items():
                if k in rebuilt and rebuilt[k] is not None:
                    gaps.append((round(rebuilt[k], 1) - v, name, v, round(rebuilt[k], 1)))
            ab = [abs(g[0]) for g in gaps]
            out["scorings"][s] = {
                "captured_rows": len(cap), "compared": len(gaps),
                "within_0_05": sum(1 for a in ab if a < 0.051),
                "median_abs_gap": round(st.median(ab), 2), "max_abs_gap": round(max(ab), 1),
                "largest": [{"player": n, "captured": v, "rebuilt": r} for _, n, v, r in
                            sorted(gaps, key=lambda g: -abs(g[0]))[:8]],
            }
    out["joins"] = K.join_report()
    out["provenance"] = K.provenance()
    json.dump(out, open(W / "ros_rank_baseline_check_out.json", "w"), indent=1)
    for s, r in out["scorings"].items():
        print(s, {k: v for k, v in r.items() if k != "largest"})


if __name__ == "__main__":
    main()
