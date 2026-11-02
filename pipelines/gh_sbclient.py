"""Standalone Supabase client for GitHub Actions (no Muse dependency).

Implements the same interface as the Muse-backed sbclient.py, but reads
credentials from environment variables:

    SUPABASE_URL          e.g. https://iskiybsimubiujwuchsl.supabase.co
    SUPABASE_SERVICE_KEY  the service_role key (stored as a GitHub secret)

Drop this on PYTHONPATH as sbclient.py when running outside Muse.
"""

import atexit
from datetime import datetime, timezone
import gzip
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

# JEG-793: response-body bytes per (method, table or rpc/<fn>), so the
# Supabase egress hogs can be ranked from real numbers. Counts only; no row
# data, params or keys are ever stored or logged.
_BYTES = {}
# JEG-793: on-wire (possibly gzip-compressed) bytes for the same keys. _BYTES
# stays the decoded body size so lines are comparable with the earlier audit;
# wire counts response bodies only, excluding headers and transport overhead.
_WIRE = {}


def _label(path):
    """'/rest/v1/players' -> 'players'; '/rest/v1/rpc/fn' -> 'rpc/fn'."""
    return path.split("/rest/v1/", 1)[-1].split("?", 1)[0]


def _count(method, path, nbytes, wire=None):
    key = (method, _label(path))
    entry = _BYTES.setdefault(key, [0, 0])
    entry[0] += 1
    entry[1] += nbytes
    _WIRE[key] = _WIRE.get(key, 0) + (nbytes if wire is None else wire)


def _decode_body(raw, headers):
    """Transparent gzip decode: returns (decoded_bytes, wire_bytes)."""
    wire = len(raw)
    encoding = ""
    if headers is not None:
        encoding = (headers.get("Content-Encoding") or "").strip().lower()
    if raw and encoding == "gzip":
        raw = gzip.decompress(raw)
    return raw, wire


def bytes_summary_enabled():
    return (os.environ.get("SUPABASE_BYTES_LOG") == "1"
            or os.environ.get("GITHUB_ACTIONS") == "true")


def _ranked():
    return sorted(_BYTES.items(), key=lambda kv: -kv[1][1])


def bytes_summary_lines():
    """Counts plus explicit, allowlisted attribution; caller must be non-secret."""
    who = os.environ.get("GITHUB_WORKFLOW") or "local"
    context = {
        "workflow": who,
        "script": os.path.basename(sys.argv[0] or "python"),
        "caller": os.environ.get("SUPABASE_BYTES_CALLER", ""),
        "run_id": os.environ.get("GITHUB_RUN_ID", ""),
        "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        "job": os.environ.get("GITHUB_JOB", ""),
        # Actions exposes the summary filename, but no native step-id variable.
        "step": os.environ.get("SUPABASE_BYTES_STEP") or
                os.path.basename(os.environ.get("GITHUB_STEP_SUMMARY", "")),
        "at": datetime.now(timezone.utc).isoformat(),
        "event": uuid.uuid4().hex,
    }
    return [f"[supabase-bytes] {who} {m} {t} requests={n} bytes={b}"
            f" wire={_WIRE.get((m, t), b)} context=" + json.dumps(context, ensure_ascii=True)
            for (m, t), (n, b) in _ranked()]


