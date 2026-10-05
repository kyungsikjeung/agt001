"""거래기록 분리 보관 (RECORD_RETENTION_REVIEW §4-B).

프로젝트를 지우면 사이트·대화·사진·손님 명단은 30일 뒤 지우지만, 주문·결제·환불·정산은
법정 보존 기간(전자상거래법 시행령 제6조: 대금결제·공급, 계약·청약철회 각 5년) 때문에 지울 수 없다.
개인정보보호법 제21조 제3항은 그렇게 남길 개인정보를 **다른 개인정보와 분리해 저장·관리**하라고 한다.
그래서 이 표 하나에만 옮겨 두고(손님 이름·전화는 가려서), 기간이 지나면 자동 파기한다.

shops를 가리키는 외래키를 두지 않는다 — 가게 행이 지워진 뒤에도 남아야 하는 기록이다.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "archived_transactions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("site_key", sa.Text, nullable=False),  # 외래키 없음(가게가 지워진 뒤에도 남는다)
        sa.Column("kind", sa.Text, nullable=False),  # order · payment · subscription
        sa.Column("ref", sa.Text),  # 찾기용: 주문번호·결제번호
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", postgresql.JSONB, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.CheckConstraint("kind IN ('order', 'payment', 'subscription')", name="ck_archived_kind"),
    )
    op.create_index("ix_archived_site", "archived_transactions", ["site_key", "occurred_at"])
    op.create_index("ix_archived_purge", "archived_transactions", ["purge_after"])


def downgrade() -> None:
    op.drop_index("ix_archived_purge", table_name="archived_transactions")
    op.drop_index("ix_archived_site", table_name="archived_transactions")
    op.drop_table("archived_transactions")
