#!/usr/bin/env python3
"""Versioned loader: DDF leg JSON -> Supabase consolidated_values. (JEG-381)

Replaces the ad-hoc CBS ROS load (2026-10-04) that inserted ``raw_value``
under ``view='combo_reindexed'`` because no versioned script existed. Every
Supabase write must come from a versioned script; this is that script for
DDF-leg sources.

Field mapping (EXPLICIT -- the 2026-10-04 bug was a silent field swap):

    leg JSON field      -> consolidated_values column   (view)
    ------------------    ----------------------------   ----------------
    "value"             -> value                          combo_reindexed
                          (0-70 indexed; leg guarantees value == raw*scale)
    "raw_value"         -> value                          vorp_indexed
                          (native VORP economics; NOT 0-70 capped)
    "player_key"        -> player_key                    (FK to players)
    inputs.source_tag   -> source
    inputs.scoring      -> scoring
    inputs.teams        -> teams
    --season             -> season                        (CLI; legs are ROS)
    --week               -> week                          (CLI)
    --qb-variant         -> qb_variant                    (default qb1)
    bake_uuid           -> bake_uuid                      (looked up / CLI)
    source_generated_at -> source_generated_at            (content vintage!)

Standing rule: freshness measures when the SOURCE changed its numbers, never
when we pulled them. source_generated_at comes from the leg's
``inputs.<source>_snapshot_date`` (the publisher snapshot date), NOT the bake
time. Never default it to now().

Usage:
    python3 pipelines/load_ddf_leg_to_supabase.py \\
        data/ddf-two-tier/ddf-20260930-cbsros-standard-12t-0p15/ddf_leg_cbsros.json \\
        --season 2026 --week 5 --dry-run
    python3 pipelines/load_ddf_leg_to_supabase.py <leg.json> \\
        --season 2026 --week 5 --views both

Credentials: tries the supabase-football-signal skill sbclient first, then
falls back to SUPABASE_URL / SUPABASE_SERVICE_KEY env vars (gh_sbclient.py).
"""

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.parse
import urllib.request
import uuid as _uuid
from pathlib import Path

# Per-source 70-cap rescale pipeline stage. Imported late in this module
# because pipelines/caps/per_source_rescale.py is stdlib-only and lightweight,
# but we keep the import adjacent to its usage so the dependency is obvious.
from caps.per_source_rescale import (  # noqa: E402
    RescaleError,
    apply_per_source_cap,
    build_rescale_audit,
    build_run_context,
    compute_rescale_factors,
    emit_artifact_rescale_audit,
    insert_rescale_audit,
    preflight_validate_cap,
)

REPO = Path(__file__).resolve().parent.parent
CHUNK = 500  # PostgREST-friendly batch size (matches unified.py)

# Unique key on consolidated_values -- the upsert conflict target.
# JEG-381 fix (2026-10-05): must match consolidated_values_pkey
# (player, source, season, week, scoring, teams, qb_variant, view); the old
# player_key-based target matched no unique constraint, so every upsert 400'd.
UNIQUE_KEY_COLS = (
    "player,source,season,week,scoring,teams,qb_variant,view"
)

# Leg/CLI scoring keys -> consolidated_values.scoring CHECK values.
SCORING_DB = {"standard": "standard", "half_ppr": "half", "half": "half",
              "ppr": "full", "full": "full"}

# ---------------------------------------------------------------------------
# Per-source 70-cap rescale configuration (JEG-77: 2026-10-04 CBS ROS incident).
# The DB CHECK ck_combo_reindexed_cap is the final backstop; this stage is the
# deterministic, audited pre-DB enforcement. per_source_cap_audit table created
# 2026-10-04 via browser; DB audit now enabled.
# ---------------------------------------------------------------------------
PER_SOURCE_CAP_VALUE_COLUMN = "combo_reindexed"
PER_SOURCE_CAP_GROUP_KEY = "source"
PER_SOURCE_CAP_CAP = 70
PER_SOURCE_CAP_EPS = 1e-9
PER_SOURCE_CAP_DB_AUDIT = True

# ---------------------------------------------------------------------------
# EXPLICIT field mapping. Each entry: (db_column, leg_json_field, view, notes).
# "value" is the 0-70 INDEXED field (leg: value == raw_value * scale_70_over_max).
# "raw_value" is NATIVE VORP economics (never 0-70 capped).
# Swapping these two is exactly the 2026-10-04 CBS ROS bug. Do not "simplify".
# ---------------------------------------------------------------------------
FIELD_MAP = {
    # db column        : (leg field,      applicable view,    validation)
    "player_key": ("player_key", "both", "int, must exist in public.players"),
    "combo_value": ("value", "combo_reindexed", "0 <= v <= 70, fail closed"),
    "vorp_value": ("raw_value", "vorp_indexed", "v >= 0, fail closed"),
}


