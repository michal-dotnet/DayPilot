"""task work_style (assignment / exam)

Revision ID: b7e1c4d9a2f3
Revises: 71adb3a56a45
Create Date: 2026-11-24 23:30:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7e1c4d9a2f3'
down_revision: Union[str, None] = '71adb3a56a45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('work_style', sa.String(length=20), nullable=False, server_default='assignment'))


def downgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('work_style')
