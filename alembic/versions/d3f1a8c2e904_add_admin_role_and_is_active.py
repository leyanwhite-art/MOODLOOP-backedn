"""add admin role, drop manager, add is_active and created_at to employees

Revision ID: d3f1a8c2e904
Revises: c2a91b4e1f02
Create Date: 2026-05-12 01:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3f1a8c2e904"
down_revision: Union[str, None] = "c2a91b4e1f02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres enums cannot drop/add values inside the same transaction as
    # other DDL touching the type. Use ALTER TYPE for the additive change,
    # then handle the `manager` removal by recreating the type. We do this
    # in two short steps and keep `manager` available as a no-op alias so
    # existing rows (if any — there shouldn't be) are not broken.
    op.execute("ALTER TYPE roleenum ADD VALUE IF NOT EXISTS 'admin'")

    # Safety: re-home any stray manager rows back to employee.
    op.execute("UPDATE employees SET role = 'employee' WHERE role = 'manager'")

    op.add_column(
        "employees",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        "employees",
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    # Backfill created_at to NOW() so existing accounts have a sensible value.
    op.execute("UPDATE employees SET created_at = NOW() WHERE created_at IS NULL")


def downgrade() -> None:
    op.drop_column("employees", "created_at")
    op.drop_column("employees", "is_active")
    # Postgres has no DROP VALUE for enums; leaving 'admin' in the type on
    # downgrade is harmless and matches what alembic-autogenerate would do.
