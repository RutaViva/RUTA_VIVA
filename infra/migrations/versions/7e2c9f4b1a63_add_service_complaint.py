"""Add operational service complaints."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7e2c9f4b1a63"
down_revision: Union[str, Sequence[str], None] = "1c747396d464"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_complaint",
        sa.Column(
            "complaint_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "trip_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trip_request.trip_id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("category", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "category IN ('service', 'fare', 'safety', 'other')",
            name="ck_service_complaint_category",
        ),
        sa.PrimaryKeyConstraint("complaint_id"),
    )
    op.create_index(
        "ix_service_complaint_created_at",
        "service_complaint",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_service_complaint_created_at",
        table_name="service_complaint",
    )
    op.drop_table("service_complaint")
