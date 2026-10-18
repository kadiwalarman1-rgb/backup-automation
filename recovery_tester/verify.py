from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .exceptions import OperationalError
from .utils import (
    row_count,
    schema_fingerprint,
    sha256_file,
    supported_tables,
    table_content_hash,
    utc_now_iso,
)


def _load_manifest(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.exists():
        raise OperationalError(f"Manifest not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise OperationalError(f"Malformed manifest JSON: {manifest_path}: {err}") from err

    required = {"backup_id", "backup_file", "backup_sha256", "schema_fingerprint", "tables"}
    missing = sorted(required - set(data.keys()))
    if missing:
        raise OperationalError(f"Manifest missing required keys: {', '.join(missing)}")
    if not isinstance(data["tables"], dict):
        raise OperationalError("Manifest field 'tables' must be an object")
    return data


def _evaluate_backup_and_manifest(backup_path: Path, manifest: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    checks.append({"name": "backup_exists", "ok": backup_path.exists(), "detail": str(backup_path)})
    checks.append({"name": "manifest_valid", "ok": True, "detail": "manifest loaded"})

    if backup_path.exists():
        actual_sha = sha256_file(backup_path)
        expected_sha = str(manifest.get("backup_sha256", ""))
        checks.append(
            {
                "name": "backup_checksum",
                "ok": actual_sha == expected_sha,
                "detail": f"expected={expected_sha} observed={actual_sha}",
            }
        )
    else:
        checks.append({"name": "backup_checksum", "ok": False, "detail": "backup file missing"})

    return checks


def restore_backup(backup_path: Path, restore_db_path: Path, timeout_seconds: float = 5.0) -> tuple[bool, str, float]:
    if restore_db_path.exists():
        raise OperationalError(f"Refusing overwrite, restore destination exists: {restore_db_path}")
    restore_db_path.parent.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    src = sqlite3.connect(backup_path, timeout=timeout_seconds)
    try:
        dst = sqlite3.connect(restore_db_path, timeout=timeout_seconds)
        try:
            src.backup(dst)
        except sqlite3.Error as err:
            raise OperationalError(f"Restore failed: {err}") from err
        finally:
            dst.close()
    except sqlite3.OperationalError as err:
        msg = str(err)
        if "database is locked" in msg.lower():
            raise OperationalError(f"Database lock timeout during restore: {msg}") from err
        raise OperationalError(f"Restore operational error: {msg}") from err
    finally:
        src.close()

    ended = time.perf_counter()
    return True, "restored", ended - started


def _run_representative_queries(conn: sqlite3.Connection) -> list[str]:
    q1 = conn.execute(
        """
        SELECT c.region, COUNT(*)
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        GROUP BY c.region
        ORDER BY c.region
        """
    ).fetchall()
    q2 = conn.execute("SELECT COUNT(*) FROM orders WHERE amount > 500").fetchone()
    if not q1 or q2 is None:
        raise OperationalError("Representative query returned empty result unexpectedly")
    return ["orders by region", "high value orders count"]


def verify_restored_db(restored_db: Path, manifest: dict[str, Any]) -> tuple[list[dict[str, Any]], float]:
    checks: list[dict[str, Any]] = []
    started = time.perf_counter()

    if not restored_db.exists():
        raise OperationalError(f"Restored database not found: {restored_db}")

    try:
        conn = sqlite3.connect(restored_db)
    except sqlite3.Error as err:
        raise OperationalError(f"Unable to open restored database: {err}") from err

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        checks.append({"name": "restored_db_opens", "ok": True, "detail": str(restored_db)})

        integrity = conn.execute("PRAGMA integrity_check").fetchone()
        integrity_ok = bool(integrity and integrity[0] == "ok")
        checks.append({"name": "integrity_check", "ok": integrity_ok, "detail": str(integrity[0] if integrity else "")})

        fk_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        checks.append({"name": "foreign_key_check", "ok": len(fk_issues) == 0, "detail": f"violations={len(fk_issues)}"})

        observed_schema = schema_fingerprint(conn)
        expected_schema = str(manifest.get("schema_fingerprint", ""))
        checks.append(
            {
                "name": "schema_fingerprint",
                "ok": observed_schema == expected_schema,
                "detail": f"expected={expected_schema} observed={observed_schema}",
            }
        )

        table_expectations = manifest.get("tables", {})
        for table in supported_tables(conn):
            expected_table = table_expectations.get(table)
            if not isinstance(expected_table, dict):
                checks.append({"name": f"table_{table}_in_manifest", "ok": False, "detail": "table missing from manifest"})
                continue

            observed_count = row_count(conn, table)
            expected_count = int(expected_table.get("row_count", -1))
            checks.append(
                {
                    "name": f"table_{table}_row_count",
                    "ok": observed_count == expected_count,
                    "detail": f"expected={expected_count} observed={observed_count}",
                }
            )

            observed_hash = table_content_hash(conn, table)
            expected_hash = str(expected_table.get("content_hash", ""))
            checks.append(
                {
                    "name": f"table_{table}_content_hash",
                    "ok": observed_hash == expected_hash,
                    "detail": f"expected={expected_hash} observed={observed_hash}",
                }
            )

        query_names = _run_representative_queries(conn)
        checks.append({"name": "representative_queries", "ok": True, "detail": ", ".join(query_names)})
    except sqlite3.OperationalError as err:
        msg = str(err)
        if "database is locked" in msg.lower():
            raise OperationalError(f"Database lock timeout during verification: {msg}") from err
        raise OperationalError(f"Database operational error during verification: {msg}") from err
    finally:
        conn.close()

    ended = time.perf_counter()
    return checks, ended - started


def restore_and_verify(backup_path: Path, manifest_path: Path, restore_dir: Path, timeout_seconds: float = 5.0) -> dict[str, Any]:
    run_started = utc_now_iso()
    manifest = _load_manifest(manifest_path)

    checks = _evaluate_backup_and_manifest(backup_path, manifest)
    restore_db = restore_dir / "restored.sqlite"

    restore_duration = 0.0
    verify_duration = 0.0
    backup_exists = any(check["name"] == "backup_exists" and check["ok"] for check in checks)
    if backup_exists:
        try:
            _, _, restore_duration = restore_backup(backup_path, restore_db, timeout_seconds=timeout_seconds)
            verify_checks, verify_duration = verify_restored_db(restore_db, manifest)
            checks.extend(verify_checks)
        except OperationalError as err:
            if str(err).startswith("Refusing overwrite"):
                raise
            checks.append({"name": "restore_or_verify_error", "ok": False, "detail": str(err)})

    overall_ok = all(check["ok"] for check in checks)
    run_ended = utc_now_iso()

    return {
        "run_started_utc": run_started,
        "run_ended_utc": run_ended,
        "overall_ok": overall_ok,
        "checks": checks,
        "restore_duration_seconds": round(restore_duration, 6),
        "verification_duration_seconds": round(verify_duration, 6),
        "manifest": manifest,
        "restore_db": str(restore_db),
    }


def verify_backup_only(backup_path: Path, manifest_path: Path) -> dict[str, Any]:
    run_started = utc_now_iso()
    manifest = _load_manifest(manifest_path)
    checks = _evaluate_backup_and_manifest(backup_path, manifest)
    return {
        "run_started_utc": run_started,
        "run_ended_utc": utc_now_iso(),
        "overall_ok": all(check["ok"] for check in checks),
        "checks": checks,
        "manifest": manifest,
    }
