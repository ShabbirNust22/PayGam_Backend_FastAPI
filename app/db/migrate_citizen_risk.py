"""
Lightweight schema evolution for citizen_risk_predictions.

Adds new audit columns on existing SQLite/Postgres tables without Alembic
for the v1 additive expansion. Safe to call on every startup.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("citizen_risk.migrate")

_TABLE = "citizen_risk_predictions"

# column_name -> SQL type fragment (SQLite-compatible; also works on Postgres for these types)
_NEW_COLUMNS: dict[str, str] = {
    "ml_score": "FLOAT",
    "rule_score": "FLOAT",
    "confidence": "FLOAT",
    "rollout_mode": "VARCHAR",
    "fallback_reason": "TEXT",
    "model_metrics": "JSON",
}


def ensure_citizen_risk_schema(engine: Engine) -> None:
    """Create missing table via metadata elsewhere; here only add new columns."""
    try:
        insp = inspect(engine)
        if _TABLE not in insp.get_table_names():
            return  # create_all will create the full table
        existing = {col["name"] for col in insp.get_columns(_TABLE)}
        missing = [name for name in _NEW_COLUMNS if name not in existing]
        if not missing:
            return
        with engine.begin() as conn:
            for name in missing:
                ddl = f"ALTER TABLE {_TABLE} ADD COLUMN {name} {_NEW_COLUMNS[name]}"
                conn.execute(text(ddl))
                logger.info("citizen_risk_schema_added_column table=%s column=%s", _TABLE, name)
    except Exception as exc:
        logger.warning("citizen_risk_schema_migration_skipped reason=%s", exc)
