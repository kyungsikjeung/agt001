"""세션·방·참여자·메시지·투표 초기 스키마 (STAGE0_DESIGN.md §6.2)

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = sa.text("now()")
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("requirement_id", sa.Text(), nullable=False, unique=True),
        sa.Column("last_request", sa.Text()),
        sa.Column("quote", JSONB()),
        sa.Column("codegen", JSONB()),
        sa.Column("design_url", sa.Text()),
        sa.Column("design_preview_url", sa.Text()),
        sa.Column("design_url_unsent", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("deploy_url", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_table(
        "rooms",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("sessions.id"), nullable=False, unique=True),
        sa.Column("ai_status", sa.Text(), nullable=False, server_default="IDLE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_table(
        "room_members",
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("member_id", sa.Text(), primary_key=True),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
    )
    op.create_table(
        "room_messages",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Text(), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("room_id", "seq", name="uq_room_messages_room_seq"),
    )
    op.create_index("ix_room_messages_room_seq", "room_messages", ["room_id", "seq"])
    op.create_table(
        "room_votes",
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("member_id", sa.Text(), primary_key=True),
        sa.Column("vote", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("room_votes")
    op.drop_index("ix_room_messages_room_seq", table_name="room_messages")
    op.drop_table("room_messages")
    op.drop_table("room_members")
    op.drop_table("rooms")
    op.drop_table("sessions")
