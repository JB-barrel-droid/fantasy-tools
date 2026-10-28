"""EXPERIMENT (JEG-1176), not for main: put the build into the state the nightly
rebuild chain saw in run 40624176718 (CBS one week behind every other source and
on a red review hold for "fidelity: scrape_validity").

`apply` builds dist/ once, takes tests.test_week_history.transition_overrides
(lagging=("cbs",)) (CBS's saved week before the newest week, as served natives
and label), adds a red validationHold to that section, and writes it into the
canonical fixture data/fixtures/current/comparison-sources-data.json. It then
re-runs the sync so the history index, the published fixture copy and every
later test's own sync (tests/_render_env.ensure_built) all derive the chain's
state from those inputs: rewriting only dist/ would be undone by the first
test that re-syncs.

`run SHARD` runs every test-core-shard-SHARD module on its own (no stop at the
first failure) and prints one ::error annotation per failing module naming the
failing tests and the first assertion line.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipelines"))
CANON = ROOT / "data" / "fixtures" / "current" / "comparison-sources-data.json"


def sync():
    proc = subprocess.run([sys.executable, "pipelines/sync_dashboard_artifacts.py"], cwd=ROOT,
                          capture_output=True, text=True)
    if proc.returncode != 0 and os.environ.get("LAG_PROBE_ALLOW_SYNC_FAIL") != "1":
        sys.exit(f"sync failed: {proc.stderr[-1500:]}")


def apply():
    sync()
    from tests import test_week_history as W
    overrides = W.transition_overrides(lagging=("cbs",))
    index = json.loads(overrides["assets/history/index.json"])
    lag_week = index["served"]["cbs"]["week"]
    section = json.loads(overrides[W.FIXTURE_ASSET])["sources"]["cbs"]
    # transition_overrides swaps only the natives the page reads; the canonical
    # fixture also carries the saved Indexed values and the combo's vintage, which
    # the sync's rank guard checks. Keep them consistent with the swapped natives
    # (Indexed = native x the combo's one factor, JEG-482).
    for combo in section["combos"].values():
        factor = combo["fit"]["order_preserving_rescale"]["factor"]
        combo["reindexed"] = {k: float(v) * factor for k, v in combo["native"].items()}
        combo["n"] = len(combo["native"])
        combo["vintage"] = {"content_vintage": f"Week {lag_week}", "week_designated": f"Week {lag_week}"}
    section["validationHold"] = {"reason": "fidelity: scrape_validity", "week": lag_week, "root": "cbs",
                                 "stage": "scrape_validity", "hold_level": "red"}
    doc = json.loads(CANON.read_text(encoding="utf-8"))
    doc["sources"]["cbs"] = section
    CANON.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sync()
    built = json.loads((ROOT / "dist" / "assets" / "history" / "index.json").read_text(encoding="utf-8"))
    served = {k: v.get("week") for k, v in built["served"].items()}
    fixture = json.loads((ROOT / "dist" / "assets" / "comparison-sources-data.json").read_text(encoding="utf-8"))
    hold = fixture["sources"]["cbs"].get("validationHold")
    print(f"lag probe: served weeks {served}; cbs hold {hold}")
    newest = max(w for k, w in served.items() if k != "cbs" and isinstance(w, int))
    if served.get("cbs") != newest - 1 or (hold or {}).get("hold_level") != "red":
        sys.exit("lag probe: the rebuilt dist is not in the chain's state")


def modules(shard):
    out = subprocess.run(["make", "-n", f"test-core-shard-{shard}"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout
    return [line.strip() for line in out.splitlines()
            if line.strip().startswith(("python3 -m unittest", "node tests/"))]


def esc(text):
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def run(shard, label):
    failed = []
    for cmd in modules(shard):
        proc = subprocess.run(cmd, shell=True, cwd=ROOT, capture_output=True, text=True)
        status = "ok" if proc.returncode == 0 else f"FAILED rc={proc.returncode}"
        print(f"[{label}] {cmd}: {status}", flush=True)
        if proc.returncode == 0:
            continue
        text = proc.stdout + "\n" + proc.stderr
        tests = re.findall(r"^(?:FAIL|ERROR): (\S+ \([^)]+\))", text, re.M)
        first = next((ln.strip() for ln in text.splitlines()
                      if re.match(r"\s*(AssertionError|[A-Za-z]*Error|Exception|SkipTest)\b", ln)
                      or "assert" in ln.lower() and "Error" in ln), "")
        if not first:
            first = (text.strip().splitlines() or [""])[-1]
        failed.append((cmd.split()[-1], tests, first[:400]))
        sys.stdout.write(text[-6000:] + "\n")
    shown = failed[:9]
    for module, tests, first in shown:
        print(f"::error title=[{label}] {module}::" + esc(
            f"tests: {', '.join(tests) or '(module level)'}\nfirst: {first}"))
    if failed[9:]:
        rest = "; ".join(f"{m}: {', '.join(t) or '(module level)'} | {f[:150]}" for m, t, f in failed[9:])
        print(f"::error title=[{label}] {len(failed) - 9} more failing modules::" + esc(rest))
    if not failed:
        print(f"::notice title=[{label}] shard {shard}::every module passed")
    return 0


if __name__ == "__main__":
    if sys.argv[1] == "apply":
        apply()
    else:
        sys.exit(run(sys.argv[2], sys.argv[3]))
