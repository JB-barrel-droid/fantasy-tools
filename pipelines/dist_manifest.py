#!/usr/bin/env python3
"""Per-file SHA-256 manifest of a built ``dist/`` tree (JEG-31 preview deploys).

A preview is only worth anything if it serves the bytes production would publish
for the same commit. This tool makes that checkable:

  python3 pipelines/dist_manifest.py build dist --out dist-manifest.json
  python3 pipelines/dist_manifest.py compare a.json b.json

The comparison rule is deliberately narrow (Jeremy, 2026-10-01): every file must be
byte-identical EXCEPT one named field. ``assets/reference-freshness.json`` carries a
wall-clock ``generated_at`` that differs on every run of ``make sync`` even for the
same commit; that single top-level field is ignored when hashing that single file.
Nothing else is ignored. The same file also records ``today`` and date-relative
values, so two manifests are only comparable when their ``today`` matches; otherwise
``compare`` refuses instead of reporting a difference or a match.

Fail-closed: an unreadable or non-JSON freshness file is an error, never a skip.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

SCHEMA = "trade-value-dist-manifest-v1"
FRESHNESS_PATH = "assets/reference-freshness.json"
IGNORED_FIELD = "generated_at"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_file_hash(rel_path: str, data: bytes) -> str:
    """Hash of one file; the single permitted exception is applied here only."""
    if rel_path != FRESHNESS_PATH:
        return sha256_bytes(data)
    try:
        doc = json.loads(data)
    except ValueError as exc:
        raise SystemExit(f"manifest refused: {rel_path} is not valid JSON ({exc})")
    if not isinstance(doc, dict):
        raise SystemExit(f"manifest refused: {rel_path} is not a JSON object")
    doc.pop(IGNORED_FIELD, None)
    canonical = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    return sha256_bytes(canonical)


def root_hash(files: dict[str, str]) -> str:
    lines = "".join(f"{path}\0{digest}\n" for path, digest in sorted(files.items()))
    return sha256_bytes(lines.encode())


def build_manifest(dist_dir: Path) -> dict:
    dist_dir = Path(dist_dir)
    if not dist_dir.is_dir():
        raise SystemExit(f"manifest refused: {dist_dir} is not a directory")
    files: dict[str, str] = {}
    for path in sorted(p for p in dist_dir.rglob("*") if p.is_file()):
        rel = path.relative_to(dist_dir).as_posix()
        files[rel] = canonical_file_hash(rel, path.read_bytes())
    if not files:
        raise SystemExit(f"manifest refused: {dist_dir} contains no files")
    today = None
    freshness = dist_dir / FRESHNESS_PATH
    if freshness.is_file():
        today = json.loads(freshness.read_bytes()).get("today")
    return {
        "schema": SCHEMA,
        "today": today,
        "ignored": [f"{FRESHNESS_PATH}#{IGNORED_FIELD}"],
        "file_count": len(files),
        "root_sha256": root_hash(files),
        "files": files,
    }


def compare_manifests(a: dict, b: dict) -> dict:
    """Return {'comparable': bool, 'equal': bool, 'differences': [...], 'reason': str}."""
    for name, m in (("first", a), ("second", b)):
        if m.get("schema") != SCHEMA:
            raise SystemExit(f"compare refused: {name} manifest has schema {m.get('schema')!r}")
    if a.get("today") != b.get("today"):
        return {
            "comparable": False,
            "equal": False,
            "differences": [],
            "reason": (f"built on different days ({a.get('today')!r} vs {b.get('today')!r}); "
                       f"{FRESHNESS_PATH} holds date-relative values, so they are not comparable"),
        }
    fa, fb = a["files"], b["files"]
    diffs = []
    for path in sorted(set(fa) | set(fb)):
        if path not in fb:
            diffs.append(f"only in first: {path}")
        elif path not in fa:
            diffs.append(f"only in second: {path}")
        elif fa[path] != fb[path]:
            diffs.append(f"differs: {path}")
    return {"comparable": True, "equal": not diffs, "differences": diffs, "reason": ""}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="write a manifest for a dist directory")
    b.add_argument("dist", type=Path)
    b.add_argument("--out", type=Path, default=None)
    c = sub.add_parser("compare", help="compare two manifests")
    c.add_argument("first", type=Path)
    c.add_argument("second", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "build":
        manifest = build_manifest(args.dist)
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        if args.out:
            args.out.write_text(text)
            print(f"manifest: {manifest['file_count']} files, root {manifest['root_sha256']}, "
                  f"today {manifest['today']} -> {args.out}")
        else:
            sys.stdout.write(text)
        return 0

    result = compare_manifests(json.loads(args.first.read_text()),
                               json.loads(args.second.read_text()))
    if not result["comparable"]:
        print(f"NOT COMPARABLE: {result['reason']}", file=sys.stderr)
        return 2
    if result["equal"]:
        print("IDENTICAL (ignoring only reference-freshness.json generated_at)")
        return 0
    print("DIFFERENT:", file=sys.stderr)
    for line in result["differences"]:
        print(f"  {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
