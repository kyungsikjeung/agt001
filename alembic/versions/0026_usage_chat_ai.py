"""사용 장부에 '손님 채팅 AI 답'을 센다 (D61 요금제 포함량).

0020의 CHECK는 action을 design·restyle만 허용했다. 요금제가 손님 채팅 AI 답 포함량(무료 월 300건
·가게 1,000·프로 3,000)을 두므로 chat_ai를 허용한다. 알림톡·문자는 선불 충전 쪽이라 여기 없다(F4).

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-06
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_usage_ledger_action", "usage_ledger", type_="check")
    op.create_check_constraint("ck_usage_ledger_action", "usage_ledger",
                               "action IN ('design', 'restyle', 'chat_ai')")


def downgrade() -> None:
    # 되돌리기 전에 chat_ai 줄을 지운다(옛 CHECK가 막는다)
    op.execute("DELETE FROM usage_ledger WHERE action = 'chat_ai'")
    op.drop_constraint("ck_usage_ledger_action", "usage_ledger", type_="check")
    op.create_check_constraint("ck_usage_ledger_action", "usage_ledger",
                               "action IN ('design', 'restyle')")
