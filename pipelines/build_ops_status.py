#!/usr/bin/env python3
"""Build modules/ops-status.json: the facts the ops dashboard needs that no
other producer publishes (ops-dashboard lane, 2026-10-08).

The ops dashboard (modules/status.html) reads the existing producers directly
(monitoring-summary.json, github-actions.json, comparison-chain-status.json,
source-import-health.json, pipeline-checkpoints.json, reference-freshness.json,
assets/history/index.json). This file adds only what nothing else carries:

  deploy      pages.yml runs with head_sha, main's HEAD, and the build tag the
              live site serves right now (so "live vs main" is answerable)
  synthetic   the last live-page-synthetic run and its report (pages[], page
              errors); the workflow only uploads it as a run artifact
  alerts      open GitHub issues labelled ops-alert (the monitoring lane's
              deduplicated alert channel)
  identity    the identity review queue (public.player_identity_unresolved_v)
  players_bake  players.json meta: as_of and the snapshot date of every source

Every block carries its own `as_of` and either `status: "ok"` or
`status: "error"` with the reason. A failed read never drops the block and
never reports green: the page shows the error as Unknown/Failed.

Runs in health-artifacts.yml with GITHUB_TOKEN (actions:read, issues:read)
and the Supabase service key. Locally it runs with whatever is available
(`GH_TOKEN=$(gh auth token)`); missing credentials become block errors.

Usage:
  python3 pipelines/build_ops_status.py [--out output/ops-status.json]
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

REPO = "JB-barrel-droid/fantasy-tools"
SITE = "https://jb-barrel-droid.github.io/fantasy-tools/"
SCHEMA = "ddf-ops-status-v1"
ALERT_LABEL = "ops-alert"
ALERT_KEY = re.compile(r"<!--\s*ops-alert-key:\s*([^\s]+)\s*-->")
BUILD_META = re.compile(r'<meta name="trade-chart-build" content="([^"]*)"')
PLAYERS = ROOT / "data" / "fixtures" / "current" / "players.json"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def gh_request(path: str):
    url = path if path.startswith("http") else f"https://api.github.com/repos/{REPO}/{path}"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ddf-ops-status/1.0"}
    if _token():
        headers["Authorization"] = f"Bearer {_token()}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as resp:
        body = resp.read()
    return json.loads(body.decode())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 - urllib hook
        return None


def gh_download(url: str) -> bytes:
    """Artifact zips redirect to signed blob storage, which rejects the GitHub
    Authorization header urllib would forward: follow the redirect by hand."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ddf-ops-status/1.0"}
    if _token():
        headers["Authorization"] = f"Bearer {_token()}"
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        if e.code not in (301, 302, 303, 307, 308):
            raise
        location = e.headers.get("Location")
    req = urllib.request.Request(location, headers={"User-Agent": "ddf-ops-status/1.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def http_get_text(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "ddf-ops-status/1.0", "Cache-Control": "no-cache"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def _err(exc: Exception) -> str:
    return f"{type(exc).__name__}: {str(exc)[:240]}"


def block(builder, *args):
    """Run one block builder; a failure becomes an error block, never a crash."""
    try:
        out = builder(*args)
        out.setdefault("status", "ok")
    except Exception as exc:  # noqa: BLE001 - reported in the artifact
        out = {"status": "error", "error": _err(exc)}
    out.setdefault("as_of", now_iso())
    return out


def _duration_s(run: dict) -> int | None:
    try:
        a = datetime.fromisoformat(run["run_started_at"].replace("Z", "+00:00"))
        b = datetime.fromisoformat(run["updated_at"].replace("Z", "+00:00"))
        return max(0, int((b - a).total_seconds()))
    except Exception:  # noqa: BLE001
        return None


def slim_run(run: dict) -> dict:
    return {
        "id": run.get("id"),
        "created_at": run.get("created_at"),
        "updated_at": run.get("updated_at"),
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "event": run.get("event"),
        "head_sha": run.get("head_sha"),
        "duration_s": _duration_s(run),
        "html_url": run.get("html_url"),
    }


def tag_sha(tag: str | None) -> str | None:
    """tv-YYYYMMDD-HHMM-<sha> -> <sha> (None when the tag is not that shape)."""
    m = re.fullmatch(r"tv-\d{8}-\d{4}-([0-9a-f]{4,40})", tag or "")
    return m.group(1) if m else None


def deploy_verdict(live_tag: str | None, main_sha: str | None, deployed_sha: str | None) -> tuple[str, str]:
    """Compare the live build tag to main's HEAD and the last successful deploy."""
    live = tag_sha(live_tag)
    if not live:
        return "unknown", f"live build tag unreadable ({live_tag!r})"
    if main_sha and main_sha.startswith(live):
        return "current", "live site serves main's HEAD"
    if deployed_sha and deployed_sha.startswith(live):
        return "pending", "live site serves the last successful deploy; main has moved since"
    return "unexpected", "live site serves a build that is neither main's HEAD nor the last successful deploy"


def build_deploy() -> dict:
    runs = gh_request("actions/workflows/pages.yml/runs?branch=main&per_page=10").get("workflow_runs", [])
    main = gh_request("commits/main")
    main_sha = main.get("sha")
    main_at = ((main.get("commit") or {}).get("committer") or {}).get("date")
    deployed = next((r for r in runs if r.get("conclusion") == "success"), None)
    code, html = http_get_text(SITE)
    m = BUILD_META.search(html)
    live_tag = m.group(1) if m else None
    verdict, why = deploy_verdict(live_tag, main_sha, deployed and deployed.get("head_sha"))
    return {
        "main_sha": main_sha,
        "main_committed_at": main_at,
        "live_url": SITE,
        "live_http_status": code,
        "live_tag": live_tag,
        "last_success_sha": deployed and deployed.get("head_sha"),
        "verdict": verdict,
        "verdict_reason": why,
        "pages_runs": [slim_run(r) for r in runs],
    }


def trim_report(rep: dict) -> dict:
    """Keep what the dashboard shows from tests/rendered_gate/live.mjs output."""
    pages = []
    for p in rep.get("pages") or []:
        pages.append({
            "name": p.get("name"),
            "url": p.get("url"),
            "httpStatus": p.get("httpStatus"),
            "liveTag": p.get("liveTag"),
            "passed": bool(p.get("passed")),
            "problems": (p.get("problems") or [])[:10],
            "pageErrors": (p.get("pageErrors") or [])[:5],
            "tabs": [{"hash": t.get("hash"), "visible": t.get("visible"), "rowCount": t.get("rowCount"),
                      "problems": (t.get("problems") or [])[:5]} for t in (p.get("tabs") or [])],
        })
    return {
        "passed": bool(rep.get("passed")),
        "url": rep.get("url"),
        "liveTag": rep.get("liveTag"),
        "expectedBuilds": rep.get("expectedBuilds"),
        "problems": (rep.get("problems") or [])[:20],
        "pageErrors": (rep.get("pageErrors") or [])[:10],
        "pages": pages,
    }


def build_synthetic() -> dict:
    runs = gh_request("actions/workflows/live-page-synthetic.yml/runs?per_page=5").get("workflow_runs", [])
    done = [r for r in runs if r.get("status") == "completed"]
    if not done:
        return {"status": "error", "error": "no completed live-page-synthetic run", "run": None, "report": None}
    run = done[0]
    out = {"run": slim_run(run), "report": None}
    arts = gh_request(f"actions/runs/{run['id']}/artifacts").get("artifacts", [])
    art = next((a for a in arts if a.get("name") == "live-page-synthetic-results" and not a.get("expired")), None)
    if not art:
        out.update(status="error", error="the run has no live-page-synthetic-results artifact")
        return out
    try:
        with zipfile.ZipFile(io.BytesIO(gh_download(art["archive_download_url"]))) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".json"))
            out["report"] = trim_report(json.loads(zf.read(name).decode()))
    except Exception as exc:  # noqa: BLE001 - keep the run, report the read failure
        out.update(status="error", error=f"report unreadable: {_err(exc)}")
    return out


