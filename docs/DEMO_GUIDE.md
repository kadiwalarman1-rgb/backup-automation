# Demo Guide

## Goal
Show one successful restore and one expected failure detection using a single command.

## Command

```bash
python -m recovery_tester demo --artifacts-dir artifacts
```

## What it demonstrates

- Healthy backup restore + verification passes.
- Truncated backup copy is rejected.
- Valid SQLite copy with modified data (same row count) is rejected by content hash checks.

## Interview screenshots to capture

1. Terminal output showing demo command and generated report paths.
2. HTML report summary with overall result.
3. Demo scenario table showing healthy pass and expected failures detected.
4. Checks table showing checksum/schema/content hash validations.

## Talking points

- Backup is created using SQLite backup API (consistent snapshot approach).
- Verification checks data integrity deeper than row counts.
- Negative scenarios are treated as successful demo outcomes only when detection is correct.
