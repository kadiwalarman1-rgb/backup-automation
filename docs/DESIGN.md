# Design Notes

## Scope
Local SQLite backup and restore verification for learning and demonstration.

## Modules

- `sample_data.py`: deterministic source DB creation.
- `backup.py`: backup creation with manifest baseline from backup snapshot.
- `verify.py`: backup checks, isolated restore, integrity/foreign key/schema/content checks.
- `demo.py`: healthy + failure scenario automation in isolated run directories.
- `reporting.py`: JSON + standalone HTML report generation.
- `cli.py`: argparse commands and documented exit codes.

## Supported schema/table types

- Schema objects fingerprinted: `table`, `index`, `view`, `trigger` from `sqlite_master` excluding internal `sqlite_%`.
- Content verification tables: user tables (`type='table'`) excluding `sqlite_%`.

## Security and integrity note

Manifest + checksum helps detect accidental corruption and drift, but if an attacker can alter both backup and manifest, authenticity is not guaranteed.

## Restore safety

- Uses unique run directories under artifacts.
- Refuses restore destination overwrite.
- Keeps source DB and original backup untouched.
- Failure simulations modify only copied files created by the tool.
