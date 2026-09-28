"""손님 명단 바탕 (CUSTOMER_PLAN §1.1)

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("phone_verified_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("site_key", "phone", name="uq_customers_site_phone"),
    )
    op.add_column("inquiries", sa.Column("customer_id", sa.BigInteger(),
                                         sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_inquiries_customer", "inquiries", ["customer_id"])
    op.add_column("bookings", sa.Column("customer_id", sa.BigInteger(),
                                        sa.ForeignKey("customers.id", ondelete="SET NULL"), nullable=True))
    op.create_index("ix_bookings_customer", "bookings", ["customer_id"])


def downgrade() -> None:
    op.drop_index("ix_bookings_customer", table_name="bookings")
    op.drop_column("bookings", "customer_id")
    op.drop_index("ix_inquiries_customer", table_name="inquiries")
    op.drop_column("inquiries", "customer_id")
    op.drop_table("customers")
