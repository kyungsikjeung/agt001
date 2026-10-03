"""휴대폰 알림(웹 푸시) 구독 (OWNER_NOTIFY_PLAN N1).

로그인한 사람의 기기마다 한 줄. 탈퇴하면 지운다(accounts.withdraw), users가 지워지면 같이 지워진다.

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False, unique=True),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("label", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("last_ok_at", sa.DateTime(timezone=True)),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_push_subscriptions_user", "push_subscriptions", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_subscriptions_user", table_name="push_subscriptions")
    op.drop_table("push_subscriptions")
