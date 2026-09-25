"""계정: users, oauth_accounts, login_sessions, oauth_states, user_rooms (1-1·1-3)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    now = sa.text("now()")
    op.create_table(
        "users",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("email", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "oauth_accounts",
        sa.Column("provider", sa.Text(), primary_key=True),
        sa.Column("provider_user_id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )
    op.create_table(
        "login_sessions",
        sa.Column("token_hash", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "oauth_states",
        sa.Column("state_hash", sa.Text(), primary_key=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("code_verifier", sa.Text(), nullable=False),
        sa.Column("next_path", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "user_rooms",
        sa.Column("user_id", sa.Text(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("room_id", sa.Text(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("member_id", sa.Text(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False, server_default=now),
    )


def downgrade() -> None:
    for name in ("user_rooms", "oauth_states", "login_sessions", "oauth_accounts", "users"):
        op.drop_table(name)
