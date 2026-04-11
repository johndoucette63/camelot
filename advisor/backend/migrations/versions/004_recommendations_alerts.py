"""recommendations and alerts: extend alerts + add thresholds, mutes, notification sinks

Revision ID: 004_recommendations_alerts
Revises: 003_chat_conversations
Create Date: 2026-04-10

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004_recommendations_alerts"
down_revision: Union[str, None] = "003_chat_conversations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extend alerts table ──────────────────────────────────────────────
    op.drop_column("alerts", "acknowledged")

    op.add_column(
        "alerts",
        sa.Column("rule_id", sa.String(100), nullable=False, server_default="legacy"),
    )
    op.add_column(
        "alerts",
        sa.Column("target_type", sa.String(20), nullable=False, server_default="system"),
    )
    op.add_column("alerts", sa.Column("target_id", sa.Integer(), nullable=True))
    op.add_column(
        "alerts",
        sa.Column("state", sa.String(20), nullable=False, server_default="active"),
    )
    op.add_column("alerts", sa.Column("acknowledged_at", sa.DateTime(), nullable=True))
    op.add_column("alerts", sa.Column("resolved_at", sa.DateTime(), nullable=True))
    op.add_column(
        "alerts", sa.Column("resolution_source", sa.String(10), nullable=True)
    )
    op.add_column(
        "alerts",
        sa.Column("source", sa.String(10), nullable=False, server_default="rule"),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "suppressed", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    # Drop server defaults for the NOT-NULL columns so application code provides them
    op.alter_column("alerts", "rule_id", server_default=None)
    op.alter_column("alerts", "target_type", server_default=None)

    # Partial unique index enforces dedup: at most one open (non-resolved, non-suppressed)
    # alert per (rule_id, target_type, target_id).
    op.create_index(
        "alerts_active_rule_target_uidx",
        "alerts",
        ["rule_id", "target_type", "target_id"],
        unique=True,
        postgresql_where=sa.text("state != 'resolved' AND suppressed = false"),
    )
    op.create_index(
        "alerts_state_created_at_idx",
        "alerts",
        ["state", sa.text("created_at DESC")],
    )
    op.create_index(
        "alerts_rule_target_resolved_at_idx",
        "alerts",
        ["rule_id", "target_type", "target_id", sa.text("resolved_at DESC")],
    )

    # ── alert_thresholds ──────────────────────────────────────────────────
    op.create_table(
        "alert_thresholds",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Numeric(10, 2), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("default_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("min_value", sa.Numeric(10, 2), nullable=False),
        sa.Column("max_value", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.execute(
        """
        INSERT INTO alert_thresholds (key, value, unit, default_value, min_value, max_value)
        VALUES
            ('cpu_percent',            80, '%',       80, 10, 100),
            ('disk_percent',           85, '%',       85, 10, 100),
            ('service_down_minutes',    5, 'minutes',  5,  1, 1440),
            ('device_offline_minutes', 10, 'minutes', 10,  1, 1440)
        """
    )

    # ── rule_mutes ────────────────────────────────────────────────────────
    op.create_table(
        "rule_mutes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_rule_mutes_lookup",
        "rule_mutes",
        ["rule_id", "target_type", "target_id", sa.text("expires_at DESC"), "cancelled_at"],
    )

    # ── notification_sinks ────────────────────────────────────────────────
    op.create_table(
        "notification_sinks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column(
            "min_severity", sa.String(20), nullable=False, server_default="critical"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("notification_sinks")
    op.drop_index("idx_rule_mutes_lookup", table_name="rule_mutes")
    op.drop_table("rule_mutes")
    op.drop_table("alert_thresholds")

    op.drop_index("alerts_rule_target_resolved_at_idx", table_name="alerts")
    op.drop_index("alerts_state_created_at_idx", table_name="alerts")
    op.drop_index("alerts_active_rule_target_uidx", table_name="alerts")
    op.drop_column("alerts", "suppressed")
    op.drop_column("alerts", "source")
    op.drop_column("alerts", "resolution_source")
    op.drop_column("alerts", "resolved_at")
    op.drop_column("alerts", "acknowledged_at")
    op.drop_column("alerts", "state")
    op.drop_column("alerts", "target_id")
    op.drop_column("alerts", "target_type")
    op.drop_column("alerts", "rule_id")
    op.add_column(
        "alerts",
        sa.Column(
            "acknowledged", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )
