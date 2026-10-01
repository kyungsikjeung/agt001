"""손님 ↔ 사장님 채팅 (GUEST_CHAT_CONTRACT §1).

손님 토큰은 원문 없이 해시(token_hash)만 둔다. 마지막 글 뒤 30일이 지나면 지운다(guest_chat.purge).
가게 설정에 '손님 채팅 받기'(기본 켜짐)를 더한다.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guest_chat_threads",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shop_id", sa.Text(), sa.ForeignKey("shops.site_key", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="ai"),
        sa.Column("owner_unread", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("notified_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('ai', 'owner', 'closed', 'blocked')", name="ck_guest_chat_threads_status"),
        sa.UniqueConstraint("shop_id", "token_hash", name="uq_guest_chat_threads_shop_token"),
    )
    op.create_index("ix_guest_chat_threads_shop_last", "guest_chat_threads", ["shop_id", sa.text("last_at DESC")])
    op.create_table(
        "guest_chat_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.BigInteger(), sa.ForeignKey("guest_chat_threads.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("sender", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("sender IN ('guest', 'ai', 'owner')", name="ck_guest_chat_messages_sender"),
        sa.CheckConstraint("char_length(text) BETWEEN 1 AND 500", name="ck_guest_chat_messages_text"),
    )
    op.create_index("ix_guest_chat_messages_thread", "guest_chat_messages", ["thread_id", "id"])
    op.add_column("shop_settings", sa.Column("guest_chat_on", sa.Boolean(), nullable=False,
                                             server_default=sa.text("true")))


def downgrade() -> None:
    op.drop_column("shop_settings", "guest_chat_on")
    op.drop_index("ix_guest_chat_messages_thread", table_name="guest_chat_messages")
    op.drop_table("guest_chat_messages")
    op.drop_index("ix_guest_chat_threads_shop_last", table_name="guest_chat_threads")
    op.drop_table("guest_chat_threads")
