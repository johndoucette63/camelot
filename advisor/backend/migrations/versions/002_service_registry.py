"""Service registry and health check tables

Revision ID: 002_service_registry
Revises: 001_network_discovery
Create Date: 2026-04-09

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_service_registry"
down_revision: Union[str, None] = "001_network_discovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Create service_definitions table ─────────────────────────────────
    op.create_table(
        "service_definitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("host_label", sa.String(100), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("check_type", sa.String(10), nullable=False),
        sa.Column("check_url", sa.String(255), nullable=True),
        sa.Column(
            "check_interval_seconds",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column("degraded_threshold_ms", sa.Integer(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint("name", "host", name="uq_service_name_host"),
    )
    op.create_index(
        "idx_service_definitions_host_label",
        "service_definitions",
        ["host_label"],
    )
    op.create_index(
        "idx_service_definitions_enabled",
        "service_definitions",
        ["enabled"],
    )

    # ── Create health_check_results table ────────────────────────────────
    op.create_table(
        "health_check_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "service_id",
            sa.Integer(),
            sa.ForeignKey("service_definitions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "checked_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("response_time_ms", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_hcr_service_checked",
        "health_check_results",
        ["service_id", sa.text("checked_at DESC")],
    )
    op.create_index(
        "idx_hcr_checked_at",
        "health_check_results",
        ["checked_at"],
    )

    # ── Seed service definitions ─────────────────────────────────────────
    op.execute("""
        INSERT INTO service_definitions (name, host_label, host, port, check_type, check_url, degraded_threshold_ms)
        VALUES
            ('Plex',      'HOLYGRAIL',   '192.168.10.129', 32400, 'http', '/identity',    2000),
            ('Ollama',    'HOLYGRAIL',   '192.168.10.129', 11434, 'http', '/api/tags',    2000),
            ('Grafana',   'HOLYGRAIL',   '192.168.10.129', 3000,  'http', '/api/health',  2000),
            ('Portainer', 'HOLYGRAIL',   '192.168.10.129', 9443,  'tcp',  NULL,           NULL),
            ('Traefik',   'HOLYGRAIL',   '192.168.10.129', 8080,  'tcp',  NULL,           NULL),
            ('Advisor',   'HOLYGRAIL',   '127.0.0.1',      8000,  'http', '/health',      2000),
            ('Deluge',    'Torrentbox',  '192.168.10.141', 8112,  'http', '/',            2000),
            ('Sonarr',    'Torrentbox',  '192.168.10.141', 8989,  'http', '/',             2000),
            ('Radarr',    'Torrentbox',  '192.168.10.141', 7878,  'http', '/',             2000),
            ('Prowlarr',  'Torrentbox',  '192.168.10.141', 9696,  'http', '/',            2000),
            ('SMB',       'NAS',         '192.168.10.105', 445,   'tcp',  NULL,           NULL),
            ('Pi-hole',   'Pi-hole DNS', '192.168.10.150', 80,    'http', '/admin/',      2000)
    """)


def downgrade() -> None:
    op.drop_table("health_check_results")
    op.drop_table("service_definitions")
