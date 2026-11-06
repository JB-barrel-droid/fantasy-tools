#!/usr/bin/env python3
"""Export JEG-1348's held integration into a local review copy.

Example: CHROMIUM_PATH=/usr/bin/chromium python3 tools/preview_bench_context.py --out /tmp/jeg1348-review
Then: python3 -m http.server 8765 --directory /tmp/jeg1348-review
Open http://localhost:8765, then Position weights in the context menu.
The exported page uses the data fixture's clock, not live data.
"""
import argparse
import hashlib
import json
import shlex
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import _render_env
from tests.test_jeg1348_bench_context_render import integration_overrides, PATCH, CASES


def export_review(destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Choose a new review directory: {destination}")
    _render_env.ensure_built()
    overrides = integration_overrides()
    shutil.copytree(ROOT / "dist", destination)
    for relative, data in overrides.items():
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    page = destination / "index.html"
    page.write_text(page.read_text().replace("</head>", "<script>" + _render_env.pin_data_week_script() + "</script></head>", 1))
    manifest = {"purpose": "JEG-1348 local review; held integration applied to this exported copy",
                "patchSha256": hashlib.sha256(PATCH.read_bytes()).hexdigest(),
                "historicalMatrixSha256": hashlib.sha256((ROOT / CASES["historical_source"]).read_bytes()).hexdigest(),
                "fixtureClock": _render_env.pin_data_week_script()}
    (destination / "jeg1348-review.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, required=True, help="A new directory for the review copy")
    args = parser.parse_args()
    out = export_review(args.out.resolve())
    print(f"JEG-1348 fixture review exported to {out}")
    print("Serve locally: " + shlex.join(["python3", "-m", "http.server", "8765", "--directory", str(out)]))
