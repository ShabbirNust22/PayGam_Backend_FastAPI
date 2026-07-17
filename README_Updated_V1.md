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

## Run it

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Swagger UI: **http://127.0.0.1:8000/docs**
(SQLite database `paygam.db` is created automatically on first run — swap
`DATABASE_URL` in `app/core/config.py` for Postgres/MySQL in production.)

## The payment flow (TapSign + risk scoring)

`POST /api/v1/payments/send` is the core of the integration:

1. **TapSign verification** — the request carries a `feature_vector`
   (produced by the on-device/CNN fingerprint feature extractor — the raw
   fingerprint image is never sent to or stored by this backend) plus a
   `liveness_score`. The backend:
   - rejects if liveness fails (anti-spoofing gate)
   - compares the vector against the user's **encrypted** enrolled template
     using cosine similarity (`app/services/tapsign_service.py`)
2. **Risk scoring** — amount, transaction velocity, and new-payee checks
   produce a 0–1 risk score (`app/services/risk_service.py`), which decides:
   `authorized` → funds move immediately · `requires_review` → transaction
   is recorded but held · `blocked` → rejected outright.
3. Funds move only after both gates pass, and every attempt (success or
   failure) is recorded in the `transactions` table for audit.

## Member authentication — fingerprint, face, PIN, phone, and a real challenge-response protocol

`main.py` now hosts the top-level member-authentication orchestration
(`match_customer_fingerprint`, `test_fingerprint_protocol`,
`handle_challenge_protocol`, `evaluate_member_authentication`), which the
routers below call into:

| Factor | Endpoint(s) | What it does |
|---|---|---|
| Fingerprint (TapSign) | `POST /tapsign/enroll`, `/tapsign/verify` | Centralized cosine-similarity match against an encrypted template |
| Face | `POST /face/enroll`, `/face/verify` | Same pattern, separate modality, tighter threshold |
| PIN | `POST /pin/set`, `/pin/verify` | Bcrypt-hashed, 5-attempt lockout with cooldown ("accountability") |
| Phone/SIM | `POST /phone/verify` | Carrier lookup + recent-SIM-swap risk flag |
| Device (challenge-response) | `POST /device/register`, `/challenge`, `/verify`, `GET /device/selftest` | **Real** Ed25519 sign/verify protocol — see below |
| Composite | `POST /auth/member/authenticate`, `GET /auth/member/protocol-selftest` | Runs whichever factors are supplied and feeds the result into the eGov risk module |

**Two authentication models, on purpose.** Factors 1–3 above use the
same centralized-vector-matching approach as the original TapSign demo —
easy to reason about and test, but not how production hardware-backed
biometric auth actually works. The **device challenge-response protocol**
(`app/services/device_auth_service.py`) is the realistic alternative:
the device generates an Ed25519 keypair locally, the private key never
leaves it, and the backend only ever verifies a signed, one-time,
action-bound nonce — the same public, standards-based pattern behind
FIDO2/WebAuthn/passkeys. `GET /device/selftest` runs this protocol
end-to-end with a throwaway keypair and confirms both that a valid
signature is accepted *and* that a tampered challenge is correctly
rejected.

## eGov Citizen Risk Assessment ML module

Implements `Citizen_Risk_Assessment_ML_Module.pdf`: `POST
/egov/risk-score` returns the exact response shape from the spec
(`risk_score`, `risk_level`, `org_type`, `top_reasons`, `model_version`,
`decision_source`), backed by a baseline **Logistic Regression** model
(`app/services/citizen_risk_service.py`) with linear-coefficient-based
explanations (the exact equivalent of SHAP's `LinearExplainer` for this
model type — swap in `shap.TreeExplainer` if a candidate tree model
replaces the baseline). Every prediction is stored **additively** in
`CitizenRiskPrediction` with a full audit snapshot, and the module
automatically falls back to a transparent rule-based score
(`decision_source: "RULE_BASED_FALLBACK"`) whenever the model's
confidence is too low — per the spec's safety requirement that it "never
makes an unreviewed decision without a safety net."

The PIN/phone factors above feed directly into this model as behavioral
signals (`pin_failed_attempts`, `phone_sim_swap_recent`) — this is how
the new security factors "correspond to the eGov framework."

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
