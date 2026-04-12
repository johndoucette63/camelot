"""advisor notes: create notes and rejected_suggestions tables

Revision ID: 005_advisor_notes
Revises: 004_recommendations_alerts
Create Date: 2026-04-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_advisor_notes"
down_revision: Union[str, None] = "004_recommendations_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: Create notes table ──────────────────────────────────────
    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("target_type", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "pinned", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "target_type IN ('device', 'service', 'playbook')",
            name="notes_target_type_check",
        ),
    )

    op.create_index("idx_notes_target", "notes", ["target_type", "target_id"])
    op.create_index("idx_notes_pinned", "notes", ["pinned", "target_type"])
    op.create_index(
        "idx_notes_updated_at", "notes", [sa.text("updated_at DESC")]
    )

    # ── Step 2: Create rejected_suggestions table ───────────────────────
    op.create_table(
        "rejected_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # ── Step 3: Seed playbook entries ───────────────────────────────────
    notes_table = sa.table(
        "notes",
        sa.column("target_type", sa.String),
        sa.column("target_id", sa.Integer),
        sa.column("title", sa.String),
        sa.column("body", sa.Text),
        sa.column("pinned", sa.Boolean),
        sa.column("tags", sa.JSON),
    )
    op.bulk_insert(
        notes_table,
        [
            {
                "target_type": "playbook",
                "target_id": None,
                "title": "NAS RAID Scrub Schedule",
                "body": (
                    "The NAS (192.168.10.105) runs a scheduled RAID scrub every "
                    "Sunday 2:00 AM\u20133:00 AM. During this window the NAS may be "
                    "unresponsive \u2014 this is expected, not an outage."
                ),
                "pinned": True,
                "tags": ["maintenance", "nas"],
            },
            {
                "target_type": "playbook",
                "target_id": None,
                "title": "VPN Credential Rotation",
                "body": (
                    "VPN credentials on the Torrentbox rotate on the first Monday "
                    "of every month. Check 1Password for current credentials after "
                    "rotation."
                ),
                "pinned": False,
                "tags": ["maintenance", "security", "vpn"],
            },
            {
                "target_type": "playbook",
                "target_id": None,
                "title": "DNS Ownership",
                "body": (
                    "Pi-hole DNS runs on 192.168.10.150. Upstream DNS is configured "
                    "in the Pi-hole admin panel. Changes to DNS settings should be "
                    "tested during the maintenance window."
                ),
                "pinned": False,
                "tags": ["dns", "convention"],
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("rejected_suggestions")
    op.drop_table("notes")
