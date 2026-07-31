"""
PayGam Backend — Configuration
--------------------------------
Central settings object. In production these values come from environment
variables / a secrets manager (never hard-code secrets in source).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_PLACEHOLDER_SECRETS = {
    "CHANGE_ME",
    "CHANGE_ME_IN_PRODUCTION_USE_ENV_VAR",
    "CHANGE_ME_INTERNAL_SERVICE_KEY",
}


class Settings(BaseSettings):
    PROJECT_NAME: str = "PayGam Backend API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: str = "development"  # development | staging | production
    DOCS_ENABLED: bool = True
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"
    ALLOWED_HOSTS: str = "localhost,127.0.0.1,testserver"

    # --- Auth / JWT ---
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_ENV_VAR"
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "paygam-backend"
    JWT_AUDIENCE: str = "paygam-clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./paygam.db"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True

    # Stable Fernet key (url-safe base64, 32 bytes). Required in production.
    TEMPLATE_ENCRYPTION_KEY: str = ""

    # --- TapSign (biometric auth) ---
    TAPSIGN_MATCH_THRESHOLD: float = 0.90
    TAPSIGN_MAX_FAR: float = 0.00001
    TAPSIGN_LIVENESS_MIN_SCORE: float = 0.80

    # --- EGOV integration ---
    EGOV_API_BASE_URL: str = "https://api.egov.example.gov/v1"
    EGOV_API_KEY: str = "CHANGE_ME"
    EGOV_TIMEOUT_SECONDS: int = 8
    EGOV_USE_MOCK: bool = True

    # --- Telco / SIM authenticity ---
    TELCO_API_BASE_URL: str = "https://api.telco.example.gm/v1"
    TELCO_API_KEY: str = "CHANGE_ME"
    TELCO_TIMEOUT_SECONDS: int = 8
    TELCO_USE_MOCK: bool = True
    TELCO_SIM_SWAP_LOOKBACK_DAYS: int = 30

    # --- Payment risk scoring ---
    RISK_SCORE_BLOCK_THRESHOLD: float = 0.85
    RISK_SCORE_REVIEW_THRESHOLD: float = 0.55
    PAYMENTS_REQUIRE_EGOV_VERIFIED: bool = False
    RATE_LIMIT_AUTH: str = "20/minute"
    RATE_LIMIT_VERIFY: str = "30/minute"

    # --- Citizen Risk Assessment ML (egov-ml-engine) ---
    INTERNAL_SERVICE_KEY: str = "CHANGE_ME_INTERNAL_SERVICE_KEY"
    CITIZEN_RISK_MIN_CONFIDENCE_MARGIN: float = 0.08
    CITIZEN_RISK_ROLLOUT: str = "BANK=SHADOW,POLICE=SHADOW,COURT=SHADOW,DEFAULT=SHADOW"
    CITIZEN_RISK_DEVELOPMENT_ONLY: bool = True
    CITIZEN_RISK_MODEL_DIR: str = "model_artifacts/citizen_risk"
    CITIZEN_RISK_TRAINING_SOURCE: str = "synthetic"  # synthetic | file | postgres
    CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",") if h.strip()]

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

    def validate_for_environment(self) -> None:
        """Fail closed when running in production with unsafe defaults."""
        if not self.is_production:
            return

        errors: list[str] = []
        if self.SECRET_KEY in _PLACEHOLDER_SECRETS or len(self.SECRET_KEY) < 32:
            errors.append("SECRET_KEY must be set to a strong non-placeholder value")
        if self.INTERNAL_SERVICE_KEY in _PLACEHOLDER_SECRETS:
            errors.append("INTERNAL_SERVICE_KEY must be set to a non-placeholder value")
        if not self.TEMPLATE_ENCRYPTION_KEY:
            errors.append("TEMPLATE_ENCRYPTION_KEY is required in production")
        if self.DATABASE_URL.startswith("sqlite"):
            errors.append("DATABASE_URL must be PostgreSQL in production")
        if self.EGOV_USE_MOCK:
            errors.append("EGOV_USE_MOCK must be false in production")
        if self.TELCO_USE_MOCK:
            errors.append("TELCO_USE_MOCK must be false in production")
        if self.EGOV_API_KEY in _PLACEHOLDER_SECRETS:
            errors.append("EGOV_API_KEY must be set in production")
        if self.TELCO_API_KEY in _PLACEHOLDER_SECRETS:
            errors.append("TELCO_API_KEY must be set in production")
        if "*" in self.allowed_origins_list:
            errors.append("ALLOWED_ORIGINS must not include '*' in production")
        if self.CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT:
            errors.append("CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT must be false in production")
        if errors:
            raise RuntimeError(
                "Production configuration invalid:\n- " + "\n- ".join(errors)
            )


settings = Settings()
