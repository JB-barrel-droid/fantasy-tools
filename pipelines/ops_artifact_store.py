#!/usr/bin/env python3
"""JEG-414 follow-up: read/write ops artifacts from/to public.ops_artifacts.

Used by health-artifacts.yml (write) and health_artifacts_watch.py (read)
to replace committing JSON blobs to main.

Service-role writes go via SUPABASE_URL + SUPABASE_SERVICE_KEY (in GHA env).
Anon reads go via SUPABASE_URL + SUPABASE_ANON_KEY (in GHA env and browser).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Optional


TABLE = "ops_artifacts"
PIPELINE_CHECKPOINTS = "pipeline-checkpoints"
SOURCE_IMPORT_HEALTH = "source-import-health"
CODE_HASH = "code-hash"


class OpsArtifactError(Exception):
    pass


def _base_url() -> str:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not url:
        raise OpsArtifactError("SUPABASE_URL not set")
    return url


def _service_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise OpsArtifactError("SUPABASE_SERVICE_KEY not set")
    return key


def _anon_key() -> str:
    key = os.environ.get("SUPABASE_ANON_KEY", "")
    if not key:
        raise OpsArtifactError("SUPABASE_ANON_KEY not set")
    return key


def _request(method: str, url: str, body=None, api_key: str = "") -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", api_key)
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")
    req.add_header("Prefer", "return=representation,resolution=merge-duplicates")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        raw = resp.read()
        if not raw:
            return None
        return json.loads(raw.decode())
    except urllib.error.HTTPError as e:
        raise OpsArtifactError(
            f"{method} {url}: HTTP {e.code} {e.read().decode()[:400]}"
        )


def upsert(name: str, payload: dict, produced_at: Optional[datetime] = None) -> None:
    """Upsert an artifact into public.ops_artifacts (requires service_role key).

    Raises OpsArtifactError on failure.
    """
    if produced_at is None:
        produced_at = datetime.now(timezone.utc)
    row = {
        "name": name,
        "payload": payload,
        "produced_at": produced_at.isoformat(),
    }
    url = f"{_base_url()}/rest/v1/{TABLE}"
    _request("POST", url, body=row, api_key=_service_key())


def fetch(name: str, use_service_key: bool = False) -> Optional[dict]:
    """Fetch an artifact payload from public.ops_artifacts.

    Returns the payload dict, or None if not found / unreachable.
    Uses the anon key by default; pass use_service_key=True for CI watch jobs.
    """
    key = _service_key() if use_service_key else _anon_key()
    url = f"{_base_url()}/rest/v1/{TABLE}?name=eq.{name}&select=payload,produced_at"
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Accept", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        rows = json.loads(resp.read().decode())
        if not rows:
            return None
        row = rows[0]
        payload = row.get("payload")
        if not isinstance(payload, dict):
            return None
        # Attach produced_at as a top-level field if not already present
        if "produced_at" not in payload and row.get("produced_at"):
            payload = dict(payload, produced_at=row["produced_at"])
        return payload
    except Exception:
        return None


def fetch_all() -> dict[str, dict]:
    """Fetch all ops artifacts. Returns {name: payload}."""
    key = _service_key()
    url = f"{_base_url()}/rest/v1/{TABLE}?select=name,payload,produced_at"
    req = urllib.request.Request(url, method="GET")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Accept", "application/json")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        rows = json.loads(resp.read().decode())
        result = {}
        for row in rows:
            p = row.get("payload")
            if isinstance(p, dict):
                if "produced_at" not in p and row.get("produced_at"):
                    p = dict(p, produced_at=row["produced_at"])
                result[row["name"]] = p
        return result
    except Exception:
        return {}
