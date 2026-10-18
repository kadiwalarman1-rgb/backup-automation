class RecoveryTesterError(Exception):
    """Base exception."""


class OperationalError(RecoveryTesterError):
    """Operational failure such as path, lock, or malformed input."""


class VerificationFailed(RecoveryTesterError):
    """Verification detected mismatch or corruption."""
