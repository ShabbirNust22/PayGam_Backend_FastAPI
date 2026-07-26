"""
PIN accountability service
------------------------------
"Accountability" here means: PINs are never stored in plaintext, every
verification attempt is counted, and repeated failures lock the account
out for a cooldown window — the same discipline used for TapSign/face,
applied to the simplest factor. Failed attempts also feed the eGov risk
model as a compliance/behavior signal (see citizen_risk_service.py).
"""

from datetime import datetime, timedelta, timezone

from app.core.security import hash_password, verify_password  # bcrypt — reused, not reinvented

MAX_PIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def hash_pin(pin: str) -> str:
    return hash_password(pin)


def is_locked(user) -> tuple[bool, datetime | None]:
    locked_until = user.pin_locked_until
    if not locked_until:
        return False, None
    # SQLite drops tzinfo on round-trip, so normalize both sides to naive UTC.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    compare_until = locked_until.replace(tzinfo=None) if locked_until.tzinfo else locked_until
    if compare_until > now:
        return True, locked_until
    return False, None


def verify_pin(user, pin: str) -> tuple[bool, int, bool, datetime | None]:
    """
    Returns (correct, attempts_remaining, locked, locked_until).
    Mutates `user.pin_failed_attempts` / `user.pin_locked_until` in place —
    caller is responsible for committing the session.
    """
    locked, locked_until = is_locked(user)
    if locked:
        return False, 0, True, locked_until

    if not user.pin_hash:
        return False, 0, False, None

    correct = verify_password(pin, user.pin_hash)

    if correct:
        user.pin_failed_attempts = 0
        user.pin_locked_until = None
        return True, MAX_PIN_ATTEMPTS, False, None

    user.pin_failed_attempts = (user.pin_failed_attempts or 0) + 1
    attempts_remaining = max(MAX_PIN_ATTEMPTS - user.pin_failed_attempts, 0)

    if user.pin_failed_attempts >= MAX_PIN_ATTEMPTS:
        user.pin_locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)
        return False, 0, True, user.pin_locked_until

    return False, attempts_remaining, False, None
