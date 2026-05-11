"""create system_settings and activity_logs tables, seed defaults

Revision ID: e7a2c91f5b08
Revises: d3f1a8c2e904
Create Date: 2026-05-12 01:10:00.000000

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e7a2c91f5b08"
down_revision: Union[str, None] = "d3f1a8c2e904"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_SETTINGS = [
    ("alarm_threshold_low", 0.30),
    ("alarm_threshold_medium", 0.50),
    ("alarm_threshold_high", 0.65),
    ("alarm_threshold_critical", 0.80),
    ("alarm_k_anonymity_floor", 5),
    ("reflection_retention_days", 365),
    ("max_reflections_per_day", 3),
    ("reflection_cooldown_hours", 2),
    ("model_hub_id", "ghaida75/arabert-emotions-7class"),
]


def upgrade() -> None:
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("employees.employee_id"), nullable=True),
    )
    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("actor_employee_id", sa.Integer(), sa.ForeignKey("employees.employee_id"), nullable=True),
        sa.Column("actor_role", sa.String(), nullable=True),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("target_type", sa.String(), nullable=True),
        sa.Column("target_id", sa.String(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("ip", sa.String(), nullable=True),
        sa.Column("user_agent", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_activity_logs_action", "activity_logs", ["action"])
    op.create_index("ix_activity_logs_created_at", "activity_logs", ["created_at"])

    # Seed defaults so the API has values to read on first boot.
    settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String),
        sa.column("value", sa.JSON),
        sa.column("updated_at", sa.DateTime),
    )
    op.bulk_insert(
        settings_table,
        [{"key": k, "value": v, "updated_at": None} for k, v in _DEFAULT_SETTINGS],
    )


def downgrade() -> None:
    op.drop_index("ix_activity_logs_created_at", table_name="activity_logs")
    op.drop_index("ix_activity_logs_action", table_name="activity_logs")
    op.drop_table("activity_logs")
    op.drop_table("system_settings")