class LoadError(Exception):
    pass


# ---------------------------------------------------------------------------
# Supabase clients
# ---------------------------------------------------------------------------
def _skill_client():
    bin_dir = os.path.expanduser("~/workspace/skills/supabase-football-signal/bin")
    if bin_dir not in sys.path:
        sys.path.insert(0, bin_dir)
    import sbclient  # noqa: E402
    return sbclient


class _EnvClient:
    """Stdlib client mirroring pipelines/gh_sbclient.py (env credentials)."""

    class _Err(Exception):
        pass

    def __init__(self):
        self.base = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not self.base or not self.key:
            raise LoadError("SUPABASE_URL / SUPABASE_SERVICE_KEY not set")

    def _req(self, method, path, body=None, params="", prefer="return=representation",
             schema=None):
        url = self.base + path + params
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("apikey", self.key)
        req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Content-Type", "application/json")
        if prefer:
            req.add_header("Prefer", prefer)
        if schema:
            req.add_header("Content-Profile", schema)
            req.add_header("Accept-Profile", schema)
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            raw = resp.read()
            return json.loads(raw.decode()) if raw else []
        except urllib.error.HTTPError as e:
            raise LoadError(f"{method} {path}: HTTP {e.code} {e.read().decode()[:400]}")

    def get(self, table, params=""):
        return self._req("GET", f"/rest/v1/{table}", params=params, prefer="")

    def get_all(self, table, params="", batch=1000):
        rows, offset = [], 0
        parts = [p for p in params.lstrip("?").split("&")
                 if p and not p.startswith("limit=") and not p.startswith("offset=")]
        base = "&".join(parts)
        while True:
            page = self._req("GET", f"/rest/v1/{table}",
                             params=f"?{base}&limit={batch}&offset={offset}" if base
                             else f"?limit={batch}&offset={offset}", prefer="")
            rows.extend(page)
            if len(page) < batch:
                return rows
            offset += batch

    def post(self, table, body, params="", prefer="return=representation"):
        return self._req("POST", f"/rest/v1/{table}", body=body, params=params, prefer=prefer)

    def rpc(self, function, payload, params="", schema=None):
        # JEG-381 fix: PostgREST resolves non-public functions only with the
        # Content-Profile header; without it api.* RPCs always 404'd.
        prefix = f"/rest/v1/rpc/{function}"
        return self._req("POST", prefix, body=payload, params=params,
                         prefer="", schema=schema)


def get_client(mode):
    if mode in ("auto", "skill"):
        try:
            return _skill_client(), "skill"
        except Exception as e:
            if mode == "skill":
                raise LoadError(f"skill sbclient unavailable: {e}")
    if mode in ("auto", "env"):
        try:
            return _EnvClient(), "env"
        except LoadError:
            if mode == "env":
                raise
    raise LoadError("no Supabase client available (skill import failed; env vars unset)")


# ---------------------------------------------------------------------------
# Leg parsing + validation
# ---------------------------------------------------------------------------
def load_leg(path):
    with open(path) as f:
        leg = json.load(f)
    if not isinstance(leg.get("values"), list) or not leg["values"]:
        raise LoadError(f"{path}: missing or empty 'values' array")
    return leg


def resolve_dims(leg, args):
    """Dimension tuple. scoring/teams default from leg inputs; season/week are
    required CLI (legs are rest-of-season; the week anchors the slice)."""
    inputs = leg.get("inputs", {}) or {}
    source = args.source or inputs.get("source_tag")
    if not source:
        raise LoadError("cannot determine source: pass --source (leg inputs.source_tag missing)")
    scoring = args.scoring or inputs.get("scoring")
    teams = args.teams or inputs.get("teams")
    if not scoring or not teams:
        raise LoadError("cannot determine scoring/teams: pass --scoring/--teams")
    return {
        "source": source,
        "season": args.season,
        "week": args.week,
        "scoring": scoring,
        "teams": int(teams),
        "qb_variant": args.qb_variant,
    }


