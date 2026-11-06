#!/usr/bin/env python3
"""Versioned JSON bundles over an object gateway supporting HTTP PUT and GET.

Empty MONITORING_PUBLICATION_URL retains legacy publication. No retries or git
writes. The gateway must persist objects and atomically replace latest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import sys as _sys  # noqa: E402

# `lib` lives in pipelines/; make it importable whatever the CWD, checkout path or
# import order (tests import this module as pipelines.X without pipelines/ on sys.path).
_sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.timestamps import parse_iso_timestamp  # noqa: E402

SCHEMA = 1
HEALTH = ('source-import-health.json', 'pipeline-checkpoints.json')


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def build_bundle(directory):
    objects = {}
    entries = {}
    for name in HEALTH:
        data = json.loads((Path(directory) / name).read_bytes())
        if not isinstance(data, dict):
            raise ValueError(f'{name}: expected JSON object')
        fields = ('checked_at', 'generated_at') if name.startswith('source-') else ('generated_at',)
        stamp = next((data.get(key) for key in fields if data.get(key)), None)
        if not isinstance(stamp, str):
            raise ValueError(f'{name}: missing source timestamp')
        parsed = parse_iso_timestamp(stamp)
        if parsed.tzinfo is None:
            raise ValueError(f'{name}: timestamp must include timezone')
        body = encode(data)
        digest = hashlib.sha256(body).hexdigest()
        key = f'objects/{digest}.json'
        objects[key] = body
        entries[name] = {'key': key, 'sha256': digest, 'source_timestamp': stamp}
    revision = hashlib.sha256(encode(entries)).hexdigest()
    manifest = {'schema_version': SCHEMA, 'revision': revision, 'artifacts': entries}
    objects[f'versions/{revision}.json'] = encode(manifest)
    return objects, manifest


def publish(directory, base_url, put=None):
    objects, manifest = build_bundle(directory)
    parsed = urlsplit(base_url)
    if not (parsed.scheme == 'https' and parsed.hostname or
            parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
        raise ValueError('publication URL must use HTTPS (or local HTTP for simulation)')
    if put is None:
        def put(key, body):
            headers = {'Content-Type': 'application/json'}
            token = os.environ.get('MONITORING_PUBLICATION_TOKEN')
            if token:
                headers['Authorization'] = f'Bearer {token}'
            request = Request(base_url.rstrip('/') + '/v1/health/' + key,
                              data=body, headers=headers, method='PUT')
            with urlopen(request, timeout=30) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError('publication rejected')
    # Every immutable object must arrive before advertising the bundle.
    for key, body in objects.items():
        put(key, body)
    put('latest.json', encode(manifest))
    return manifest


def fetch_artifact(base_url, name, get):
    """Resolve the stable manifest, then verify the immutable object's digest."""
    root = base_url.rstrip('/') + '/v1/health/'
    manifest = json.loads(get(root + 'latest.json'))
    if manifest['schema_version'] != SCHEMA:
        raise ValueError('unsupported monitoring schema')
    entries = manifest['artifacts']
    if hashlib.sha256(encode(entries)).hexdigest() != manifest['revision']:
        raise ValueError('manifest revision mismatch')
    entry = entries[name]
    digest = entry['sha256']
    if entry['key'] != f'objects/{digest}.json' or len(digest) != 64:
        raise ValueError('invalid object key')
    body = get(root + entry['key'])
    if hashlib.sha256(body).hexdigest() != digest:
        raise ValueError('monitoring object digest mismatch')
    return json.loads(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default='output')
    args = parser.parse_args()
    base = os.environ.get('MONITORING_PUBLICATION_URL', '')
    if not base:
        parser.error('MONITORING_PUBLICATION_URL is required')
    manifest = publish(args.directory, base)
    print(f"Published health revision {manifest['revision']}")


if __name__ == '__main__':
    main()
