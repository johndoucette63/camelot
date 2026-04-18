"""frigate nvr rule thresholds (feature 017)

Seeds three rows in the existing ``alert_thresholds`` table for the two new
Frigate rules:

  - ``frigate_storage_fill_percent``      -> FR-034/35: alert when /mnt/frigate
    fill percent meets/exceeds this threshold.
  - ``frigate_detection_latency_p95_ms``  -> FR-036: alert when P95 detection
    latency (ms) meets/exceeds this threshold.
  - ``frigate_detection_latency_window_s`` -> FR-036/37: the sustained
    observation window (seconds) over which P95 is computed. Lives as its
    own row because ``alert_thresholds`` has no ``window_seconds`` column —
    see data-model.md.

Data-only — no schema changes. Downgrade removes the three rows only.

Revision ID: 009_frigate_thresholds
Revises: 008_home_assistant_integration
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op

revision: str = "009_frigate_thresholds"
down_revision: Union[str, None] = "008_home_assistant_integration"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO alert_thresholds (key, value, unit, default_value, min_value, max_value)
        VALUES
            ('frigate_storage_fill_percent',       85,    '%',  85,    50,    99),
            ('frigate_detection_latency_p95_ms',   2000,  'ms', 2000,  500,   10000),
            ('frigate_detection_latency_window_s', 300,   's',  300,   60,    3600)
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM alert_thresholds
        WHERE key IN (
            'frigate_storage_fill_percent',
            'frigate_detection_latency_p95_ms',
            'frigate_detection_latency_window_s'
        )
        """
    )
