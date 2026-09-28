"""가게별 설정 저장 (OWNER_SETTINGS_PLAN §1.2)

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shop_settings",
        sa.Column("site_key", sa.Text(), primary_key=True),
        sa.Column("phone_verify", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("solapi_key_enc", sa.Text()),
        sa.Column("solapi_secret_enc", sa.Text()),
        sa.Column("sms_sender", sa.Text()),
        sa.Column("key_last4", sa.Text()),
        sa.Column("updated_by", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("shop_settings")
