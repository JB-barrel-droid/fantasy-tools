"""JEG-327 contract dump helper.

Dumps the five `api.*` read views to JSON so verify_contract_parity can
compare them against the static artifacts product-data.js reads today.

Designed for dependency injection: dump_views takes a `client` whose
`.select(view, params)` returns the rows for that page. This module knows
nothing about credentials, URL construction, or auth headers; the injected
client owns them.

Sandbox note (do not work around): the sandbox has no sbclient. The
__main__ block below imports sbclient and will fail when run there.
That is expected — Roman runs this against a live Supabase project.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


# Default manifest location, relative to repo root. The dump script reads
# the surface list from the manifest instead of hardcoding the five
# views so a future surface rename only touches the manifest.
DEFAULT_MANIFEST = "pipelines/contract_parity_manifest.json"


def _read_view_list(manifest_path: str) -> list[str]:
    """Read the surface name list from the parity manifest.

    The manifest's `contract` paths follow the convention
    `./dumps/api.<surface>.json`. We derive the fully-qualified view name
    from each entry's name so this module never hardcodes the api schema
    (PostgREST does not expose api.* by default; the dump client must
    know how to reach it).
    """
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    surfaces = manifest.get("surfaces", [])
    return [f"api.{entry['name']}" for entry in surfaces]


def dump_views(client: Any, views: list[str], out_dir: str) -> dict:
    """Dump each view to <out_dir>/api.<surface>.json out.

    Args:
      client: Object with a `.select(view, params)` method returning a
        list of row dicts. The harness does not page (it assumes the
        client handles pagination internally or returns all rows).
      views: Fully-qualified view names (e.g. "api.player_values").
      out_dir: Directory to write the dumps to. Created if missing.

    Returns:
      {<view>: {"path": <written path>, "count": <n>} mapping.
    """
    os.makedirs(out_dir, exist_ok=True)
    result: dict[str, dict] = {}
    for view in views:
        # Convention: bare name is "api.<surface>"; the file on disk is
        # the same string with ".json" appended. The caller is free to
        # pass any view shape.
        rows = client.select(view, {}) or []
        rows_list = [r for r in rows if isinstance(r, dict)]
        out_path = os.path.join(out_dir, f"{view}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(rows_list, f, indent=2, default=str)
            f.write("\n")
        result[view] = {"path": out_path, "count": len(rows_list)}
    return result


def _run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pipelines.dump_contract_views",
        description="Dump api.* contract views to JSON for parity verification.",
    )
    parser.add_argument(
        "--manifest",
        default=DEFAULT_MANIFEST,
        help="Manifest whose surfaces list drives the view set.",
    )
    parser.add_argument(
        "--out-dir",
        default="dumps",
        help="Directory to write the per-view dumps to.",
    )
    args = parser.parse_args(argv)

    # This import is intentionally outside the function body: sbclient
    # is project-local and lives outside this sandbox. Roman runs this
    # against a configured environment; the import will fail here.
    import sbclient  # type: ignore[import-not-found]  # noqa: F401

    views = _read_view_list(args.manifest)
    client = sbclient.Client()
    result = dump_views(client, views, args.out_dir)
    for view, info in result.items():
        print(f"{view}: {info['count']} rows -> {info['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(_run(sys.argv[1:]))