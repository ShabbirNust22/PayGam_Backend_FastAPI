# PayGam Backend — FastAPI (TapSign + EGOV)
Research Assessment by Ahmed Shabbir Ibrahim Moomin, Colombo, Sri Lanka. I have completed this week’s report, which covers Python, SQL database, and security protocols for account members’ fingertip access. However, there are several faults and errors, particularly in the Python coding. Nevertheless, I look forward to your feedback and to discussing this further in our weekly meeting.

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
    │   │                         # BiometricTemplate, Transaction
    │   ├── user.py
    │   └── transaction.py
    ├── schemas/                  # Pydantic request/response models
    │   ├── user.py
    │   ├── tapsign.py
    │   ├── egov.py
    │   └── transaction.py
    ├── services/                 # business logic, framework-agnostic
    │   ├── tapsign_service.py    # cosine-similarity template matching
    │   ├── egov_service.py       # government identity-verification client
    │   └── risk_service.py       # transaction fraud/risk scoring
    └── api/
        ├── deps.py                # get_current_user() auth dependency
        └── v1/
            ├── api.py             # router aggregator
            └── endpoints/
                ├── auth.py
                ├── tapsign.py
                ├── egov.py
                └── payments.py
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

## Where the real ML models plug in

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
