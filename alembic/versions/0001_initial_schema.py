"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")

    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("full_name", sa.String(), nullable=False),
        sa.Column("phone_number", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("national_id_number", sa.String(), nullable=True),
        sa.Column("egov_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("tapsign_enrolled", sa.Boolean(), server_default=sa.false()),
        sa.Column("face_enrolled", sa.Boolean(), server_default=sa.false()),
        sa.Column("pin_hash", sa.String(), nullable=True),
        sa.Column("pin_failed_attempts", sa.Integer(), server_default="0"),
        sa.Column("pin_locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_verified", sa.Boolean(), server_default=sa.false()),
        sa.Column("phone_last_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("phone_last_sim_swap_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_users_phone_number", "users", ["phone_number"], unique=True)
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_national_id_number", "users", ["national_id_number"], unique=True)

    op.create_table(
        "wallets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("balance", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(), server_default="GMD"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "biometric_templates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("encrypted_template", sa.LargeBinary(), nullable=False),
        sa.Column("template_version", sa.String(), server_default="cnn-v1"),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "face_templates",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("encrypted_template", sa.LargeBinary(), nullable=False),
        sa.Column("template_version", sa.String(), server_default="face-embed-v1"),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "device_keys",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default=sa.false()),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_device_keys_device_id", "device_keys", ["device_id"], unique=True)

    op.create_table(
        "auth_challenges",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("device_id", sa.String(), nullable=False),
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed", sa.Boolean(), server_default=sa.false()),
    )
    op.create_index("ix_auth_challenges_device_id", "auth_challenges", ["device_id"])

    op.create_table(
        "transactions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("sender_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("receiver_id", sa.String(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(), server_default="GMD"),
        sa.Column("status", sa.String(), server_default="pending"),
        sa.Column("risk_score", sa.Numeric(8, 4), nullable=True),
        sa.Column("tapsign_verified", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_transactions_idempotency_key", "transactions", ["idempotency_key"], unique=True)

    op.create_table(
        "citizen_risk_predictions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("subject_ref", sa.String(), nullable=False),
        sa.Column("org_type", sa.String(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=False),
        sa.Column("top_reasons", json_type, nullable=False),
        sa.Column("model_version", sa.String(), nullable=False),
        sa.Column("decision_source", sa.String(), nullable=False),
        sa.Column("input_feature_snapshot", json_type, nullable=False),
        sa.Column("score_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ml_score", sa.Float(), nullable=True),
        sa.Column("rule_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("rollout_mode", sa.String(), nullable=True),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("model_metrics", json_type, nullable=True),
    )
    op.create_index("ix_citizen_risk_predictions_subject_ref", "citizen_risk_predictions", ["subject_ref"])

    op.create_table(
        "partner_risk_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("partner_code", sa.String(), nullable=False),
        sa.Column("subject_ref", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_partner_risk_events_event_id", "partner_risk_events", ["event_id"], unique=True)
    op.create_index("ix_partner_risk_events_partner_code", "partner_risk_events", ["partner_code"])
    op.create_index("ix_partner_risk_events_subject_ref", "partner_risk_events", ["subject_ref"])
    op.create_index("ix_partner_risk_events_event_type", "partner_risk_events", ["event_type"])

    op.create_table(
        "risk_events",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="paygam"),
        sa.Column("device_ref", sa.String(), nullable=True),
        sa.Column("subject_ref", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("metadata_json", json_type, nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_risk_events_tenant_id", "risk_events", ["tenant_id"])
    op.create_index("ix_risk_events_device_ref", "risk_events", ["device_ref"])
    op.create_index("ix_risk_events_subject_ref", "risk_events", ["subject_ref"])
    op.create_index("ix_risk_events_event_type", "risk_events", ["event_type"])

    op.create_table(
        "risk_alerts",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, server_default="paygam"),
        sa.Column("monitor", sa.String(), nullable=False),
        sa.Column("subject_ref", sa.String(), nullable=True),
        sa.Column("device_ref", sa.String(), nullable=True),
        sa.Column("severity", sa.String(), server_default="INFO"),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("details", json_type, nullable=True),
        sa.Column("acknowledged", sa.Boolean(), server_default=sa.false()),
        sa.Column("raised_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_risk_alerts_tenant_id", "risk_alerts", ["tenant_id"])
    op.create_index("ix_risk_alerts_monitor", "risk_alerts", ["monitor"])
    op.create_index("ix_risk_alerts_subject_ref", "risk_alerts", ["subject_ref"])
    op.create_index("ix_risk_alerts_device_ref", "risk_alerts", ["device_ref"])


def downgrade() -> None:
    op.drop_table("risk_alerts")
    op.drop_table("risk_events")
    op.drop_table("partner_risk_events")
    op.drop_table("citizen_risk_predictions")
    op.drop_table("transactions")
    op.drop_table("auth_challenges")
    op.drop_table("device_keys")
    op.drop_table("face_templates")
    op.drop_table("biometric_templates")
    op.drop_table("wallets")
    op.drop_table("users")
