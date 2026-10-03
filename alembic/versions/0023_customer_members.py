"""손님 회원 (FEATURE_PLATFORM_PLAN §7.1): 가게별 손님 명단에 회원 가입 시각.

전화번호 인증 + 동의로 가입하면 member_since를 채우고, 탈퇴하면 비운다.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("member_since", sa.DateTime(timezone=True)))
    op.create_index("ix_customers_members", "customers", ["site_key"],
                    postgresql_where=sa.text("member_since IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_customers_members", table_name="customers")
    op.drop_column("customers", "member_since")
