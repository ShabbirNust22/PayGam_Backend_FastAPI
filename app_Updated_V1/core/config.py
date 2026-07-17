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

    # --- Risk scoring ---
    RISK_SCORE_BLOCK_THRESHOLD: float = 0.85
    RISK_SCORE_REVIEW_THRESHOLD: float = 0.55

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
