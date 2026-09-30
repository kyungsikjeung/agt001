"""온라인 주문 받기 스위치 (PAY_WAVE3_CONTRACT §2.1).

shop_settings에 order_on 한 칸을 더한다.

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("shop_settings", sa.Column("order_on", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("shop_settings", "order_on")
