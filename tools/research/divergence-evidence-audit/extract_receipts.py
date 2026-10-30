#!/usr/bin/env python3
"""Inventory every committed source-divergence report as a receipt (JEG-1277).

Read only. Walks git history for `dist/modules/source-divergence.json` (the
report `make sync` publishes, JEG-460) and writes one compact receipt per
committed version, with the provenance that sits beside it in history:

* served weeks: the committed `data/history/index.json` whose
  `fixture_built_at` equals the report's own `fixture_built_at` (and, where one
  exists, whose `content_week` equals the report's week, since the reporter
  reads its week from that file): the version in the report's commit when it
  matches, else the newest ancestor version that does (`match` says which). The index in the same commit is often a
  later build, so it is never used without the build match.
* source dates and scoring basis: the committed
  `data/fixtures/current/comparison-sources-data.json` whose `built_at` equals
  the report's `fixture_built_at`, matched the same way.

Nothing is fetched, recomputed or synthesized: every value is copied from a
committed blob, and missing provenance stays missing (null). The reporter,
its config and the resolutions file are only read.

    python3 tools/research/divergence-evidence-audit/extract_receipts.py \
        [--ref origin/main] [--out tests/fixtures/divergence-evidence-audit/committed-receipts.json]

Needs enough history: `git fetch --shallow-since=2026-10-05 origin main` on a
shallow clone. The output is deterministic for a given ref.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REPORT = "dist/modules/source-divergence.json"
INDEX = "data/history/index.json"
FIXTURE = "data/fixtures/current/comparison-sources-data.json"
REPORTER = "pipelines/check_source_divergence.py"
OUT = REPO / "tests" / "fixtures" / "divergence-evidence-audit" / "committed-receipts.json"
SCHEMA = "divergence-evidence-receipts/1"
COMBO_FIELDS = ("n", "outliers", "outlier_rate", "bias", "mad", "status")
EXAMPLE_FIELDS = ("player_key", "value", "consensus")
POSITION_FIELDS = ("n", "outliers", "outlier_rate", "bias", "mad")


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True,
                          text=True).stdout


def commits_touching(ref: str, path: str) -> list[tuple[str, str]]:
    """[(sha, committer ISO date)] oldest first."""
    out = git("log", ref, "--format=%H %cI", "--", path)
    rows = [line.split(" ", 1) for line in out.splitlines() if line.strip()]
    return [(sha, when) for sha, when in reversed(rows)]


class Blobs:
    """`git cat-file --batch` reader, one process for every blob."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(["git", "-C", str(REPO), "cat-file", "--batch"],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE)

    def read(self, spec: str) -> tuple[str | None, bytes | None]:
        self.proc.stdin.write(spec.encode() + b"\n")
        self.proc.stdin.flush()
        header = self.proc.stdout.readline().decode().split()
        if len(header) < 3 or header[1] == "missing":
            return None, None
        body = self.proc.stdout.read(int(header[2]))
        self.proc.stdout.read(1)
        return header[0], body

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait()


def versions_by_build(blobs: Blobs, ref: str, path: str, key: str, wanted: set[str]) -> dict:
    """{build stamp: [(commit, parsed doc)] oldest first} for every committed version of `path`."""
    found: dict = {}
    for sha, _ in commits_touching(ref, path):
        _, body = blobs.read(f"{sha}:{path}")
        if body is None:
            continue
        try:
            doc = json.loads(body)
        except ValueError:
            continue
        if doc.get(key) in wanted:
            found.setdefault(doc[key], []).append((sha, doc))
    return found


def is_ancestor(older: str, newer: str) -> bool:
    return subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", older, newer],
                          capture_output=True).returncode == 0


def match_build(candidates: list, commit: str, week: int | None = None) -> tuple[str, tuple | None]:
    """The companion file the reporter most plausibly read for a report committed at `commit`:
    the version in the same commit when it carries the same build, else the newest earlier
    version (an ancestor) with that build. For the history index, versions whose
    content_week equals the report's week (the reporter reads its week from there) win
    over ones that do not. Returns (match kind, (sha, doc) or None)."""
    if week is not None:
        same_week = [(sha, doc) for sha, doc in candidates if doc.get("content_week") == week]
        if same_week:
            candidates = same_week
    for sha, doc in candidates:
        if sha == commit:
            return "same_commit", (sha, doc)
    earlier = [(sha, doc) for sha, doc in candidates if is_ancestor(sha, commit)]
    if earlier:
        return "earlier_commit", earlier[-1]
    return "not_found", None


def source_date(meta: dict) -> str | None:
    """The source's own content date as the fixture records it (never the fetch time)."""
    for field in ("content_vintage", "vintage", "espn_snapshot"):
        if meta.get(field):
            return str(meta[field])
    return None


def scoring_basis(meta: dict, bases: dict) -> str | None:
    """A token for the fixture's own statement of what was scraped (charts) or how it was
    scored (projections); the text itself is kept once in the document's `scoring_bases`."""
    text = meta.get("claimed_settings") or meta.get("method")
    if not text:
        return None
    token = "sha256:" + hashlib.sha256(str(text).encode()).hexdigest()[:16]
    bases[token] = str(text)
    return token


