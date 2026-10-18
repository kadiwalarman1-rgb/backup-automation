from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any


def _status_badge(ok: bool) -> str:
    return f'<span class="badge {"ok" if ok else "fail"}">{"PASS" if ok else "FAIL"}</span>'


def write_reports(report_data: dict[str, Any], output_dir: Path, report_name: str) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{report_name}.json"
    html_path = output_dir / f"{report_name}.html"

    json_path.write_text(json.dumps(report_data, indent=2), encoding="utf-8")

    checks_rows = "\n".join(
        f"<tr><td>{html.escape(check['name'])}</td><td>{_status_badge(bool(check['ok']))}</td><td>{html.escape(str(check['detail']))}</td></tr>"
        for check in report_data.get("checks", [])
    )
    scenarios_rows = "\n".join(
        (
            f"<tr><td>{html.escape(s.get('name', ''))}</td><td>{_status_badge(bool(s.get('verification_ok')))}</td>"
            f"<td>{_status_badge(bool(s.get('expected_outcome_confirmed')))}</td><td>{html.escape(s.get('detail', ''))}</td></tr>"
        )
        for s in report_data.get("scenarios", [])
    )

    html_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Backup Recovery Tester Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 1rem auto; max-width: 1100px; padding: 0 1rem; color: #1a1a1a; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 1rem; margin-bottom: 1rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; vertical-align: top; }}
    th {{ background: #f7f7f7; }}
    .badge {{ display: inline-block; padding: 0.15rem 0.45rem; border-radius: 999px; font-size: 0.75rem; font-weight: 700; }}
    .ok {{ background: #dcfce7; color: #166534; }}
    .fail {{ background: #fee2e2; color: #991b1b; }}
    .muted {{ color: #4b5563; font-size: 0.9rem; }}
    @media (max-width: 720px) {{ th, td {{ font-size: 0.9rem; }} }}
  </style>
</head>
<body>
  <h1>Backup Recovery Tester</h1>
  <p class="muted">Local SQLite recovery-verification report. Timings are measured in this demo environment and are not production recovery guarantees.</p>

  <section class="card">
    <h2>Run Summary</h2>
    <ul>
      <li><strong>Run ID:</strong> {html.escape(str(report_data.get('run_id', 'n/a')))}</li>
      <li><strong>Started (UTC):</strong> {html.escape(str(report_data.get('run_started_utc', 'n/a')))}</li>
      <li><strong>Ended (UTC):</strong> {html.escape(str(report_data.get('run_ended_utc', 'n/a')))}</li>
      <li><strong>Overall:</strong> {_status_badge(bool(report_data.get('overall_ok')))}</li>
      <li><strong>Restore duration:</strong> {html.escape(str(report_data.get('restore_duration_seconds', 'n/a')))}s</li>
      <li><strong>Verification duration:</strong> {html.escape(str(report_data.get('verification_duration_seconds', 'n/a')))}s</li>
    </ul>
  </section>

  <section class="card">
    <h2>Checks</h2>
    <table>
      <thead><tr><th>Check</th><th>Status</th><th>Details</th></tr></thead>
      <tbody>{checks_rows}</tbody>
    </table>
  </section>

  <section class="card">
    <h2>Demo Scenarios</h2>
    <table>
      <thead><tr><th>Scenario</th><th>Backup Verification Result</th><th>Expected Failure Detected</th><th>Details</th></tr></thead>
      <tbody>{scenarios_rows}</tbody>
    </table>
  </section>

  <section class="card">
    <h2>Manifest Snapshot</h2>
    <pre>{html.escape(json.dumps(report_data.get('manifest', {}), indent=2))}</pre>
  </section>
</body>
</html>
""",
        encoding="utf-8",
    )
    return json_path, html_path
