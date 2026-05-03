"""infra updates table — track docker compose pull/up runs

Revision ID: 011_infra_updates
Revises: 010_tank_thresholds
Create Date: 2026-05-03

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_infra_updates"
down_revision: Union[str, None] = "010_tank_thresholds"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "infra_updates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stack_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("output", sa.Text(), nullable=False, server_default=""),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed', 'timeout')",
            name="infra_updates_status_check",
        ),
    )
    op.create_index(
        "idx_infra_updates_stack_started",
        "infra_updates",
        ["stack_key", sa.text("started_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("idx_infra_updates_stack_started", table_name="infra_updates")
    op.drop_table("infra_updates")
