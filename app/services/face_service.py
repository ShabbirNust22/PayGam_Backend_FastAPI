"""
Face verification service layer
-----------------------------------
Same coursework-style approach as TapSign fingerprint matching: compare an
incoming facial embedding against the user's enrolled, encrypted template
with cosine similarity, gated by a liveness score. See
`biometric_matching.py` for the shared vector logic and its module
docstring for how this differs from real on-device Face ID matching.
"""

from app.core.config import settings
from app.schemas.face import FaceVerifyResult
from app.services.biometric_matching import enroll_template, cosine_match  # noqa: F401 (re-exported)

FACE_MATCH_THRESHOLD = 0.92          # facial embeddings typically need a tighter threshold than fingerprints
FACE_LIVENESS_MIN_SCORE = settings.TAPSIGN_LIVENESS_MIN_SCORE


def verify(stored_encrypted_template: bytes, incoming_embedding: list[float], liveness_score: float) -> FaceVerifyResult:
    liveness_passed = liveness_score >= FACE_LIVENESS_MIN_SCORE
    if not liveness_passed:
        return FaceVerifyResult(
            match=False,
            similarity=0.0,
            liveness_passed=False,
            reason="Liveness check failed — possible spoof attempt (photo/video replay).",
        )

    similarity = cosine_match(stored_encrypted_template, incoming_embedding)
    is_match = similarity >= FACE_MATCH_THRESHOLD

    return FaceVerifyResult(
        match=is_match,
        similarity=round(similarity, 6),
        liveness_passed=True,
        reason=None if is_match else "Face does not match enrolled template.",
    )
