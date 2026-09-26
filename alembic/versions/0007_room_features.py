"""채팅방 기능: 초대 링크, 사진, 메시지 부가 정보, 카카오 알림 토큰

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("invite_required", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("room_messages", sa.Column("meta", JSONB()))
    op.add_column("oauth_accounts", sa.Column("talk_refresh_enc", sa.Text()))
    op.add_column("oauth_accounts", sa.Column("talk_refresh_expires_at", sa.DateTime(timezone=True)))
    op.create_table(
        "room_invites",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("created_by", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("uses", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_room_invites_room_id", "room_invites", ["room_id"])
    op.create_table(
        "attachments",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text()),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_attachments_room_id", "attachments", ["room_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_room_id", table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("ix_room_invites_room_id", table_name="room_invites")
    op.drop_table("room_invites")
    op.drop_column("oauth_accounts", "talk_refresh_expires_at")
    op.drop_column("oauth_accounts", "talk_refresh_enc")
    op.drop_column("room_messages", "meta")
    op.drop_column("rooms", "invite_required")
