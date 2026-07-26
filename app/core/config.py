"""
PayGam Backend — Configuration
--------------------------------
Central settings object. In production these values come from environment
variables / a secrets manager (never hard-code secrets in source).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "PayGam Backend API"
    API_V1_PREFIX: str = "/api/v1"

    # --- Auth / JWT ---
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_ENV_VAR"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./paygam.db"

    # --- TapSign (biometric auth) ---
    TAPSIGN_MATCH_THRESHOLD: float = 0.90  # cosine similarity threshold for a fingerprint match
    TAPSIGN_MAX_FAR: float = 0.00001       # target false-acceptance-rate ceiling (0.001%), see docs
    TAPSIGN_LIVENESS_MIN_SCORE: float = 0.80

    # --- EGOV integration ---
    EGOV_API_BASE_URL: str = "https://api.egov.example.gov/v1"  # placeholder — real gov endpoint
    EGOV_API_KEY: str = "CHANGE_ME"
    EGOV_TIMEOUT_SECONDS: int = 8

    # --- Payment risk scoring ---
    RISK_SCORE_BLOCK_THRESHOLD: float = 0.85
    RISK_SCORE_REVIEW_THRESHOLD: float = 0.55

    # --- Citizen Risk Assessment ML (egov-ml-engine) ---
    # Shared secret for POST /internal/risk-score (Java / service-to-service).
    INTERNAL_SERVICE_KEY: str = "CHANGE_ME_INTERNAL_SERVICE_KEY"
    # Distance from 0.5 required before ML is considered confident enough.
    CITIZEN_RISK_MIN_CONFIDENCE_MARGIN: float = 0.08
    # Per-org rollout: DISABLED | SHADOW | ML_ASSISTED (comma-separated KEY=MODE).
    # Default SHADOW for all known types — ML runs in parallel; rules stay authoritative.
    CITIZEN_RISK_ROLLOUT: str = "BANK=SHADOW,POLICE=SHADOW,COURT=SHADOW,DEFAULT=SHADOW"
    # Mark responses as development-only while synthetic training is in use.
    CITIZEN_RISK_DEVELOPMENT_ONLY: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def citizen_risk_rollout_map(self) -> dict[str, str]:
        mapping: dict[str, str] = {"DEFAULT": "SHADOW"}
        for part in self.CITIZEN_RISK_ROLLOUT.split(","):
            part = part.strip()
            if not part or "=" not in part:
                continue
            key, value = part.split("=", 1)
            mapping[key.strip().upper()] = value.strip().upper()
        return mapping

    def rollout_mode_for_org(self, org_type: str) -> str:
        mapping = self.citizen_risk_rollout_map()
        return mapping.get(org_type.upper(), mapping.get("DEFAULT", "SHADOW"))


settings = Settings()
