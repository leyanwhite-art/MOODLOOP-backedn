"""convert departments.name to varchar, normalize values, drop enum

Revision ID: a2b8c7e91102
Revises: f1d92a44c810
Create Date: 2026-05-12 02:00:00.000000

The departments.name column was a Postgres ENUM with six fixed labels. To let
admins create arbitrary departments we widen it to VARCHAR. Existing rows are
normalized from enum-member names ("accounting", "human_resources") to the
human-readable titlecase strings the rest of the codebase displays.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a2b8c7e91102"
down_revision: Union[str, None] = "f1d92a44c810"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NORMALIZE_MAP = {
    "accounting": "Accounting",
    "maintenance": "Maintenance",
    "human_resources": "Human Resources",
    "it": "IT",
    "sales": "Sales",
    "marketing": "Marketing",
}


def upgrade() -> None:
    op.alter_column(
        "departments", "name",
        existing_type=sa.Enum(name="departmentnameenum"),
        type_=sa.String(length=255),
        existing_nullable=False,
        postgresql_using="name::text",
    )
    for legacy, titled in _NORMALIZE_MAP.items():
        op.execute(
            sa.text("UPDATE departments SET name = :titled WHERE name = :legacy")
            .bindparams(titled=titled, legacy=legacy)
        )
    op.execute("DROP TYPE IF EXISTS departmentnameenum")


def downgrade() -> None:
    # The new column may contain admin-created departments that don't fit the
    # original 6-value enum. Refuse rather than silently losing data.
    raise RuntimeError(
        "Cannot safely downgrade a2b8c7e91102 — departments.name may contain "
        "admin-created values that do not map back to the original enum."
    )
