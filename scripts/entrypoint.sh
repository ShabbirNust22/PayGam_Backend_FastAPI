#!/bin/sh
set -e

echo "Waiting for database..."
python - <<'PY'
import os, time
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
engine = create_engine(url)
for i in range(60):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("database ready")
        break
    except Exception as exc:
        print(f"waiting for db ({i}): {exc}")
        time.sleep(2)
else:
    raise SystemExit("database not ready")
PY

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
