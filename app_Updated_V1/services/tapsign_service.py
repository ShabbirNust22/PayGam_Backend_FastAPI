"""
TapSign service layer
-----------------------
This module owns the *matching* logic that sits behind the TapSign API
endpoints. The CNN feature-extraction model itself (Conv2D -> Conv2D ->
Dense -> sigmoid, per the progress report) runs on-device or in a
dedicated inference service; what lands here is already a fixed-length
feature vector. This layer is responsible for:

  1. Comparing an incoming feature vector against the user's enrolled,
     encrypted template (cosine similarity — the standard approach for
     comparing CNN embedding vectors).
  2. Enforcing the liveness-detection gate (anti-spoofing score).
  3. Returning a decision the API layer can act on.

Swap `cosine_match()` for a call to your real inference/matching service
when the CNN model is deployed; the interface (inputs/outputs) stays the same.

NOTE on the more realistic alternative: real hardware-backed fingerprint
auth (Secure Enclave / Android Keystore / passkeys) never sends the
fingerprint or its feature vector to a server — matching happens on-device
and the server just verifies a signed challenge. See
`device_auth_service.py` for that pattern, now also implemented here.
This module remains as the coursework-style centralized-matching demo.
"""

from app.core.config import settings
from app.schemas.tapsign import TapSignVerifyResult
from app.services.biometric_matching import enroll_template, cosine_match  # noqa: F401 (re-exported)


def verify(stored_encrypted_template: bytes, incoming_vector: list[float], liveness_score: float) -> TapSignVerifyResult:
    liveness_passed = liveness_score >= settings.TAPSIGN_LIVENESS_MIN_SCORE
    if not liveness_passed:
        return TapSignVerifyResult(
            match=False,
            similarity=0.0,
            liveness_passed=False,
            reason="Liveness check failed — possible spoof attempt (replica/photo).",
        )

    similarity = cosine_match(stored_encrypted_template, incoming_vector)
    is_match = similarity >= settings.TAPSIGN_MATCH_THRESHOLD

    return TapSignVerifyResult(
        match=is_match,
        similarity=round(similarity, 6),
        liveness_passed=True,
        reason=None if is_match else "Fingerprint does not match enrolled template.",
    )
