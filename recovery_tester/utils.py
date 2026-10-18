from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SUPPORTED_TABLE_TYPES = {"table"}
SUPPORTED_SCHEMA_PREFIXES = ("sqlite_",)


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def new_run_id() -> str:
    return uuid.uuid4().hex[:12]


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def schema_sql(conn: sqlite3.Connection) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        """
        SELECT type, name, COALESCE(sql, '')
        FROM sqlite_master
        WHERE type IN ('table', 'index', 'view', 'trigger')
        AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    ).fetchall()
    return [(str(r[0]), str(r[1]), str(r[2])) for r in rows]


def schema_fingerprint(conn: sqlite3.Connection) -> str:
    payload = json.dumps(schema_sql(conn), separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def supported_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(r[0]) for r in rows]


def row_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def _pk_order_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    pks = sorted((row for row in info if int(row[5]) > 0), key=lambda row: int(row[5]))
    if pks:
        return [str(row[1]) for row in pks]
    return [str(row[1]) for row in info]


def _encode_value(value: Any) -> str:
    if value is None:
        return "N:null"
    if isinstance(value, bool):
        return f"I:{int(value)}"
    if isinstance(value, int):
        return f"I:{value}"
    if isinstance(value, float):
        return f"F:{value:.17g}"
    if isinstance(value, bytes):
        return f"B:{value.hex()}"
    return f"S:{json.dumps(str(value), ensure_ascii=False)}"


def table_content_hash(conn: sqlite3.Connection, table: str) -> str:
    columns = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]
    order_cols = _pk_order_columns(conn, table)
    order_by = ", ".join([f'"{col}"' for col in order_cols])
    col_select = ", ".join([f'"{col}"' for col in columns])
    rows = conn.execute(f'SELECT {col_select} FROM "{table}" ORDER BY {order_by}').fetchall()

    digest = hashlib.sha256()
    digest.update(("|".join(columns)).encode("utf-8"))
    for row in rows:
        encoded = "|".join(_encode_value(value) for value in row)
        digest.update(encoded.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()
