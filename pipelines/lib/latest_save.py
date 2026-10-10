"""One snapshot date = one save (GAP-RAZZBALL-CHART-BEHIND-STORED, 2026-10-09).

Razzball re-saves the same snapshot date in place when the
publisher updates the same day: the saver upserts on (player_key, date). A
player the publisher dropped between two saves keeps its row from the earlier
save, so the stored date mixes two pulls: on 2026-10-08 Kaytron Allen and
Emari Demercado (19:26 save) sat beside the 03:25 save's 688 rows, the saver's
own count check failed (690 vs 688) after the upsert had already landed, and
the chain imported all 690 under the new snapshot id.

Every row of one save carries the save's single ``pulled_at``, so the newest
save is the rows with the newest ``pulled_at``; older rows are superseded.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _ts(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def latest_save_rows(rows: list[dict], stamp_key: str = "pulled_at") -> tuple[list[dict], list[dict]]:
    """(rows of the newest save, superseded rows) for one snapshot date.

    Rows without a readable stamp are superseded when any row has one; when
    none has one (rows saved before the stamp existed), nothing is dropped.
    """
    stamps = [_ts(r.get(stamp_key)) for r in rows]
    known = [s for s in stamps if s is not None]
    if not known:
        return list(rows), []
    newest = max(known)
    keep, dropped = [], []
    for row, stamp in zip(rows, stamps):
        (keep if stamp == newest else dropped).append(row)
    return keep, dropped