def receipt(commit: str, committed_at: str, report_blob: str, report: dict, reporter_blob: str | None,
            index_hit, fixture_hit, index_kind: str = "not_found", fixture_kind: str = "not_found",
            bases: dict | None = None) -> dict:
    bases = {} if bases is None else bases
    sources = {}
    for s, v in sorted((report.get("sources") or {}).items()):
        combos = {}
        for key, c in sorted((v.get("combos") or {}).items()):
            row = {f: c.get(f) for f in COMBO_FIELDS}
            # The value-impact evidence the report carries, copied as is: the five largest
            # deviations (player, value, consensus) and the per-position statistics.
            row["examples"] = [{k: e.get(k) for k in EXAMPLE_FIELDS} for e in (c.get("examples") or [])]
            row["by_position"] = {p: {k: b.get(k) for k in POSITION_FIELDS}
                                  for p, b in sorted((c.get("by_position") or {}).items())}
            combos[key] = row
        sources[s] = {"status": v.get("status"), "computed_status": v.get("computed_status"),
                      "week": v.get("week"), "headline_combo": v.get("headline_combo"),
                      "resolution": (v.get("resolution") or {}).get("resolution"), "combos": combos}
    served = None
    if index_hit:
        sha, doc = index_hit
        served = {"index_commit": sha, "match": index_kind, "content_week": doc.get("content_week"),
                  "sources": {s: {k: e.get(k) for k in ("label_week", "week", "fingerprint")}
                              for s, e in sorted((doc.get("served") or {}).items())}}
    source_meta = None
    if fixture_hit:
        sha, doc = fixture_hit
        source_meta = {"fixture_commit": sha, "match": fixture_kind, "sources": {
            s: {"week_designated": m.get("week_designated"), "source_date": source_date(m),
                "fetched_at": m.get("fetched_at"), "scoring_basis": scoring_basis(m, bases)}
            for s, m in sorted((doc.get("sources") or {}).items()) if s in sources}}
    summary = report.get("summary") or {}
    return {
        "commit": commit, "committed_at": committed_at, "report_blob": report_blob,
        "reporter_blob": reporter_blob,
        "report": {"schema": report.get("schema"), "generated_at": report.get("generated_at"),
                   "fixture_built_at": report.get("fixture_built_at"), "week": report.get("week"),
                   "status": report.get("status"), "error": report.get("error"),
                   "thresholds": report.get("thresholds"),
                   "flagged": summary.get("flagged"), "investigate": summary.get("investigate")},
        "served": served, "source_meta": source_meta, "sources": sources,
    }


def extract(ref: str) -> dict:
    blobs = Blobs()
    try:
        head = git("rev-parse", ref).strip()
        raw = []
        for sha, when in commits_touching(ref, REPORT):
            blob, body = blobs.read(f"{sha}:{REPORT}")
            reporter_blob, _ = blobs.read(f"{sha}:{REPORTER}")
            raw.append((sha, when, blob, json.loads(body), reporter_blob))
        builds = {r[3].get("fixture_built_at") for r in raw} - {None}
        index_by = versions_by_build(blobs, ref, INDEX, "fixture_built_at", builds)
        fixture_by = versions_by_build(blobs, ref, FIXTURE, "built_at", builds)
    finally:
        blobs.close()
    receipts, bases = [], {}
    for sha, when, blob, rep, rb in raw:
        build = rep.get("fixture_built_at")
        index_kind, index_hit = match_build(index_by.get(build, []), sha, rep.get("week"))
        fixture_kind, fixture_hit = match_build(fixture_by.get(build, []), sha)
        receipts.append(receipt(sha, when, blob, rep, rb, index_hit, fixture_hit, index_kind, fixture_kind, bases))
    return {"schema": SCHEMA, "synthetic": False,
            "about": "Committed source-divergence reports (JEG-460) with the served-week and source-date "
                     "provenance matched by fixture build. Copied from git blobs by extract_receipts.py; "
                     "nothing fetched or synthesized. null means the provenance was not found in history.",
            "extracted_from": {"ref": ref, "head": head, "report_path": REPORT,
                               "history_floor": raw[0][1] if raw else None},
            "scoring_bases": dict(sorted(bases.items())), "receipts": receipts}


def dumps(doc: dict) -> str:
    """Deterministic JSON with one compact line per receipt, so a regenerated file diffs
    by receipt and stays small."""
    head = {k: v for k, v in doc.items() if k != "receipts"}
    lines = json.dumps(head, indent=1, sort_keys=True)[:-2].rstrip()
    rows = [json.dumps(r, sort_keys=True, separators=(",", ":")) for r in doc["receipts"]]
    return lines + ',\n "receipts": [\n  ' + ",\n  ".join(rows) + "\n ]\n}\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    doc = extract(args.ref)
    text = dumps(doc)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(f"{len(doc['receipts'])} receipts from {doc['extracted_from']['head'][:8]} -> {args.out} "
          f"(sha256 {hashlib.sha256(text.encode()).hexdigest()[:12]})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
