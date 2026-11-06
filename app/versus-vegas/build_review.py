#!/usr/bin/env python3
"""Export both isolated layouts. Stored real inputs pass through unchanged.

Without --input, use the existing frozen comparison-test fixture and label it
synthetic. This never activates a data source or changes a live page.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pipelines.build_versus_vegas import build_view, render_html  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.resolve().is_relative_to((ROOT / "dist").resolve()):
        parser.error("Review exports must stay outside dist")
    if args.input:
        raw = args.input.read_bytes()
        doc = json.loads(raw)
        note = "Offline preview · saved inputs"
    else:
        from tests.test_versus_vegas import partial_fixture
        doc = partial_fixture()
        doc["producer"] = "tests.test_versus_vegas.partial_fixture (synthetic)"
        raw = json.dumps(doc, sort_keys=True).encode()
        note = "Synthetic fixture · layout review only"
    view = build_view(doc)
    view["input_sha256"] = hashlib.sha256(raw).hexdigest()
    args.out.mkdir(parents=True, exist_ok=True)
    for layout in ("compact", "analysis"):
        (args.out / f"{layout}.html").write_text(render_html(view, layout, note))
    print(f"Exported two isolated review layouts to {args.out}; shared input {view['input_sha256']}")


if __name__ == "__main__":
    main()
