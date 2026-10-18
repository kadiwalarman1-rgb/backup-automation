from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Any

from .backup import create_backup
from .exceptions import OperationalError
from .sample_data import create_sample_database
from .utils import ensure_dir, new_run_id, utc_now_iso
from .verify import restore_and_verify


def _run_scenario(name: str, backup_path: Path, manifest_path: Path, run_dir: Path, expect_success: bool) -> dict[str, Any]:
    scenario_dir = ensure_dir(run_dir / name)
    try:
        result = restore_and_verify(backup_path, manifest_path, scenario_dir / "restore")
        verification_ok = bool(result["overall_ok"])
        detail = "verification completed"
    except OperationalError as err:
        verification_ok = False
        result = {
            "run_started_utc": utc_now_iso(),
            "run_ended_utc": utc_now_iso(),
            "overall_ok": False,
            "checks": [{"name": "operational_error", "ok": False, "detail": str(err)}],
            "restore_duration_seconds": 0.0,
            "verification_duration_seconds": 0.0,
            "manifest": {},
        }
        detail = str(err)

    expected_outcome_confirmed = verification_ok == expect_success
    return {
        "name": name,
        "expect_success": expect_success,
        "verification_ok": verification_ok,
        "expected_outcome_confirmed": expected_outcome_confirmed,
        "detail": detail,
        "result": result,
    }


def run_demo(artifacts_root: Path, orders: int = 1000, seed: int = 42) -> tuple[dict[str, Any], Path]:
    run_id = f"demo-{new_run_id()}"
    run_dir = ensure_dir(artifacts_root / run_id)

    source_db = run_dir / "source" / "sample.sqlite"
    create_sample_database(source_db, order_count=orders, seed=seed)

    backup_path, manifest_path, _manifest = create_backup(source_db, run_dir / "backup" / "backup.sqlite", backup_id=run_id)

    scenarios: list[dict[str, Any]] = []
    scenarios.append(_run_scenario("healthy_backup", backup_path, manifest_path, run_dir / "scenarios", expect_success=True))

    corrupt_copy = run_dir / "backup" / "backup_truncated.sqlite"
    shutil.copy2(backup_path, corrupt_copy)
    raw = corrupt_copy.read_bytes()
    corrupt_copy.write_bytes(raw[: max(1, len(raw) // 2)])
    scenarios.append(_run_scenario("truncated_copy", corrupt_copy, manifest_path, run_dir / "scenarios", expect_success=False))

    changed_copy = run_dir / "backup" / "backup_data_changed.sqlite"
    shutil.copy2(backup_path, changed_copy)
    conn = sqlite3.connect(changed_copy)
    try:
        conn.execute("UPDATE orders SET amount = amount + 1 WHERE order_id = 1")
        conn.commit()
    finally:
        conn.close()
    scenarios.append(_run_scenario("modified_data_same_rowcount", changed_copy, manifest_path, run_dir / "scenarios", expect_success=False))

    all_expected = all(s["expected_outcome_confirmed"] for s in scenarios)
    report = {
        "run_id": run_id,
        "run_started_utc": scenarios[0]["result"].get("run_started_utc", utc_now_iso()),
        "run_ended_utc": utc_now_iso(),
        "overall_ok": all_expected,
        "checks": scenarios[0]["result"].get("checks", []),
        "restore_duration_seconds": scenarios[0]["result"].get("restore_duration_seconds", 0.0),
        "verification_duration_seconds": scenarios[0]["result"].get("verification_duration_seconds", 0.0),
        "manifest": scenarios[0]["result"].get("manifest", {}),
        "scenarios": [
            {
                "name": s["name"],
                "verification_ok": s["verification_ok"],
                "expected_outcome_confirmed": s["expected_outcome_confirmed"],
                "detail": s["detail"],
            }
            for s in scenarios
        ],
    }

    return report, run_dir
