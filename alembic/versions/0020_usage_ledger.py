"""무료 사용 한도 장부 (USAGE_QUOTA_CONTRACT §1, D40).

가게(사이트 키)·KST 달·종류(design·restyle)마다 지급(grant)·사용(use)·충전(topup)을 적는다.
지급은 (가게, 달, 종류)마다 한 줄만(부분 고유 색인).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "usage_ledger",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text(), nullable=False),
        sa.Column("month", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("action IN ('design', 'restyle')", name="ck_usage_ledger_action"),
        sa.CheckConstraint("kind IN ('grant', 'use', 'topup')", name="ck_usage_ledger_kind"),
    )
    op.create_index("ix_usage_ledger_site_month", "usage_ledger", ["site_key", "month", "action"])
    op.create_index("uq_usage_ledger_grant", "usage_ledger", ["site_key", "month", "action"], unique=True,
                    postgresql_where=sa.text("kind = 'grant'"))


def downgrade() -> None:
    op.drop_index("uq_usage_ledger_grant", table_name="usage_ledger")
    op.drop_index("ix_usage_ledger_site_month", table_name="usage_ledger")
    op.drop_table("usage_ledger")
