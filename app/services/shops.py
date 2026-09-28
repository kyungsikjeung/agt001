"""가게 행 (OWNER_CONSOLE_PLAN §2 4번, SALES_DB_PLAN §4.1).

공개할 때 shops 행을 만들고, 방장이 로그인해 방을 붙였으면 그 계정을 owner로 둔다. 여러 번 불려도 같다.
권한 한 곳 모으기(`require`)는 OWNER_CONSOLE O1에서 이 파일에 더한다.
"""
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import store
from app.db.models import ShopMemberRow, ShopRow, UserRoomRow
from app.db.session import get_sessionmaker
from app.services import rooms


def ensure(site_key: str, name: Optional[str], room_id: Optional[str]) -> None:
    owner_user = None
    room = store.read_room(room_id) if room_id else None
    oid = rooms.owner_id(room) if room else None
    with get_sessionmaker()() as db, db.begin():
        ins = pg_insert(ShopRow).values(site_key=site_key, name=name or None)
        db.execute(ins.on_conflict_do_update(index_elements=["site_key"],
                                             set_={"name": func.coalesce(ins.excluded.name, ShopRow.name)}))
        if oid:
            owner_user = db.scalar(select(UserRoomRow.user_id).where(
                UserRoomRow.room_id == room_id, UserRoomRow.member_id == oid).order_by(UserRoomRow.claimed_at))
        if owner_user and not db.scalar(select(ShopMemberRow.user_id).where(
                ShopMemberRow.site_key == site_key, ShopMemberRow.role == "owner")):
            db.execute(pg_insert(ShopMemberRow).values(site_key=site_key, user_id=owner_user, role="owner")
                       .on_conflict_do_update(index_elements=["site_key", "user_id"], set_={"role": "owner"}))
