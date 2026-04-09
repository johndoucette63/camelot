"""Network discovery and device inventory schema

Revision ID: 001_network_discovery
Revises:
Create Date: 2026-04-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001_network_discovery"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Add new columns to devices ──────────────────────────────────
    op.add_column("devices", sa.Column("mac_address", sa.String(17), nullable=True))
    op.add_column("devices", sa.Column("vendor", sa.String(255), nullable=True))
    op.add_column(
        "devices",
        sa.Column(
            "first_seen",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "last_seen",
            sa.DateTime(),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),
    )
    op.add_column(
        "devices",
        sa.Column("is_online", sa.Boolean(), nullable=True, server_default="false"),
    )
    op.add_column(
        "devices",
        sa.Column(
            "consecutive_missed_scans",
            sa.Integer(),
            nullable=True,
            server_default="0",
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "is_known_device", sa.Boolean(), nullable=True, server_default="false"
        ),
    )

    # ── Step 2: Populate mac_address placeholders for existing seed devices ──
    op.execute("""
        UPDATE devices SET
            mac_address = 'UNKNOWN:0' || id::text,
            first_seen = NOW(),
            last_seen = NOW(),
            is_online = false,
            consecutive_missed_scans = 0,
            is_known_device = true
        WHERE hostname IN (
            'HOLYGRAIL', 'Torrentbox', 'NAS', 'Pi-hole DNS', 'Mac Workstation'
        )
    """)
    # For any other existing rows
    op.execute("""
        UPDATE devices SET
            mac_address = 'UNKNOWN:9' || id::text,
            first_seen = NOW(),
            last_seen = NOW(),
            is_online = false,
            consecutive_missed_scans = 0,
            is_known_device = false
        WHERE mac_address IS NULL
    """)

    # Now make required columns NOT NULL
    op.alter_column("devices", "mac_address", nullable=False)
    op.alter_column("devices", "first_seen", nullable=False)
    op.alter_column("devices", "last_seen", nullable=False)
    op.alter_column("devices", "is_online", nullable=False)
    op.alter_column("devices", "consecutive_missed_scans", nullable=False)
    op.alter_column("devices", "is_known_device", nullable=False)

    # ── Step 3: Make hostname nullable (discovered devices may have no hostname) ─
    op.alter_column("devices", "hostname", nullable=True)

    # ── Step 4: Drop old unique constraints ──────────────────────────────────
    op.drop_constraint("devices_hostname_key", "devices", type_="unique")
    op.drop_constraint("devices_ip_address_key", "devices", type_="unique")

    # ── Step 5: Add mac_address unique constraint and indexes ────────────────
    op.create_unique_constraint("uq_devices_mac_address", "devices", ["mac_address"])
    op.create_index("idx_devices_ip", "devices", ["ip_address"])
    op.create_index("idx_devices_is_online", "devices", ["is_online"])

    # ── Step 6: Drop old columns ─────────────────────────────────────────────
    op.drop_column("devices", "device_type")
    op.drop_column("devices", "status")

    # ── Step 7: Create annotations table ─────────────────────────────────────
    op.create_table(
        "annotations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "role", sa.String(50), nullable=False, server_default="unknown"
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "tags",
            sa.JSON(),
            nullable=False,
            server_default="[]",
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

    # Insert pre-populated annotations for known Camelot devices
    op.execute("""
        INSERT INTO annotations (device_id, role, description, tags)
        SELECT id, 'server',
               'Ryzen 7800X3D — central server (Plex, Ollama, monitoring, advisor)',
               '["plex","ollama","monitoring","advisor"]'::json
        FROM devices WHERE hostname = 'HOLYGRAIL'
    """)
    op.execute("""
        INSERT INTO annotations (device_id, role, description, tags)
        SELECT id, 'server',
               'Raspberry Pi 5 — Deluge + *arr apps + VPN',
               '["deluge","sonarr","radarr","vpn"]'::json
        FROM devices WHERE hostname = 'Torrentbox'
    """)
    op.execute("""
        INSERT INTO annotations (device_id, role, description, tags)
        SELECT id, 'storage',
               'Raspberry Pi 4 — OpenMediaVault, SMB shares',
               '["nas","smb","openmediavault"]'::json
        FROM devices WHERE hostname = 'NAS'
    """)
    op.execute("""
        INSERT INTO annotations (device_id, role, description, tags)
        SELECT id, 'dns',
               'Raspberry Pi 5 — Pi-hole DNS server',
               '["pihole","dns"]'::json
        FROM devices WHERE hostname = 'Pi-hole DNS'
    """)
    op.execute("""
        INSERT INTO annotations (device_id, role, description, tags)
        SELECT id, 'workstation',
               'MacBook Pro M4 Pro — dev/management workstation',
               '["mac","dev"]'::json
        FROM devices WHERE hostname = 'Mac Workstation'
    """)

    # ── Step 8: Create scans table ────────────────────────────────────────────
    op.create_table(
        "scans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "started_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="running"
        ),
        sa.Column("devices_found", sa.Integer(), nullable=True),
        sa.Column(
            "new_devices", sa.Integer(), nullable=True, server_default="0"
        ),
        sa.Column("error_detail", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_scans_started_at", "scans", ["started_at"], postgresql_ops={"started_at": "DESC"}
    )

    # ── Step 9: Create events table ───────────────────────────────────────────
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column(
            "device_id",
            sa.Integer(),
            sa.ForeignKey("devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "scan_id",
            sa.Integer(),
            sa.ForeignKey("scans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "timestamp",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("details", sa.JSON(), nullable=True),
    )
    op.create_index(
        "idx_events_timestamp",
        "events",
        ["timestamp"],
        postgresql_ops={"timestamp": "DESC"},
    )
    op.create_index("idx_events_event_type", "events", ["event_type"])
    op.create_index("idx_events_device_id", "events", ["device_id"])


def downgrade() -> None:
    # Drop new tables
    op.drop_table("events")
    op.drop_table("scans")
    op.drop_table("annotations")

    # Restore old device columns
    op.add_column(
        "devices",
        sa.Column(
            "device_type", sa.String(50), nullable=False, server_default="unknown"
        ),
    )
    op.add_column(
        "devices",
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="unknown"
        ),
    )

    # Restore old unique constraints
    op.create_unique_constraint("devices_hostname_key", "devices", ["hostname"])
    op.create_unique_constraint("devices_ip_address_key", "devices", ["ip_address"])

    # Drop new constraints and indexes
    op.drop_constraint("uq_devices_mac_address", "devices", type_="unique")
    op.drop_index("idx_devices_ip", "devices")
    op.drop_index("idx_devices_is_online", "devices")

    # Drop new columns
    op.drop_column("devices", "mac_address")
    op.drop_column("devices", "vendor")
    op.drop_column("devices", "first_seen")
    op.drop_column("devices", "last_seen")
    op.drop_column("devices", "is_online")
    op.drop_column("devices", "consecutive_missed_scans")
    op.drop_column("devices", "is_known_device")