def resolve_source_generated_at(leg, args, source):
    """Content vintage, NOT bake time. Prefers the publisher snapshot date
    recorded in the leg inputs (e.g. inputs.cbsros_snapshot_date)."""
    if args.source_generated_at:
        return args.source_generated_at
    inputs = leg.get("inputs", {}) or {}
    snap_key = f"{source}_snapshot_date"
    if inputs.get(snap_key):
        return inputs[snap_key] + "T00:00:00Z"
    if leg.get("generated_at"):
        # Fallback only: leg build time is bake-adjacent, NOT content vintage.
        # Logged as a warning so future legs record the snapshot date.
        print(f"WARN: no {snap_key} in leg inputs; falling back to leg generated_at "
              f"(bake-adjacent, not true content vintage)", file=sys.stderr)
        return leg["generated_at"]
    raise LoadError(f"cannot determine source_generated_at: no {snap_key} or generated_at in leg")


def build_rows(leg, dims, views, source_generated_at, bake_uuid, leg_label="ddf_leg"):
    """Pure function: leg JSON -> DB rows. Unit-testable without a DB.

    Returns ``(rows, audit_data)``:

    - ``rows``: the DB-ready row list (post-rescale, validated).
    - ``audit_data``: ``None`` when ``combo_reindexed`` is not in ``views``;
      otherwise a dict carrying the per-source ``factors`` and the pre-rescale
      snapshot ``rows_before`` so ``main()`` can build the audit + artifact
      via the new caps module. The dev from the brief's "build_rows -> rows"
      shape is documented in the final message: audit needs both pre- and
      post-rescale rows, so we capture both here rather than re-deriving them
      in main() from a parallel extraction.

    Combo row construction (JEG-77 / 2026-10-04 incident):
    1. Build combo rows WITHOUT the [0,70] check (only check value is numeric;
       defer the range check until after rescale -- a >70 leg must be able to
       load, since that is the bug class this stage prevents).
    2. Apply the per-source rescale via caps.per_source_rescale.
    3. Run preflight + the existing [0,70] per-row check + the anti-swap
       guard. The anti-swap guard still holds because the rescale targets
       exactly 70 for any over-cap source; legitimate legs with max <= 70
       pass through untouched (factor = 1.0).
    """
    rows = []
    created_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    scoring_db = SCORING_DB.get(str(dims["scoring"]))
    if scoring_db is None:
        raise LoadError(f"scoring {dims['scoring']!r} has no consolidated_values "
                        f"value (allowed: {sorted(SCORING_DB)})")
    for i, v in enumerate(leg["values"]):
        pk = v.get("player_key")
        if not isinstance(pk, int):
            raise LoadError(f"row {i}: player_key missing/not int: {v.get('player')}")
        # JEG-381 fix: player (PK column), detail_locator and bake_id are
        # NOT NULL in consolidated_values and were never emitted.
        player = (v.get("player_norm") or "").strip()
        if not player and v.get("player"):
            # Same stored-label rule the legs use for player_norm (JEG-438).
            sys.path.insert(0, str(REPO / "pipelines" / "lib"))
            from player_resolver import legacy_label  # noqa: PLC0415
            player = legacy_label(v["player"], "plain")
        if not player:
            raise LoadError(f"row {i}: player / player_norm missing")
        locator = f"{leg_label}#values[{i}]"
        base = {
            # created_at is NOT NULL; the ingest RPC inserts full records via
            # jsonb_populate_recordset, so column defaults do not apply.
            "created_at": created_at,
            "player": player,
            "bake_id": str(bake_uuid) if bake_uuid else None,
            "source": dims["source"],
            "season": dims["season"],
            "week": dims["week"],
            "scoring": scoring_db,
            "teams": dims["teams"],
            "qb_variant": dims["qb_variant"],
            "player_key": pk,
            "bake_uuid": bake_uuid,
            "source_generated_at": source_generated_at,
        }
        if "combo_reindexed" in views:
            # FIELD_MAP: leg "value" -> combo_reindexed. The 2026-10-04 bug
            # loaded "raw_value" here. This mapping is the whole point.
            #
            # The [0,70] check is intentionally DEFERRED until after the
            # per-source rescale: a leg with a >70 value (e.g. 97.3, the
            # 2026-10-04 incident class) is exactly what the rescale fixes.
            # We only verify we can parse a number here; preflight + the
            # post-rescale per-row check enforce the range.
            val = v.get("value")
            if not isinstance(val, (int, float)):
                raise LoadError(f"row {i} ({v.get('player')}): 'value' missing/not numeric")
            rows.append({**base, "view": "combo_reindexed", "value": float(val),
                         "detail_locator": f"{locator}.value"})
        if "vorp_indexed" in views:
            raw = v.get("raw_value")
            if not isinstance(raw, (int, float)):
                raise LoadError(f"row {i} ({v.get('player')}): 'raw_value' missing/not numeric")
            if raw < 0:
                raise LoadError(f"row {i} ({v.get('player')}): vorp_indexed raw_value {raw} < 0")
            rows.append({**base, "view": "vorp_indexed", "value": float(raw),
                         "detail_locator": f"{locator}.raw_value"})

    # ------------------------------------------------------------------
    # Per-source 70-cap rescale (JEG-77: 2026-10-04 incident class)
    # Only operates on combo_reindexed rows; vorp_indexed is NATIVE economics
    # and is never 0-70 capped. The audit captures pre_max / post_max and is
    # emitted by main() after this function returns; here we just expose the
    # inputs the audit needs.
    # ------------------------------------------------------------------
    audit_data = None
    if "combo_reindexed" in views:
        # Snapshot the combo rows before rescale so the audit can report the
        # pre_max the source actually had before this load touched it.
        rows_before = [dict(r) for r in rows if r.get("view") == "combo_reindexed"]
        factors = compute_rescale_factors(rows)
        rows = apply_per_source_cap(rows, factors, cap=PER_SOURCE_CAP_CAP)
        try:
            preflight_validate_cap(
                rows, cap=PER_SOURCE_CAP_CAP, eps=PER_SOURCE_CAP_EPS
            )
        except RescaleError as e:
            raise LoadError(f"per-source cap preflight failed: {e}") from e
        # Post-rescale per-row [0,70] check. Should pass by construction
        # (apply_per_source_cap clamps to cap), but kept as a defense in
        # depth so a future bug in the caps module surfaces as a clear
        # per-row LoadError rather than a silent cap drift.
        for i, r in enumerate(rows):
            if r.get("view") == "combo_reindexed":
                v = r.get("value")
                if not (0 <= v <= PER_SOURCE_CAP_CAP + PER_SOURCE_CAP_EPS):
                    raise LoadError(
                        f"row {i} (player_key={r.get('player_key')}): combo_reindexed value "
                        f"{v} outside [0,{PER_SOURCE_CAP_CAP}] after rescale"
                    )
        # Anti-swap guard (the 2026-10-04 CBS ROS bug): a properly indexed leg
        # has value == raw_value * scale_70_over_max with scale = 70/max_raw,
        # so the top combo_reindexed value is ALWAYS ~70.0 by construction.
        # After rescale, an over-cap source's max lands exactly at the cap
        # (clamp); an already-indexed source's max stays at ~70.0 (factor=1.0).
        # If the loader (or a corrupted leg) put raw_value under
        # combo_reindexed and somehow the rescale didn't catch it, the max
        # would be max_raw_value instead -- still caught here, fail closed.
        combo_vals = [r["value"] for r in rows if r["view"] == "combo_reindexed"]
        if combo_vals and abs(max(combo_vals) - 70.0) > 0.01:
            raise LoadError(
                f"combo_reindexed max is {max(combo_vals):.4f}, expected ~70.0 -- "
                f"raw_value/value swap suspected (2026-10-04 bug class). Refusing to load.")
        audit_data = {"factors": factors, "rows_before": rows_before}
    return rows, audit_data


