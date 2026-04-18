"""home assistant integration (feature 016)

Adds:
  - home_assistant_connections (singleton, seeded row with id=1)
  - ha_entity_snapshots (per-entity snapshot, upserted each poll)
  - thread_border_routers (derived, refreshed each poll)
  - thread_devices (derived, refreshed each poll)
  - devices.ha_device_id / ha_connectivity_type / ha_last_seen_at
  - devices.mac_address NULLABLE (partial unique index on non-null values)
  - devices CHECK constraint requiring at least mac_address or ha_device_id
  - notification_sinks.home_assistant_id FK
  - alerts.delivery_* retry-state columns

Revision ID: 008_home_assistant_integration
Revises: 007_device_enrichment
Create Date: 2026-04-17
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_home_assistant_integration"
down_revision: Union[str, None] = "007_device_enrichment"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── home_assistant_connections (singleton, id=1) ────────────────────
    op.create_table(
        "home_assistant_connections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("token_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    # Seed the singleton row. base_url IS NULL means "not configured".
    op.execute("INSERT INTO home_assistant_connections (id) VALUES (1)")

    # ── ha_entity_snapshots ─────────────────────────────────────────────
    op.create_table(
        "ha_entity_snapshots",
        sa.Column("entity_id", sa.Text(), primary_key=True),
        sa.Column("ha_device_id", sa.Text(), nullable=False),
        sa.Column("domain", sa.Text(), nullable=False),
        sa.Column("friendly_name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("last_changed", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("polled_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ha_entity_snapshots_ha_device_id",
        "ha_entity_snapshots",
        ["ha_device_id"],
    )
    op.create_index(
        "ix_ha_entity_snapshots_domain", "ha_entity_snapshots", ["domain"]
    )
    op.create_index(
        "ix_ha_entity_snapshots_last_changed",
        "ha_entity_snapshots",
        [sa.text("last_changed DESC")],
    )

    # ── thread_border_routers ───────────────────────────────────────────
    op.create_table(
        "thread_border_routers",
        sa.Column("ha_device_id", sa.Text(), primary_key=True),
        sa.Column("friendly_name", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column(
            "attached_device_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── thread_devices ──────────────────────────────────────────────────
    op.create_table(
        "thread_devices",
        sa.Column("ha_device_id", sa.Text(), primary_key=True),
        sa.Column("friendly_name", sa.Text(), nullable=False),
        sa.Column(
            "parent_border_router_id",
            sa.Text(),
            sa.ForeignKey(
                "thread_border_routers.ha_device_id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("online", sa.Boolean(), nullable=False),
        sa.Column("last_seen_parent_id", sa.Text(), nullable=True),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── devices: HA provenance columns ──────────────────────────────────
    op.add_column(
        "devices", sa.Column("ha_device_id", sa.Text(), nullable=True)
    )
    op.add_column(
        "devices", sa.Column("ha_connectivity_type", sa.Text(), nullable=True)
    )
    op.add_column(
        "devices",
        sa.Column("ha_last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── devices: relax mac_address NOT NULL + UNIQUE ────────────────────
    op.alter_column("devices", "mac_address", nullable=True)
    op.alter_column("devices", "ip_address", nullable=True)
    # Drop the existing table-level unique on mac_address (autogenerated
    # constraint name from earlier migrations was "devices_mac_address_key"
    # under Postgres; tolerate its absence in downgrade).
    op.drop_constraint("devices_mac_address_key", "devices", type_="unique")
    op.create_index(
        "devices_mac_address_unique",
        "devices",
        ["mac_address"],
        unique=True,
        postgresql_where=sa.text("mac_address IS NOT NULL"),
    )
    op.create_index(
        "devices_ha_device_id_unique",
        "devices",
        ["ha_device_id"],
        unique=True,
        postgresql_where=sa.text("ha_device_id IS NOT NULL"),
    )
    op.create_check_constraint(
        "devices_identifier_present",
        "devices",
        "mac_address IS NOT NULL OR ha_device_id IS NOT NULL",
    )

    # ── notification_sinks: link to HA singleton ────────────────────────
    op.add_column(
        "notification_sinks",
        sa.Column(
            "home_assistant_id",
            sa.Integer(),
            sa.ForeignKey(
                "home_assistant_connections.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
    )

    # ── alerts: delivery retry-budget state machine ─────────────────────
    op.add_column(
        "alerts",
        sa.Column(
            "delivery_status",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "delivery_attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "delivery_last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "alerts",
        sa.Column(
            "delivery_next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    # Reverse order of upgrade().
    op.drop_column("alerts", "delivery_next_attempt_at")
    op.drop_column("alerts", "delivery_last_attempt_at")
    op.drop_column("alerts", "delivery_attempt_count")
    op.drop_column("alerts", "delivery_status")

    op.drop_column("notification_sinks", "home_assistant_id")

    op.drop_constraint("devices_identifier_present", "devices", type_="check")
    op.drop_index("devices_ha_device_id_unique", table_name="devices")
    op.drop_index("devices_mac_address_unique", table_name="devices")
    op.create_unique_constraint(
        "devices_mac_address_key", "devices", ["mac_address"]
    )
    op.alter_column("devices", "ip_address", nullable=False)
    op.alter_column("devices", "mac_address", nullable=False)
    op.drop_column("devices", "ha_last_seen_at")
    op.drop_column("devices", "ha_connectivity_type")
    op.drop_column("devices", "ha_device_id")

    op.drop_table("thread_devices")
    op.drop_table("thread_border_routers")

    op.drop_index(
        "ix_ha_entity_snapshots_last_changed", table_name="ha_entity_snapshots"
    )
    op.drop_index(
        "ix_ha_entity_snapshots_domain", table_name="ha_entity_snapshots"
    )
    op.drop_index(
        "ix_ha_entity_snapshots_ha_device_id", table_name="ha_entity_snapshots"
    )
    op.drop_table("ha_entity_snapshots")

    op.drop_table("home_assistant_connections")
