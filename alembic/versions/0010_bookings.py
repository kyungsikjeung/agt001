"""생성 사이트 예약 신청 (플랫폼 공용 ② 예약·신청 받기, docs/product/BOOKING_PLAN.md)

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bookings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("site_key", sa.Text(), nullable=False),
        sa.Column("visit_date", sa.Date(), nullable=False),
        sa.Column("visit_time", sa.Text(), nullable=False),
        sa.Column("service", sa.Text()),
        sa.Column("party", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("memo", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="requested"),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_bookings_site", "bookings", ["site_key", "id"])
    op.create_index("ix_bookings_visit", "bookings", ["visit_date"])


def downgrade() -> None:
    op.drop_index("ix_bookings_visit", table_name="bookings")
    op.drop_index("ix_bookings_site", table_name="bookings")
    op.drop_table("bookings")
