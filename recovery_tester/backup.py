from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .exceptions import OperationalError
from .utils import (
    row_count,
    schema_fingerprint,
    sha256_file,
    supported_tables,
    table_content_hash,
    utc_now_iso,
)


def create_backup(source_db: Path, backup_path: Path, backup_id: str) -> tuple[Path, Path, dict]:
    if not source_db.exists():
        raise OperationalError(f"Source database not found: {source_db}")
    if backup_path.exists():
        raise OperationalError(f"Backup destination already exists: {backup_path}")

    backup_path.parent.mkdir(parents=True, exist_ok=True)

    src_conn = sqlite3.connect(source_db)
    try:
        src_conn.execute("PRAGMA foreign_keys = ON")
        dst_conn = sqlite3.connect(backup_path)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    snapshot_conn = sqlite3.connect(backup_path)
    try:
        snapshot_conn.execute("PRAGMA foreign_keys = ON")
        table_data = {}
        for table in supported_tables(snapshot_conn):
            table_data[table] = {
                "row_count": row_count(snapshot_conn, table),
                "content_hash": table_content_hash(snapshot_conn, table),
            }
        manifest = {
            "manifest_version": 1,
            "backup_id": backup_id,
            "created_at_utc": utc_now_iso(),
            "backup_file": backup_path.name,
            "backup_size_bytes": backup_path.stat().st_size,
            "backup_sha256": sha256_file(backup_path),
            "schema_fingerprint": schema_fingerprint(snapshot_conn),
            "supported_schema_types": ["table", "index", "view", "trigger"],
            "supported_table_types": ["table"],
            "tables": table_data,
        }
    finally:
        snapshot_conn.close()

    manifest_path = backup_path.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup_path, manifest_path, manifest
