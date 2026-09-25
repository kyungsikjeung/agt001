"""생성 사이트 문의 (플랫폼 공용 ① 문의 받기)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "inquiries",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("site_key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("contact", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
    )
    op.create_index("ix_inquiries_site", "inquiries", ["site_key", "id"])
    op.create_index("ix_inquiries_ts", "inquiries", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_inquiries_ts", table_name="inquiries")
    op.drop_index("ix_inquiries_site", table_name="inquiries")
    op.drop_table("inquiries")
