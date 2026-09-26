"""관리자 사이트(D49·D50): 암호화 키 저장소, 이전 키(7일 되돌리기), 관리자 행동 기록

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "secrets",
        sa.Column("name", sa.Text(), primary_key=True),
        sa.Column("value_enc", sa.Text(), nullable=False),
        sa.Column("last4", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_by", sa.Text(), nullable=False),
    )
    op.create_table(
        "secret_versions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("value_enc", sa.Text(), nullable=False),
        sa.Column("last4", sa.Text(), nullable=False),
        sa.Column("replaced_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("replaced_by", sa.Text(), nullable=False),
    )
    op.create_index("ix_secret_versions_name", "secret_versions", ["name", "replaced_at"])
    op.create_table(
        "admin_audit",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target", sa.Text()),
        sa.Column("detail", JSONB()),
    )
    op.create_index("ix_admin_audit_ts", "admin_audit", ["ts"])


def downgrade() -> None:
    op.drop_index("ix_admin_audit_ts", table_name="admin_audit")
    op.drop_table("admin_audit")
    op.drop_index("ix_secret_versions_name", table_name="secret_versions")
    op.drop_table("secret_versions")
    op.drop_table("secrets")