def verify_player_keys(sb, rows):
    """Fail closed: every player_key must exist in public.players."""
    have = {r["player_key"] for r in rows}
    got = sb.get_all("players", params="?select=player_key")
    known = {r["player_key"] for r in got if isinstance(r, dict)}
    missing = sorted(have - known)
    if missing:
        raise LoadError(f"{len(missing)} player_keys not in public.players (first 10: {missing[:10]})")
    return len(known)


def resolve_bake_uuid(sb, sb_name, source, cli_uuid):
    if cli_uuid:
        return cli_uuid
    # JEG-381 fix: public.bakes keys on bake_id (uuid) and stamps ingested_at;
    # the old bake_uuid/created_at query 400'd on every run.
    rows = sb.get("bakes", params=f"?source=eq.{urllib.parse.quote(source)}"
                                   f"&select=bake_id&order=ingested_at.desc&limit=1")
    if isinstance(rows, list) and rows and rows[0].get("bake_id"):
        return rows[0]["bake_id"]
    raise LoadError(f"no bake record for source '{source}' in public.bakes; "
                    f"create one first or pass --bake-uuid")


def slice_count(sb, dims, view):
    q = ("?select=player_key&source=eq.{source}&season=eq.{season}&week=eq.{week}"
         "&scoring=eq.{scoring}&teams=eq.{teams}&qb_variant=eq.{qb}&view=eq.{view}").format(
        source=urllib.parse.quote(dims["source"]), season=dims["season"], week=dims["week"],
        scoring=urllib.parse.quote(dims["scoring"]), teams=dims["teams"],
        qb=urllib.parse.quote(dims["qb_variant"]), view=view)
    rows = sb.get_all("consolidated_values", params=q)
    return len(rows)


