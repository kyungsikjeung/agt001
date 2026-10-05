"""프로젝트 삭제 (대표 10/5): 방에 '지운 시각'. 30일 뒤 영구 삭제한다.

지우면 바로 공개 사이트가 내려가고 목록에서는 비활성으로 남는다(되살리기 가능).
30일이 지나면 하루 한 번 도는 청소가 방·세션·가게와 딸린 기록을 모두 지운다(방침 3항).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("deleted_at", sa.DateTime(timezone=True)))
    # 청소가 '지운 지 30일 지난 방'만 훑는다. 안 지운 방(대부분)은 색인에 넣지 않는다.
    op.create_index("ix_rooms_deleted", "rooms", ["deleted_at"],
                    postgresql_where=sa.text("deleted_at IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("ix_rooms_deleted", table_name="rooms")
    op.drop_column("rooms", "deleted_at")
