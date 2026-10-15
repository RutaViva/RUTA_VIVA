"""add_inactive_to_driver_status_check

Revision ID: 1c747396d464
Revises: 0001
Create Date: 2026-10-08 09:25:54.843331

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c747396d464'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Elimina el constraint viejo y crea uno nuevo con 'inactive'
    op.drop_constraint('driver_status_check', 'driver', type_='check')
    op.create_check_constraint(
        'driver_status_check',
        'driver',
        "status IN ('active', 'inactive', 'suspended')"
    )

def downgrade() -> None:
    op.drop_constraint('driver_status_check', 'driver', type_='check')
    op.create_check_constraint(
        'driver_status_check',
        'driver',
        "status IN ('active', 'suspended')"
    )