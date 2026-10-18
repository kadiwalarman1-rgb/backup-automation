from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from recovery_tester.backup import create_backup
from recovery_tester.demo import run_demo
from recovery_tester.exceptions import OperationalError
from recovery_tester.sample_data import create_sample_database
from recovery_tester.verify import restore_and_verify, verify_backup_only


def test_successful_backup_restore_and_verify(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=50, seed=7)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    result = restore_and_verify(backup, manifest, tmp_path / "restore")
    assert result["overall_ok"] is True
    assert all(check["ok"] for check in result["checks"])


def test_truncated_backup_rejected(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=40, seed=7)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    corrupt = tmp_path / "truncated.sqlite"
    raw = backup.read_bytes()
    corrupt.write_bytes(raw[: len(raw) // 2])

    result = verify_backup_only(corrupt, manifest)
    assert result["overall_ok"] is False


def test_modified_data_same_rowcount_detected(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=40, seed=7)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    tampered = tmp_path / "tampered.sqlite"
    tampered.write_bytes(backup.read_bytes())
    conn = sqlite3.connect(tampered)
    try:
        conn.execute("UPDATE orders SET amount = amount + 0.5 WHERE order_id = 1")
        conn.commit()
    finally:
        conn.close()

    result = restore_and_verify(tampered, manifest, tmp_path / "restore")
    hash_checks = [c for c in result["checks"] if c["name"].endswith("content_hash")]
    assert any(not c["ok"] for c in hash_checks)


def test_schema_mismatch_detection(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=20, seed=2)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    tampered = tmp_path / "tampered_schema.sqlite"
    tampered.write_bytes(backup.read_bytes())
    conn = sqlite3.connect(tampered)
    try:
        conn.execute("ALTER TABLE orders ADD COLUMN note TEXT")
        conn.commit()
    finally:
        conn.close()

    result = restore_and_verify(tampered, manifest, tmp_path / "restore")
    schema_checks = [c for c in result["checks"] if c["name"] == "schema_fingerprint"]
    assert schema_checks and schema_checks[0]["ok"] is False


def test_missing_and_malformed_manifest(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=20, seed=1)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    with pytest.raises(OperationalError):
        restore_and_verify(backup, tmp_path / "missing.json", tmp_path / "restore")

    malformed = tmp_path / "bad.json"
    malformed.write_text("not-json", encoding="utf-8")
    with pytest.raises(OperationalError):
        restore_and_verify(backup, malformed, tmp_path / "restore2")


def test_preserves_original_source_and_backup(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=20, seed=3)
    source_before = source.read_bytes()

    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")
    backup_before = backup.read_bytes()

    _ = restore_and_verify(backup, manifest, tmp_path / "restore")
    assert source.read_bytes() == source_before
    assert backup.read_bytes() == backup_before


def test_refuses_overwrite_restore_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=20, seed=4)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    restore_dir = tmp_path / "restore"
    restore_dir.mkdir()
    (restore_dir / "restored.sqlite").write_bytes(b"exists")

    with pytest.raises(OperationalError):
        restore_and_verify(backup, manifest, restore_dir)


def test_cli_exit_codes_and_reports(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite"
    create_sample_database(source, order_count=25, seed=7)
    backup, manifest, _ = create_backup(source, tmp_path / "backup.sqlite", backup_id="x1")

    ok = subprocess.run(
        [sys.executable, "-m", "recovery_tester", "restore-check", str(backup), str(manifest), "--artifacts-dir", str(tmp_path / "art")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0

    bad_backup = tmp_path / "bad.sqlite"
    bad_backup.write_bytes(b"123")
    fail = subprocess.run(
        [sys.executable, "-m", "recovery_tester", "restore-check", str(bad_backup), str(manifest), "--artifacts-dir", str(tmp_path / "art2")],
        check=False,
        capture_output=True,
        text=True,
    )
    assert fail.returncode in {1, 2}


def test_demo_expected_outcomes(tmp_path: Path) -> None:
    report, run_dir = run_demo(tmp_path, orders=30, seed=10)
    assert run_dir.exists()
    assert report["overall_ok"] is True
    assert all(s["expected_outcome_confirmed"] for s in report["scenarios"])