def parse_alerts(issues: list[dict]) -> list[dict]:
    out = []
    for i in issues:
        if "pull_request" in i:
            continue
        m = ALERT_KEY.search(i.get("body") or "")
        out.append({
            "number": i.get("number"),
            "title": i.get("title"),
            "key": m.group(1) if m else None,
            "created_at": i.get("created_at"),
            "updated_at": i.get("updated_at"),
            "html_url": i.get("html_url"),
        })
    return out


def build_alerts() -> dict:
    issues = gh_request(f"issues?labels={ALERT_LABEL}&state=open&per_page=100")
    return {"label": ALERT_LABEL, "open": parse_alerts(issues)}


def summarize_identity(rows: list[dict]) -> dict:
    by_source = []
    total = 0
    for r in sorted(rows, key=lambda r: str(r.get("source"))):
        queued = sum(int(r.get(k) or 0) for k in ("review", "unmatched", "provisional"))
        total += queued
        by_source.append({**{k: r.get(k) for k in ("source", "review", "unmatched", "provisional", "verified", "last_seen_at")},
                          "queued": queued})
    return {"queue_total": total, "by_source": by_source}


def build_identity() -> dict:
    from gh_sbclient import get  # noqa: PLC0415 - optional dependency at runtime
    return summarize_identity(get("player_identity_unresolved_v", "?select=*"))


def build_players_bake() -> dict:
    meta = json.loads(PLAYERS.read_text(encoding="utf-8")).get("meta") or {}
    snapshots = {k[: -len("_snapshot")]: v for k, v in meta.items()
                 if k.endswith("_snapshot") and isinstance(v, str)}
    built_at = (meta.get("dataset_status") or {}).get("built_at")
    return {"as_of": built_at or meta.get("as_of"), "players_as_of": meta.get("as_of"),
            "n_players": meta.get("n_players"), "snapshots": snapshots}


def git_head() -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=15)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def build() -> dict:
    blocks = {
        "deploy": block(build_deploy),
        "synthetic": block(build_synthetic),
        "alerts": block(build_alerts),
        "identity": block(build_identity),
        "players_bake": block(build_players_bake),
    }
    return {
        "schema": SCHEMA,
        "generated_at": now_iso(),
        "producer": os.environ.get("GITHUB_WORKFLOW") or "local",
        "checkout_sha": git_head(),
        "blocks": blocks,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "output" / "ops-status.json")
    args = ap.parse_args()
    doc = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for name, b in doc["blocks"].items():
        print(f"{name}: {b['status']}" + (f" -- {b['error']}" if b.get("error") else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
