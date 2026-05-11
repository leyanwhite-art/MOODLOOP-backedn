"""add selected_emotion to daily_reflections

Revision ID: b5e7a3c91204
Revises: a2b8c7e91102
Create Date: 2026-05-12 02:30:00.000000

Captures the emotion the employee themselves picked at submission time,
distinct from the model's prediction stored in sentiment_analyses.emotion.
Nullable so legacy / seeded rows that pre-date this field are accepted.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b5e7a3c91204"
down_revision: Union[str, None] = "a2b8c7e91102"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "daily_reflections",
        sa.Column("selected_emotion", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("daily_reflections", "selected_emotion")
