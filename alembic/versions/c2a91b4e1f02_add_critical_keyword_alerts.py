"""add critical_keyword_alerts

Revision ID: c2a91b4e1f02
Revises: 61051d22abea
Create Date: 2026-05-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c2a91b4e1f02'
down_revision: Union[str, None] = '61051d22abea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Reuse the existing severityenum type from the department_alarms migration
# rather than re-creating it.
severity_enum = postgresql.ENUM(
    'low', 'medium', 'high', 'critical',
    name='severityenum',
    create_type=False,
)


def upgrade() -> None:
    op.create_table(
        'critical_keyword_alerts',
        sa.Column('alert_id', sa.Integer(), primary_key=True, index=True),
        sa.Column('reflection_id', sa.Integer(), sa.ForeignKey('daily_reflections.reflection_id'), nullable=False),
        sa.Column('employee_id', sa.Integer(), sa.ForeignKey('employees.employee_id'), nullable=False),
        sa.Column('department_id', sa.Integer(), sa.ForeignKey('departments.department_id'), nullable=True),
        sa.Column('matched_keyword', sa.String(), nullable=False),
        sa.Column('snippet', sa.Text(), nullable=False),
        sa.Column('severity', severity_enum, nullable=False, server_default='critical'),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index(
        'ix_critical_keyword_alerts_employee_id',
        'critical_keyword_alerts',
        ['employee_id'],
    )
    op.create_index(
        'ix_critical_keyword_alerts_is_resolved',
        'critical_keyword_alerts',
        ['is_resolved'],
    )


def downgrade() -> None:
    op.drop_index('ix_critical_keyword_alerts_is_resolved', table_name='critical_keyword_alerts')
    op.drop_index('ix_critical_keyword_alerts_employee_id', table_name='critical_keyword_alerts')
    op.drop_table('critical_keyword_alerts')
