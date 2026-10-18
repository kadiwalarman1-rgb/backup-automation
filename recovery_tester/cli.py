from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .backup import create_backup
from .demo import run_demo
from .exceptions import OperationalError
from .reporting import write_reports
from .sample_data import create_sample_database
from .utils import ensure_dir, new_run_id
from .verify import restore_and_verify, verify_backup_only

EXIT_OK = 0
EXIT_VERIFY_FAILED = 1
EXIT_USAGE_OR_OPERATIONAL = 2


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--artifacts-dir", default="artifacts", help="Base directory for generated artifacts.")


def cmd_create_sample(args: argparse.Namespace) -> int:
    db_path = Path(args.db_path)
    create_sample_database(db_path, order_count=args.orders, seed=args.seed)
    print(f"Sample database created: {db_path.resolve()}")
    return EXIT_OK


def cmd_backup(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"backup-{new_run_id()}"
    run_dir = ensure_dir(Path(args.artifacts_dir) / run_id)
    backup_path, manifest_path, _ = create_backup(Path(args.source_db), run_dir / "backup.sqlite", backup_id=run_id)
    print(f"Backup file: {backup_path.resolve()}")
    print(f"Manifest file: {manifest_path.resolve()}")
    return EXIT_OK


def cmd_verify(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"verify-{new_run_id()}"
    run_dir = ensure_dir(Path(args.artifacts_dir) / run_id)
    result = verify_backup_only(Path(args.backup), Path(args.manifest))
    result["run_id"] = run_id
    json_report, html_report = write_reports(result, run_dir, "verify_report")
    print(f"JSON report: {json_report.resolve()}")
    print(f"HTML report: {html_report.resolve()}")
    return EXIT_OK if result["overall_ok"] else EXIT_VERIFY_FAILED


def cmd_restore_check(args: argparse.Namespace) -> int:
    run_id = args.run_id or f"restore-{new_run_id()}"
    run_dir = ensure_dir(Path(args.artifacts_dir) / run_id)
    result = restore_and_verify(Path(args.backup), Path(args.manifest), run_dir / "restore", timeout_seconds=args.timeout)
    result["run_id"] = run_id
    json_report, html_report = write_reports(result, run_dir, "restore_report")
    print(f"JSON report: {json_report.resolve()}")
    print(f"HTML report: {html_report.resolve()}")
    print(f"Restored DB: {(run_dir / 'restore' / 'restored.sqlite').resolve()}")
    return EXIT_OK if result["overall_ok"] else EXIT_VERIFY_FAILED


def cmd_demo(args: argparse.Namespace) -> int:
    report, run_dir = run_demo(Path(args.artifacts_dir), orders=args.orders, seed=args.seed)
    json_report, html_report = write_reports(report, run_dir, "demo_report")
    print(f"Demo run directory: {run_dir.resolve()}")
    print(f"JSON report: {json_report.resolve()}")
    print(f"HTML report: {html_report.resolve()}")
    return EXIT_OK if report["overall_ok"] else EXIT_VERIFY_FAILED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m recovery_tester", description="Backup Recovery Tester CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sample = sub.add_parser("create-sample", help="Create deterministic sample SQLite database")
    sample.add_argument("db_path", help="Path to output SQLite database")
    sample.add_argument("--orders", type=int, default=1000, help="Number of orders to generate")
    sample.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    sample.set_defaults(handler=cmd_create_sample)

    backup = sub.add_parser("backup", help="Create a consistent SQLite backup and manifest")
    backup.add_argument("source_db", help="Path to source SQLite database")
    backup.add_argument("--run-id", help="Optional run identifier")
    _add_common(backup)
    backup.set_defaults(handler=cmd_backup)

    verify = sub.add_parser("verify", help="Verify backup checksum and manifest consistency")
    verify.add_argument("backup", help="Path to backup SQLite file")
    verify.add_argument("manifest", help="Path to manifest JSON")
    verify.add_argument("--run-id", help="Optional run identifier")
    _add_common(verify)
    verify.set_defaults(handler=cmd_verify)

    restore = sub.add_parser("restore-check", help="Restore backup into isolated directory and run full verification")
    restore.add_argument("backup", help="Path to backup SQLite file")
    restore.add_argument("manifest", help="Path to manifest JSON")
    restore.add_argument("--timeout", type=float, default=5.0, help="SQLite operation timeout in seconds")
    restore.add_argument("--run-id", help="Optional run identifier")
    _add_common(restore)
    restore.set_defaults(handler=cmd_restore_check)

    demo = sub.add_parser("demo", help="Run healthy and failure-detection scenarios")
    demo.add_argument("--orders", type=int, default=1000, help="Number of sample orders")
    demo.add_argument("--seed", type=int, default=42, help="Deterministic random seed")
    _add_common(demo)
    demo.set_defaults(handler=cmd_demo)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except OperationalError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return EXIT_USAGE_OR_OPERATIONAL


if __name__ == "__main__":
    raise SystemExit(main())
