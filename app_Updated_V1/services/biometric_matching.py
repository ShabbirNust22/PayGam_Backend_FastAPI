"""
Shared biometric-template matching helpers
==============================================
Both TapSign (fingerprint) and face verification compare a fixed-length
feature vector against an encrypted, enrolled template using cosine
similarity. This module holds that shared logic once instead of
duplicating it per-modality.

Reminder (see main.py docstring): this centralized-vector-comparison
approach is the coursework/demo model. Production hardware-backed auth
(Secure Enclave / Android Keystore / passkeys) does this matching
on-device and never sends biometric vectors to a server at all — the
server only verifies a signed challenge (see device_auth_service.py).
"""

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from app.core.security import encrypt_template, decrypt_template


def vector_to_bytes(vec: list[float]) -> bytes:
    return np.array(vec, dtype=np.float32).tobytes()


def bytes_to_vector(raw: bytes) -> np.ndarray:
    return np.frombuffer(raw, dtype=np.float32)


def enroll_template(feature_vector: list[float]) -> bytes:
    """Encrypt a freshly-captured feature vector for storage."""
    raw = vector_to_bytes(feature_vector)
    return encrypt_template(raw)


def cosine_match(stored_encrypted_template: bytes, incoming_vector: list[float]) -> float:
    stored_raw = decrypt_template(stored_encrypted_template)
    stored_vec = bytes_to_vector(stored_raw).reshape(1, -1)
    incoming_vec = np.array(incoming_vector, dtype=np.float32).reshape(1, -1)

    if stored_vec.shape[1] != incoming_vec.shape[1]:
        return 0.0

    similarity = cosine_similarity(stored_vec, incoming_vec)[0][0]
    return float(similarity)