def _emit_bytes_summary():
    if not _BYTES or not bytes_summary_enabled():
        return
    lines = bytes_summary_lines()
    for line in lines:
        print(line, file=sys.stderr)
    who = os.environ.get("GITHUB_WORKFLOW") or "run"
    total = sum(b for _, b in _BYTES.values())
    wire_total = sum(_WIRE.get(k, v[1]) for k, v in _BYTES.items())
    md = [f"#### Supabase response bytes ({who}, decoded total {total:,}, "
          f"on-wire total {wire_total:,})", "",
          "| method | table | requests | bytes | wire |", "|---|---|---:|---:|---:|"]
    for (m, t), (n, b) in _ranked():
        md.append(f"| {m} | {t} | {n} | {b:,} | {_WIRE.get((m, t), b):,} |")
    md += ["", "```text", *lines, "```", ""]
    step = os.environ.get("GITHUB_STEP_SUMMARY")
    if step:
        try:
            with open(step, "a", encoding="utf-8") as fh:
                fh.write("\n".join(md) + "\n")
        except OSError:
            pass
    if os.environ.get("GITHUB_ACTIONS") == "true":
        try:
            directory = Path(os.environ.get("RUNNER_TEMP") or tempfile.gettempdir()) / "supabase-bytes"
            directory.mkdir(exist_ok=True)
            (directory / (uuid.uuid4().hex + ".md")).write_text("\n".join(md), encoding="utf-8")
        except OSError as exc:
            print(f"[supabase-bytes-warning] artifact unavailable: {exc.__class__.__name__}", file=sys.stderr)


atexit.register(_emit_bytes_summary)


class SupabaseError(Exception):
    pass


def _base_url():
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise SupabaseError("SUPABASE_URL not set")
    return url


def _api_key():
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise SupabaseError("SUPABASE_SERVICE_KEY not set")
    return key


def _request(method, path, body=None, params="", prefer="return=representation",
             schema=None):
    url = _base_url() + path + params
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", _api_key())
    req.add_header("Authorization", f"Bearer {_api_key()}")
    req.add_header("Content-Type", "application/json")
    # JEG-793: ask for gzip; decoded transparently below (urllib does not).
    req.add_header("Accept-Encoding", "gzip")
    if schema:
        # PostgREST schema selector for non-public schemas (e.g. api.*).
        req.add_header("Accept-Profile", schema)
        req.add_header("Content-Profile", schema)
    if prefer:
        req.add_header("Prefer", prefer)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        raw, wire = _decode_body(resp.read(), getattr(resp, "headers", None))
        _count(method, path, len(raw), wire)
        if not raw:
            return []
        try:
            return json.loads(raw.decode())
        except json.JSONDecodeError:
            return raw.decode()[:500]
    except urllib.error.HTTPError as e:
        err, wire = _decode_body(e.read(), getattr(e, "headers", None))
        _count(method, path, len(err), wire)
        raise SupabaseError(f"{method} {path}: HTTP {e.code} {err.decode()[:400]}")


def get(table, params="", schema=None):
    return _request("GET", f"/rest/v1/{table}", params=params, prefer="",
                    schema=schema)


def rpc(function, payload, params=""):
    """Call a Postgres function via PostgREST RPC.

    POST /rest/v1/rpc/<function> with a JSON body; returns the decoded
    response. Raises SupabaseError on HTTP errors (the loader treats any
    promote failure as fail-closed).
    """
    return _request("POST", f"/rest/v1/rpc/{function}", body=payload,
                    params=params, prefer="")


def get_all(table, params="", batch=1000):
    """Paginated read past PostgREST's 1000-row cap, with order=id enforced."""
    rows, offset = [], 0
    parts = [p for p in params.lstrip("?").split("&")
             if p and not p.startswith("limit=") and not p.startswith("offset=")]
    if not any(p.startswith("order=") for p in parts):
        parts.append("order=id")
    base = "&".join(parts)
    while True:
        page = _request("GET", f"/rest/v1/{table}",
                        params=f"?{base}&limit={batch}&offset={offset}" if base
                        else f"?limit={batch}&offset={offset}", prefer="")
        rows.extend(page)
        if len(page) < batch:
            return rows
        offset += batch


def post(table, body, params="", prefer="return=representation"):
    return _request("POST", f"/rest/v1/{table}", body=body, params=params,
                    prefer=prefer)


def patch(table, body, params):
    return _request("PATCH", f"/rest/v1/{table}", body=body, params=params)


def delete(table, params):
    return _request("DELETE", f"/rest/v1/{table}", params=params, prefer="")