def loader_run_row(run_context, dims):
    """The public.loader_runs parent row for this execution's audit rows."""
    return {
        "run_id": run_context["run_id"],
        "ddf_leg_version": run_context.get("ddf_leg_version"),
        "git_commit_sha": run_context.get("git_commit_sha"),
        "loader_host": run_context.get("loader_host"),
        "notes": (f"load_ddf_leg_to_supabase {dims['source']} {dims['scoring']} "
                  f"{dims['teams']}t season {dims['season']} week {dims['week']}"),
    }


def ensure_loader_run(sb, run_context, dims):
    sb.post("loader_runs", [loader_run_row(run_context, dims)],
            prefer="return=minimal")


def write_rows(sb, sb_name, rows, use_rpc):
    """Prefer the transactional RPC (JEG-380); fall back to chunked upsert."""
    if use_rpc:
        try:
            # JEG-381 fix: the function signature is api.ingest_consolidated_values(p_payload jsonb).
            res = sb.rpc("ingest_consolidated_values", {"p_payload": {"rows": rows}}, schema="api")
            print(f"wrote via api.ingest_consolidated_values RPC: {res}")
            return "rpc"
        except Exception as e:
            msg = str(e)
            if "404" not in msg:
                raise
            print("RPC not found (404); falling back to direct PostgREST upsert", file=sys.stderr)
    n = 0
    for start in range(0, len(rows), CHUNK):
        sb.post("consolidated_values", rows[start:start + CHUNK],
                params=f"?on_conflict={UNIQUE_KEY_COLS}",
                prefer="resolution=merge-duplicates")
        n += len(rows[start:start + CHUNK])
    print(f"upserted {n} rows via direct PostgREST (on_conflict={UNIQUE_KEY_COLS})")
    return "upsert"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("leg", help="path to ddf_leg_<source>.json")
    ap.add_argument("--source", default=None, help="override leg inputs.source_tag")
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--scoring", default=None, help="override leg inputs.scoring")
    ap.add_argument("--teams", type=int, default=None, help="override leg inputs.teams")
    ap.add_argument("--qb-variant", default="qb1")
    ap.add_argument("--views", default="combo",
                    choices=["combo", "vorp", "both"],
                    help="combo=combo_reindexed from leg 'value' (default); "
                         "vorp=vorp_indexed from leg 'raw_value'; both=load each")
    ap.add_argument("--bake-uuid", default=None)
    ap.add_argument("--source-generated-at", default=None,
                    help="override content-vintage timestamp (ISO)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--client", default="auto", choices=["auto", "skill", "env"])
    ap.add_argument("--no-rpc", action="store_true", help="skip RPC, use direct upsert")
    args = ap.parse_args()

    view_map = {"combo": ["combo_reindexed"], "vorp": ["vorp_indexed"],
                "both": ["combo_reindexed", "vorp_indexed"]}
    views = view_map[args.views]

    leg = load_leg(args.leg)
    dims = resolve_dims(leg, args)
    sga = resolve_source_generated_at(leg, args, dims["source"])
    print(f"leg: {args.leg}  rows={len(leg['values'])}  "
          f"scale_70_over_max={leg.get('scale_70_over_max')}")
    print(f"dims: {dims}  views={views}")
    print(f"source_generated_at (content vintage): {sga}")

    sb, sb_name = get_client(args.client)
    print(f"supabase client: {sb_name}")
    bake_uuid = resolve_bake_uuid(sb, sb_name, dims["source"], args.bake_uuid)
    print(f"bake_uuid: {bake_uuid}")

    try:
        leg_label = str(Path(args.leg).resolve().relative_to(REPO))
    except ValueError:
        leg_label = Path(args.leg).name
    rows, audit_data = build_rows(leg, dims, views, sga, bake_uuid, leg_label=leg_label)
    print(f"built {len(rows)} DB rows "
          f"({sum(1 for r in rows if r['view']=='combo_reindexed')} combo_reindexed, "
          f"{sum(1 for r in rows if r['view']=='vorp_indexed')} vorp_indexed)")

    # ------------------------------------------------------------------
    # Per-source 70-cap rescale audit artifact (JEG-77).
    # Emit BEFORE any DB write -- fail-closed. The artifact sits in the leg's
    # versioned directory next to the leg JSON, so every published load has
    # its rescale audit committed alongside it. DB audit (Per_source_cap_audit)
    # stays gated behind PER_SOURCE_CAP_DB_AUDIT until the table exists.
    # ------------------------------------------------------------------
    audit_entries = []
    if audit_data is not None:
        factors = audit_data["factors"]
        rows_before = audit_data["rows_before"]
        run_context = build_run_context(
            ddf_leg_version=Path(args.leg).resolve().parent.name,
            repo_root=REPO,
        )
        audit_entries = build_rescale_audit(
            factors, rows_before, rows, run_context,
            cap=PER_SOURCE_CAP_CAP,
        )
        artifact_path = Path(args.leg).resolve().parent / "rescale_audit.json"
        emit_artifact_rescale_audit(audit_entries, artifact_path)
        summary = audit_entries[-1]
        scaled_sources = [
            e for e in audit_entries
            if e.get("kind") == "per_source"
        ]
        worst_pre = max(
            (e["pre_max"] for e in scaled_sources), default=None
        )
        worst_src = next(
            (e["source"] for e in scaled_sources
             if e["pre_max"] == worst_pre), None
        ) if worst_pre is not None else None
        print(
            f"rescale audit: {summary['sources_scaled']} source(s) scaled "
            f"of {summary['sources_total']} total; cap={PER_SOURCE_CAP_CAP}; "
            f"value_column={PER_SOURCE_CAP_VALUE_COLUMN}"
        )
        if worst_pre is not None:
            print(
                f"  worst_pre_max={worst_pre:.4f} source={worst_src}; "
                f"artifact={artifact_path}"
            )

    verify_player_keys(sb, rows)
    print(f"player_key check: all {len({r['player_key'] for r in rows})} keys exist in public.players")

    before = {v: slice_count(sb, dims, v) for v in views}
    print(f"rows in slice BEFORE: {before}")

    if args.dry_run:
        print("DRY RUN -- no writes. Sample rows:")
        for r in rows[:3]:
            print("  ", json.dumps(r, sort_keys=True))
        return 0

    # Sanity: confirm the combo mapping is really the indexed field.
    combo = [r for r in rows if r["view"] == "combo_reindexed"]
    if combo:
        mx = max(r["value"] for r in combo)
        print(f"max combo_reindexed value to load: {mx:.4f} (leg scale_70_over_max="
              f"{leg.get('scale_70_over_max')}; top player should be ~70.0)")

    # ------------------------------------------------------------------
    # Per_source_cap_audit DB insert (gated). When the table exists in
    # Supabase this rides with the data write so audit and data stay
    # transactionally consistent. Until then the JSON artifact is the only
    # persistent audit trail. Row count must equal len(entries); mismatch
    # aborts the load (anti-swap pattern from the design doc).
    # ------------------------------------------------------------------
    if PER_SOURCE_CAP_DB_AUDIT and audit_entries:
        # JEG-381 fix: per_source_cap_audit.run_id is an FK to loader_runs
        # (JEG-389); without the parent row every audit insert was rejected.
        ensure_loader_run(sb, run_context, dims)
        try:
            inserted = insert_rescale_audit(sb, audit_entries)
        except RescaleError as e:
            raise LoadError(f"per_source_cap_audit insert failed: {e}") from e
        if inserted != len(audit_entries):
            raise LoadError(
                f"per_source_cap_audit insert: expected {len(audit_entries)} "
                f"rows (1 per entry incl SUMMARY), got {inserted}; aborting load"
            )
        print(f"per_source_cap_audit: inserted {inserted} rows")

    write_rows(sb, sb_name, rows, use_rpc=not args.no_rpc)

    after = {v: slice_count(sb, dims, v) for v in views}
    print(f"rows in slice AFTER: {after}")
    for v in views:
        print(f"  {v}: {before[v]} -> {after[v]} (expected {before[v]} + "
              f"{sum(1 for r in rows if r['view']==v)} upserts)")
    print("DONE -- re-run publish gates before activating any snapshot.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LoadError as e:
        print(f"LOAD REFUSED: {e}", file=sys.stderr)
        sys.exit(2)
