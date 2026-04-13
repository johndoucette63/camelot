"""add monitor_offline flag to devices

Revision ID: 006_device_monitor_offline
Revises: 005_advisor_notes
Create Date: 2026-04-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_device_monitor_offline"
down_revision: Union[str, None] = "005_advisor_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "devices",
        sa.Column(
            "monitor_offline",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("devices", "monitor_offline")
