"""가게·가게 멤버 (BOOKING_BOT_IMPL_PLAN OWN-1, SALES_DB_PLAN §4.1과 같은 모양)

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shops",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text(), nullable=False, unique=True),
        sa.Column("name", sa.Text()),
        sa.Column("category", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        # 고객센터로 받은 가게 확인(L2)·사업자 확인(L3). 운영자가 처리한다(AI_BOOKING_AGENT_PLAN §5.2).
        sa.Column("phone_verified_at", sa.DateTime(timezone=True)),
        sa.Column("biz_no", sa.Text()),
        sa.Column("biz_verified_at", sa.DateTime(timezone=True)),
        sa.Column("verified_by", sa.Text()),
    )
    op.create_table(
        "shop_members",
        sa.Column("shop_id", sa.BigInteger(), sa.ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("role IN ('owner', 'staff')", name="ck_shop_members_role"),
    )
    op.create_index("ix_shop_members_user", "shop_members", ["user_id"])
    # 가게당 주인은 한 명
    op.create_index("uq_shop_members_owner", "shop_members", ["shop_id"], unique=True,
                    postgresql_where=sa.text("role = 'owner'"))


def downgrade() -> None:
    op.drop_table("shop_members")
    op.drop_table("shops")
