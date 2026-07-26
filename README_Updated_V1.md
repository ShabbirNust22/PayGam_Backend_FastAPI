# PayGam Backend — FastAPI (TapSign + EGOV)

Backend API for **PayGam** (paygamglobal.com), an e-wallet payment platform.
This implements the payment-processing backend described in the
ML-TapSign-EGOV progress report, with:

- **JWT-based auth** (register / login) and a wallet per user
- **TapSign** — fingerprint biometric authorization (enrol + verify), gating
  every outbound payment
- **EGOV** — national ID verification (KYC) required to unlock full account
  features
- **Risk scoring** — every payment is screened before funds move
  (authorized / held for review / blocked)

## Project layout

```
paygam_backend/
├── main.py                      # FastAPI app entrypoint
├── requirements.txt
└── app/
    ├── core/
    │   ├── config.py             # settings (thresholds, secrets, DB url)
    │   └── security.py           # JWT, password hashing, template encryption
    ├── db/
    │   └── database.py           # SQLAlchemy engine/session
    ├── models/                   # SQLAlchemy ORM: User, Wallet,
    │   │                         # BiometricTemplate, FaceTemplate,
    │   │                         # DeviceKey, AuthChallenge, Transaction,
    │   │                         # CitizenRiskPrediction, RiskEvent, RiskAlert
    │   ├── user.py
    │   ├── transaction.py
    │   ├── citizen_risk.py
    │   └── risk_monitoring.py
    ├── schemas/                  # Pydantic request/response models
    │   ├── user.py
    │   ├── tapsign.py
    │   ├── face.py
    │   ├── pin.py
    │   ├── phone.py
    │   ├── device.py
    │   ├── egov.py
    │   ├── citizen_risk.py
    │   ├── risk_monitoring.py
    │   ├── member_auth.py
    │   └── transaction.py
    ├── services/                 # business logic, framework-agnostic
    │   ├── biometric_matching.py # shared cosine-similarity template matching
    │   ├── tapsign_service.py    # fingerprint matching (centralized-vector demo)
    │   ├── face_service.py       # facial identity matching (same pattern)
    │   ├── device_auth_service.py# REAL challenge-response protocol (Ed25519)
    │   ├── pin_service.py        # PIN hashing, attempts, lockout
    │   ├── phone_service.py      # phone/SIM authenticity checks
    │   ├── egov_service.py       # government identity-verification client
    │   ├── citizen_risk_service.py   # eGov Citizen Risk Assessment ML module
    │   ├── risk_monitoring_service.py# TapSign risk monitoring (analytics-only)
    │   └── risk_service.py       # payment transaction fraud/risk scoring
    └── api/
        ├── deps.py                # get_current_user() auth dependency
        └── v1/
            ├── api.py             # router aggregator
            └── endpoints/
                ├── auth.py
                ├── tapsign.py
                ├── face.py
                ├── pin.py
                ├── phone.py
                ├── device.py
                ├── egov.py
                ├── egov_risk.py
                ├── payments.py
                └── risk_insights.py
```

## Run it (Windows)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload
```

Swagger UI: **http://127.0.0.1:8000/docs**
(SQLite database `paygam.db` is created automatically on first run — swap
`DATABASE_URL` in `app/core/config.py` or `.env` for Postgres/MySQL in production.)

Canonical package directory is `app/` (imports are `from app...`).
`main.py` is the single application entrypoint.

## eGov Citizen Risk Assessment ML module

Standalone-style scoring engine inside this FastAPI app (egov-ml-engine),
per `Citizen_Risk_Assessment_ML_Module`:

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /internal/risk-score` | `X-Internal-Service-Key` | Spec sync interface for Java callers |
| `POST /api/v1/egov/risk-score` | JWT | Compatibility wrapper for Swagger / app use |

Every response includes `risk_score`, `risk_level`, `org_type`, `top_reasons`,
`model_version`, and `decision_source` (`ML` | `RULE_BASED_FALLBACK` | `BOTH`).

**Rollout modes** (env `CITIZEN_RISK_ROLLOUT`, default all `SHADOW`):

- `DISABLED` — rules only
- `SHADOW` — ML + rules computed; **rule score is returned** with `decision_source=BOTH`
- `ML_ASSISTED` — ML returned when healthy and confident; otherwise rule fallback

**Model:** org-segmented Logistic Regression (`BANK` / `POLICE` / `COURT` / `DEFAULT`)
with coefficient-based explanations (LinearExplainer-equivalent). Holdout
AUC-ROC / F1 / Brier metrics are attached as development metadata.

**WARNING — synthetic training:** models are trained on deterministic synthetic
data until real CitizenCreditScore / service / location / compliance extracts
are wired. Responses set `development_only: true`. Do not enable automated
decisioning on synthetic metrics alone.

**Safety:** low-confidence and ML failures always fall back to rules; every
fallback is logged. Predictions are stored **additively** in
`citizen_risk_predictions` (never overwrites existing credit-score rows).
Schema expansion runs via `app/db/migrate_citizen_risk.py` on startup.

**Deferred:** Kafka consumer/producer and live Java microservice wiring.

Example internal call:

```powershell
curl -X POST http://127.0.0.1:8000/internal/risk-score `
  -H "Content-Type: application/json" `
  -H "X-Internal-Service-Key: CHANGE_ME_INTERNAL_SERVICE_KEY" `
  -d "{\"subject_ref\":\"c-1\",\"org_type\":\"BANK\",\"late_payments\":5,\"overdue_services\":3,\"compliance_flags\":1}"
```

Tests:

```powershell
pytest tests/test_citizen_risk.py -q
```

The PIN/phone factors feed this model as behavioral signals
(`pin_failed_attempts`, `phone_sim_swap_recent`).

## TapSign ML risk monitoring (analytics only — never blocks)

Implements the monitoring layer from `TapSign_ML.pdf`, under `/risk-insights`:
event ingestion, per-device aggregations, and rule-based monitors
(`unusual_device`, `excessive_attempts`, and the manifest's key
`tapsign_bypass` detector). Every function in
`app/services/risk_monitoring_service.py` either appends an event,
computes a read-only aggregate, or raises an advisory alert — **none of
them can block, deny, or modify trust/wallet/approval state**, per the
manifest's one overriding rule. This is deliberately a separate module
from `risk_service.py` (which *does* block payments) — monitoring and
enforcement are kept apart on purpose.



Two integration points are implemented as clearly-labeled stubs with the
real request/response contract already in place, ready to be pointed at the
live systems:

- **`app/services/tapsign_service.py`** — `cosine_match()` currently
  compares vectors you send it. When the CNN (`Conv2D → Conv2D → Dense →
  sigmoid`, per the progress report) is deployed as an inference service,
  point feature extraction at it; the matching/threshold logic here is
  already production-shaped (encrypted-at-rest templates, configurable
  threshold, liveness gate).
- **`app/services/egov_service.py`** — `call_egov_api()` has the real
  government API call written and commented out, plus a mock fallback used
  until EGOV credentials/endpoint are provisioned. Uncomment the `httpx`
  block and set `EGOV_API_BASE_URL` / `EGOV_API_KEY` in `app/core/config.py`
  to go live.

## Security notes

- Fingerprint templates are stored **encrypted at rest**
  (`app/core/security.py::encrypt_template`), never as raw images.
- Passwords are hashed with bcrypt, never stored in plaintext.
- JWTs expire after `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30).
- `SECRET_KEY`, `EGOV_API_KEY`, and the template-encryption key must come
  from a secrets manager in production — the values in `config.py` are
  placeholders for local development only.
