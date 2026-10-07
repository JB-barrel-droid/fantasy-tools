"""Pick the freshest usable midweek leg file per scoring.

Preference order (2026-09-16):
  1. newest valid reassessed_values_<date>_<scoring>.json
     ("valid" = reassessed_values_<date>_audit.json exists and the scoring's
     status is "ok" - a fail-closed no-op never feeds a dashboard)
  2. newest dated current_values_<date>_<scoring>.json
  3. imputed_proj_<scoring>.json (Monday market step)

All three share the imputed-record shape (proj_pg / mult / debug.edge),
so downstream pricing code needs no changes - only the file choice.
"""

import json
import re
from pathlib import Path

_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def _dated(res, stem, scoring):
    """Newest-first list of dates having res/<stem>_<date>_<scoring>.json."""
    dates = set()
    for p in res.glob(f"{stem}_*_{scoring}.json"):
        m = _DATE_RE.search(p.name)
        if m:
            dates.add(m.group(1))
    return sorted(dates, reverse=True)


def pick_leg_file(res_dir, scoring):
    """Return (path, label) for the leg file to price.

    label is "reassessed:<date>", "current:<date>" or "monday".
    """
    res = Path(res_dir)
    try:
        for d in _dated(res, "reassessed_values", scoring):
            try:
                audit = json.loads(
                    (res / f"reassessed_values_{d}_audit.json").read_text())
            except OSError:
                continue
            if (audit.get(scoring) or {}).get("status") == "ok":
                return (res / f"reassessed_values_{d}_{scoring}.json",
                        f"reassessed:{d}")
        for d in _dated(res, "current_values", scoring):
            return (res / f"current_values_{d}_{scoring}.json",
                    f"current:{d}")
    except OSError:
        pass
    return res / f"imputed_proj_{scoring}.json", "monday"


def load_leg(res_dir, scoring):
    """Load the picked leg file. Returns (records, label)."""
    path, label = pick_leg_file(res_dir, scoring)
    return json.loads(path.read_text()), label
