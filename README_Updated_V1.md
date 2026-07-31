# PayGam Backend — FastAPI (TapSign + EGOV) — Production-oriented V1

Backend API for **PayGam** (paygamglobal.com): e-wallet payments, TapSign,
EGOV KYC, and Citizen Risk Assessment ML on **PostgreSQL**.

## Quick start (Windows / local SQLite)

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Optional: set TEMPLATE_ENCRYPTION_KEY for durable biometrics
uvicorn main:app --reload
```

Swagger: http://127.0.0.1:8000/docs (disabled automatically when `ENVIRONMENT=production`)

## Postgres via Docker Compose

```powershell
# Generate a Fernet key once:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Put it in the environment or a .env next to compose, then:
docker compose up --build
```

Entrypoint waits for Postgres, runs `alembic upgrade head`, then starts uvicorn.

Production checklist (fail-closed):
- `ENVIRONMENT=production`
- Strong `SECRET_KEY`, `INTERNAL_SERVICE_KEY`, `TEMPLATE_ENCRYPTION_KEY`
- `DATABASE_URL=postgresql+psycopg://...`
- `EGOV_USE_MOCK=false`, `TELCO_USE_MOCK=false`, real API keys
- `CITIZEN_RISK_ALLOW_SYNTHETIC_TRAIN_ON_BOOT=false`
- Explicit `ALLOWED_ORIGINS` (no `*`)

## Architecture split with Java eGov

See [docs/JAVA_INTEGRATION.txt](docs/JAVA_INTEGRATION.txt):

- **Java** owns HF7000 `BiometricDevice` / `BiometricTemplate` / login DTO
- **This service** owns wallet, payments, citizen risk, partner feeds

## Key endpoints

| Endpoint | Auth | Purpose |
|---|---|---|
| `POST /api/v1/auth/register\|login` | — | User + JWT |
| `POST /api/v1/payments/send` | JWT + optional `Idempotency-Key` | TapSign-gated transfer |
| `POST /api/v1/tapsign/*`, `/face/*`, `/pin/*`, `/device/*` | JWT | Auth factors |
| `POST /api/v1/egov/verify` | JWT | KYC (mock outside prod) |
| `POST /internal/risk-score` | `X-Internal-Service-Key` | Citizen risk (spec) |
| `POST /internal/partners/{code}/events` | service key | Partner feature feeds |
| `GET /health` | — | Includes DB check |

## Citizen risk

- Org-segmented Logistic Regression artifacts under `model_artifacts/citizen_risk`
- Train offline: `python scripts/train_citizen_risk.py`
- Default rollout: **SHADOW** (rules authoritative)
- Production never silent-trains synthetic models for `ML_ASSISTED`

## Migrations

```powershell
alembic upgrade head
```

Dev/test may still bootstrap via `create_all` when `ENVIRONMENT!=production`.

## Tests

```powershell
pytest -q
```

Uses in-memory SQLite; set `ALLOWED_HOSTS` to include `testserver` (default).
