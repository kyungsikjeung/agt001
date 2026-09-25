"""대화 턴 기록 (원문 + 엔진 판단, AI 성능 평가용)

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "chat_turns",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("room_id", sa.Text()),
        sa.Column("author", sa.Text()),
        sa.Column("user_text", sa.Text(), nullable=False),
        sa.Column("ai_text", sa.Text(), nullable=False),
        sa.Column("state_before", sa.Text(), nullable=False),
        sa.Column("state_after", sa.Text(), nullable=False),
        sa.Column("meta", JSONB()),
    )
    op.create_index("ix_chat_turns_session", "chat_turns", ["session_id", "id"])
    op.create_index("ix_chat_turns_ts", "chat_turns", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_chat_turns_ts", table_name="chat_turns")
    op.drop_index("ix_chat_turns_session", table_name="chat_turns")
    op.drop_table("chat_turns")
