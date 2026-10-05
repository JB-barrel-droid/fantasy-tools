"""JEG-327 contract parity harness.

Compares two JSON dumps row-by-row:
  - one dump from the new api.* contract view (the live contract data)
  - one dump from the static artifact the FE currently reads (product-data.js)

Reads the manifest, runs compare_surface per entry, prints a summary table,
writes a JSON report next to the manifest. Returns 0 iff every entry is
parity_ok, 1 otherwise.

CLI:
  python3 -m pipelines.verify_contract_parity --manifest <json>

No credentials. No network. Pure-file.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any


FLOAT_TOLERANCE = 1e-9


def load_json(path: str) -> dict:
    """Load a JSON dump file. Wraps the open() so callers don't have to.

    The dump files are arbitrary JSON; the harness only inspects the
    top-level structure. Per-surface conventions:
      - list dump:  bare list of row dicts
      - singleton:   {"<key>": <value>, ...}
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _as_list(payload: Any, surface: str) -> list[dict]:
    """Normalize a JSON dump to a list[dict].

    Accepts either a bare list or an object with one of the standard keys:
    rows, data, items. Anything else raises — the harness never invents
    shape.
    """
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for k in ("rows", "data", "items"):
            if k in payload and isinstance(payload[k], list):
                return [r for r in payload[k] if isinstance(r, dict)]
        # Singleton: treat the dict itself as a one-row surface.
        return [payload]
    raise ValueError(
        f"surface {surface!r}: dump is not a list or dict (got {type(payload).__name__})"
    )


def _row_key(row: dict, key_fields: list[str]) -> tuple:
    return tuple(row.get(k) for k in key_fields)


def _values_equal(v1: Any, v2: Any) -> bool:
    """Equality with 1e-9 float tolerance.

    Floats (and ints) are compared with abs(a-b) <= 1e-9. Other types fall
    through to ==. None vs missing-string vs "" are not normalized — the
    contract version is the authority on shape.
    """
    if isinstance(v1, float) or isinstance(v2, float):
        try:
            f1 = float(v1)
            f2 = float(v2)
        except (TypeError, ValueError):
            return v1 == v2
        return abs(f1 - f2) <= FLOAT_TOLERANCE
    if isinstance(v1, (int,)) and isinstance(v2, (int,)):
        return v1 == v2
    return v1 == v2


def compare_surface(
    contract_rows: list[dict],
    static_rows: list[dict],
    key_fields: list[str],
    compare_fields: list[str],
) -> dict:
    """Compare two row sets on the given key + compare fields.

    Returns:
      {
        'matched':           int,            # rows with all compare_fields equal
        'mismatched':        [{key, field, contract, static}],  # wrong values
        'missing_in_contract': [keys],       # in static, not in contract
        'missing_in_static':   [keys],       # in contract, not in static
      }
    Key = tuple of key_fields values for that row.
    """
    c_by_key = {_row_key(r, key_fields): r for r in contract_rows}
    s_by_key = {_row_key(r, key_fields): r for r in static_rows}

    c_keys = set(c_by_key.keys())
    s_keys = set(s_by_key.keys())

    matched = 0
    mismatched: list[dict] = []

    for key in c_keys & s_keys:
        c_row = c_by_key[key]
        s_row = s_by_key[key]
        row_ok = True
        for f in compare_fields:
            v1 = c_row.get(f)
            v2 = s_row.get(f)
            if not _values_equal(v1, v2):
                row_ok = False
                mismatched.append(
                    {
                        "key": key,
                        "field": f,
                        "contract": v1,
                        "static": v2,
                    }
                )
        if row_ok:
            matched += 1

    missing_in_contract = [k for k in sorted(s_keys - c_keys)]
    missing_in_static = [k for k in sorted(c_keys - s_keys)]

    return {
        "matched": matched,
        "mismatched": mismatched,
        "missing_in_contract": missing_in_contract,
        "missing_in_static": missing_in_static,
    }


def check_surface(
    name: str,
    contract_path: str,
    static_path: str,
    key_fields: list[str],
    compare_fields: list[str],
) -> dict:
    """Load both dumps, compare, and wrap with surface-name + parity_ok flag.

    parity_ok = True iff mismatched, missing_in_contract, and
    missing_in_static are all empty. Matched-row count alone is not
    enough — row-set coverage must also agree.
    """
    contract_payload = load_json(contract_path)
    static_payload = load_json(static_path)
    contract_rows = _as_list(contract_payload, name)
    static_rows = _as_list(static_payload, name)
    result = compare_surface(
        contract_rows, static_rows, key_fields, compare_fields
    )
    parity_ok = (
        not result["mismatched"]
        and not result["missing_in_contract"]
        and not result["missing_in_static"]
    )
    return {"surface": name, **result, "parity_ok": parity_ok}


def _print_summary(results: list[dict]) -> None:
    """Print a human-readable parity summary to stdout."""
    header = f"{'surface':<24} {'matched':>8} {'mismatch':>9} {'miss_>_c':>9} {'miss_>_s':>9} {'parity':>7}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['surface']:<24} "
            f"{r['matched']:>8} "
            f"{len(r['mismatched']):>9} "
            f"{len(r['missing_in_contract']):>9} "
            f"{len(r['missing_in_static']):>9} "
            f"{'OK' if r['parity_ok'] else 'FAIL':>7}"
        )


def main(manifest_path: str) -> int:
    """Run check_surface per surface, write report, return 0 iff all OK."""
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    surfaces = manifest.get("surfaces", [])
    if not isinstance(surfaces, list) or not surfaces:
        print(f"manifest {manifest_path!r}: no 'surfaces' entries", file=sys.stderr)
        return 2

    results: list[dict] = []
    for entry in surfaces:
        name = entry["name"]
        result = check_surface(
            name=name,
            contract_path=entry["contract"],
            static_path=entry["static"],
            key_fields=entry["key_fields"],
            compare_fields=entry["compare_fields"],
        )
        results.append(result)

    _print_summary(results)

    report_path = os.path.join(
        os.path.dirname(os.path.abspath(manifest_path)) or ".",
        "contract_parity_report.json",
    )
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump({"results": results}, f, indent=2, default=str)
        f.write("\n")
    print(f"\nreport written: {report_path}")

    all_ok = all(r["parity_ok"] for r in results)
    return 0 if all_ok else 1


def _cli(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="pipelines.verify_contract_parity",
        description="Compare api.* contract dumps against static JSON artifacts.",
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to the parity manifest JSON (see contract_parity_manifest.json).",
    )
    args = parser.parse_args(argv)
    return main(args.manifest)


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))