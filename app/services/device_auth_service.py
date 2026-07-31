"""
Device challenge-response authentication protocol
======================================================
This is the realistic counterpart to the centralized fingerprint/face
matching above. It implements the same *pattern* used by FIDO2/WebAuthn,
passkeys, and hardware-backed signing generally (this pattern is public,
widely documented, standards-based cryptography — not anyone's
proprietary implementation):

  1. REGISTER — the device generates an Ed25519 keypair locally (e.g.
     unlocked by the phone's fingerprint/Face ID/PIN via the OS's secure
     keystore). Only the PUBLIC key is ever sent to this backend.
  2. CHALLENGE — the backend issues a one-time random nonce, scoped to a
     specific action ("login", "payment:<tx_id>"), with a short expiry.
  3. VERIFY — the device signs the nonce with its private key (this is
     the local "scan" — the biometric never leaves the device, it just
     authorizes the local signing operation). The backend verifies the
     signature against the registered public key and immediately
     consumes (invalidates) the challenge so it can never be replayed.

This is "protocol handling" in the literal sense: a request-bound,
one-time, cryptographically verifiable exchange — not a password, not a
transmitted biometric.
"""

import base64
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from cryptography.exceptions import InvalidSignature

CHALLENGE_TTL_SECONDS = 60


def generate_nonce() -> str:
    return secrets.token_urlsafe(32)


def new_challenge_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_TTL_SECONDS)


def is_expired(expires_at: datetime) -> bool:
    # SQLite drops tzinfo on round-trip, so normalize both sides to naive UTC.
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.now(timezone.utc).replace(tzinfo=None) > expires_at


def verify_signature(public_key_pem: str, nonce: str, signature_b64: str) -> tuple[bool, str | None]:
    """Verify an Ed25519 signature over `nonce` using the device's stored public key."""
    try:
        public_key = load_pem_public_key(public_key_pem.encode())
        if not isinstance(public_key, Ed25519PublicKey):
            return False, "Registered key is not an Ed25519 public key."

        signature = base64.b64decode(signature_b64)
        public_key.verify(signature, nonce.encode())
        return True, None
    except InvalidSignature:
        return False, "Signature does not match — wrong key or tampered challenge."
    except Exception:
        return False, "Could not verify signature."


def self_test() -> dict:
    """
    A runnable evaluation/self-test of the protocol using a freshly
    generated in-memory keypair — proves the sign/verify round-trip works
    without needing a real device. Useful as a smoke test / CI check.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, NoEncryption, PrivateFormat

    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo).decode()

    nonce = generate_nonce()
    signature = private_key.sign(nonce.encode())
    signature_b64 = base64.b64encode(signature).decode()

    ok, reason = verify_signature(public_pem, nonce, signature_b64)

    # Negative case: verify a tampered nonce correctly FAILS
    tampered_ok, _ = verify_signature(public_pem, nonce + "x", signature_b64)

    return {
        "positive_case_verified": ok,
        "positive_case_reason": reason,
        "negative_case_correctly_rejected": not tampered_ok,
    }
