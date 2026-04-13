"""add device enrichment columns

Revision ID: 007_device_enrichment
Revises: 006_device_monitor_offline
Create Date: 2026-04-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007_device_enrichment"
down_revision: Union[str, None] = "006_device_monitor_offline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Device enrichment columns
    op.add_column("devices", sa.Column("os_family", sa.String(50), nullable=True))
    op.add_column("devices", sa.Column("os_detail", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("mdns_name", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("netbios_name", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("ssdp_friendly_name", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("ssdp_model", sa.String(255), nullable=True))
    op.add_column("devices", sa.Column("last_enriched_at", sa.DateTime(), nullable=True))
    op.add_column("devices", sa.Column("enrichment_ip", sa.String(15), nullable=True))

    # Annotation classification columns
    op.add_column("annotations", sa.Column("classification_source", sa.String(50), nullable=True))
    op.add_column("annotations", sa.Column("classification_confidence", sa.String(10), nullable=True))

    # Backfill: mark existing user-set roles
    op.execute(
        "UPDATE annotations SET classification_source = 'user' WHERE role != 'unknown'"
    )


def downgrade() -> None:
    op.drop_column("annotations", "classification_confidence")
    op.drop_column("annotations", "classification_source")

    op.drop_column("devices", "enrichment_ip")
    op.drop_column("devices", "last_enriched_at")
    op.drop_column("devices", "ssdp_model")
    op.drop_column("devices", "ssdp_friendly_name")
    op.drop_column("devices", "netbios_name")
    op.drop_column("devices", "mdns_name")
    op.drop_column("devices", "os_detail")
    op.drop_column("devices", "os_family")
