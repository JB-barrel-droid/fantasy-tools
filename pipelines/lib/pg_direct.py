"""Direct Postgres hooks for savers when the REST client is unavailable (JEG-621).

The connection URL lives only in the macOS Keychain (account fantasy-tools, service
ddf-supabase-db-url) and is read at runtime. It is never printed, logged or written.
Hooks match the saver signatures: fetch_players(), upsert_rows(table, rows, on_conflict),
count_rows(table, params) where params is the REST-style "?select=id&col=eq.value" string.
"""

from __future__ import annotations

import re
import subprocess
from typing import Any
from urllib.parse import parse_qsl

KEYCHAIN_ACCOUNT = "fantasy-tools"
KEYCHAIN_SERVICE = "ddf-supabase-db-url"
_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")
BATCH = 500


def read_db_url() -> str:
    out = subprocess.run(["security", "find-generic-password", "-a", KEYCHAIN_ACCOUNT, "-s", KEYCHAIN_SERVICE, "-w"],
                         capture_output=True, text=True)
    url = out.stdout.strip()
    if out.returncode != 0 or not url:
        raise SystemExit("Fail closed: database login not found in Keychain "
                         f"(account {KEYCHAIN_ACCOUNT}, service {KEYCHAIN_SERVICE}).")
    return url


def connect():
    import psycopg  # noqa: PLC0415 -- only needed for real saves
    return psycopg.connect(read_db_url(), autocommit=False)


def _ident(name: str) -> str:
    if not _IDENT.match(name):
        raise ValueError(f"unsafe SQL identifier: {name!r}")
    return f'"{name}"'


def fetch_players(connect_fn=connect) -> list[dict[str, Any]]:
    with connect_fn() as conn, conn.cursor() as cur:
        cur.execute("select player_key, full_name, position, active from public.players")
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def upsert_sql(table: str, columns: list[str], on_conflict: str) -> str:
    conflict = [c.strip() for c in on_conflict.split(",")]
    cols = ", ".join(_ident(c) for c in columns)
    marks = ", ".join(["%s"] * len(columns))
    sets = ", ".join(f"{_ident(c)} = excluded.{_ident(c)}" for c in columns if c not in conflict)
    return (f"insert into public.{_ident(table)} ({cols}) values ({marks}) "
            f"on conflict ({', '.join(_ident(c) for c in conflict)}) do update set {sets}")


def upsert_rows(table: str, rows: list[dict[str, Any]], on_conflict: str, connect_fn=connect) -> None:
    if not rows:
        return
    columns = list(rows[0])
    sql = upsert_sql(table, columns, on_conflict)
    with connect_fn() as conn:  # one transaction: all rows land or none
        with conn.cursor() as cur:
            for start in range(0, len(rows), BATCH):
                cur.executemany(sql, [[r.get(c) for c in columns] for r in rows[start:start + BATCH]])
        conn.commit()


def count_sql(table: str, params: str) -> tuple[str, list[str]]:
    where, args = [], []
    for key, val in parse_qsl(params.lstrip("?"), keep_blank_values=True):
        if key == "select":
            continue
        if not val.startswith("eq."):
            raise ValueError(f"unsupported filter {key}={val!r}")
        where.append(f"{_ident(key)} = %s")
        args.append(val[3:])
    sql = f"select count(*) from public.{_ident(table)}" + (" where " + " and ".join(where) if where else "")
    return sql, args


def count_rows(table: str, params: str, connect_fn=connect) -> int:
    sql, args = count_sql(table, params)
    with connect_fn() as conn, conn.cursor() as cur:
        cur.execute(sql, args)
        return int(cur.fetchone()[0])
