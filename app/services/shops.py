"""가게와 가게 권한 (OWNER_CONSOLE_PLAN §2 4번, SALES_DB_PLAN §4.1, BOOKING_BOT_IMPL_PLAN OWN-1~OWN-5).

가게 열쇠는 site_key(sessions.requirement_id) 하나다. 예약 엔진 표의 shop_id 칸도 site_key 값이다(D55).
공개할 때 ensure()로 shops 행을 만들고, 방장이 로그인해 방을 붙였으면 그 계정을 owner로 둔다.
권한 확인은 require_member 한 곳을 지난다. 멤버 행이 없어도 옛 방식(방장이 방을 계정에 붙임)으로
주인이면 그 자리에서 가게·owner 행을 만든다(지연 이행). 한 번 붙은 뒤에는 방장을 넘겨도 가게 주인은 그대로다.
"""
import datetime
import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import store
from app.db.models import AdminAuditRow, RoomRow, SessionRow, ShopMemberRow, ShopRow, UserRoomRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token

log = logging.getLogger(__name__)

ROLES = ("owner", "manager", "staff")


class NotMember(Exception):
    """권한 없음. API는 404로 답한다(남의 가게가 있는지 알리지 않음)."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def ensure(site_key: str, name: Optional[str], room_id: Optional[str]) -> None:
    owner_user = None
    from app.services import rooms
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


def ensure_in(db, site_key: str, name: Optional[str] = None) -> str:
    """가게 열쇠(site_key). 없으면 만든다. 넘겨받은 트랜잭션 안에서 쓴다."""
    db.execute(pg_insert(ShopRow).values(site_key=site_key, name=name)
               .on_conflict_do_nothing(index_elements=["site_key"]))
    return site_key


def _shop_name(session: Optional[dict]) -> str:
    slot = (((session or {}).get("prd") or {}).get("slots") or {}).get("shop_name") or {}
    raw = slot.get("value") or ""
    return raw.strip() if isinstance(raw, str) else ""


def _adopt_legacy(user_id: str) -> None:
    """계정에 붙인 방 중 방장인 방의 가게를 owner로 옮긴다. 이미 다른 주인이 있으면 건드리지 않는다."""
    with get_sessionmaker()() as db:
        claims = db.execute(select(UserRoomRow.room_id, UserRoomRow.member_id)
                            .where(UserRoomRow.user_id == user_id)).all()
    from app.services import rooms as rooms_svc
    for room_id, member_id in claims:
        room = store.read_room(room_id)
        if room is None or rooms_svc.owner_id(room) != member_id:
            continue
        session = store.read_session(room["session_id"])
        key = (session or {}).get("requirement_id")
        if not key:
            continue
        with get_sessionmaker()() as db, db.begin():
            shop_id = ensure_in(db, key, _shop_name(session) or None)
            has_owner = db.scalar(select(ShopMemberRow.user_id).where(
                ShopMemberRow.site_key == shop_id, ShopMemberRow.role == "owner"))
            if has_owner is None:
                db.execute(pg_insert(ShopMemberRow).values(site_key=shop_id, user_id=user_id, role="owner")
                           .on_conflict_do_nothing())


def member_sites(user_id: str) -> list[dict]:
    """이 계정이 멤버인 가게 {shop_id, site_key, role, room_id, shop_name, published}."""
    if not user_id:
        return []
    _adopt_legacy(user_id)
    with get_sessionmaker()() as db:
        rows = db.execute(
            select(ShopRow.site_key, ShopMemberRow.role, RoomRow.id.label("room_id"), SessionRow.prd)
            .join(ShopMemberRow, ShopMemberRow.site_key == ShopRow.site_key)
            .outerjoin(SessionRow, SessionRow.requirement_id == ShopRow.site_key)
            .outerjoin(RoomRow, RoomRow.session_id == SessionRow.id)
            .where(ShopMemberRow.user_id == user_id, ShopRow.deleted_at.is_(None))
            .order_by(ShopRow.created_at)).all()
    out = []
    for r in rows:
        prd = r.prd if isinstance(r.prd, dict) else {}
        out.append({"shop_id": r.site_key, "site_key": r.site_key, "role": r.role, "room_id": r.room_id,
                    "shop_name": _shop_name({"prd": prd}), "published": bool(prd.get("published"))})
    return out


def require_member(user_id: Optional[str], site_key: str, roles: tuple = ROLES) -> str:
    """가게 열쇠(site_key). 멤버가 아니거나 역할이 맞지 않으면 NotMember."""
    key = sanitize_token(site_key or "")
    if not user_id or not key:
        raise NotMember()
    for s in member_sites(user_id):
        if s["site_key"] == key and s["role"] in roles:
            return s["shop_id"]
    raise NotMember()


def shop_id_for(site_key: str) -> Optional[str]:
    with get_sessionmaker()() as db:
        return db.scalar(select(ShopRow.site_key).where(ShopRow.site_key == site_key))


def mark_verified(admin_user_id: str, site_key: str, kind: str, biz_no: Optional[str] = None) -> dict:
    """고객센터로 받은 가게 확인(phone)·사업자 확인(biz)을 운영자가 처리한다. admin_audit에 남긴다."""
    if kind not in ("phone", "biz"):
        raise ValueError("kind는 phone 또는 biz")
    digits = "".join(ch for ch in (biz_no or "") if ch.isdigit())
    if kind == "biz" and len(digits) != 10:
        raise ValueError("사업자등록번호는 숫자 10자리")
    with get_sessionmaker()() as db, db.begin():
        shop = db.get(ShopRow, ensure_in(db, site_key))
        if kind == "phone":
            shop.phone_verified_at = _now()
        else:
            shop.biz_no = digits
            shop.biz_verified_at = _now()
        shop.verified_by = admin_user_id
        db.add(AdminAuditRow(user_id=admin_user_id, action=f"shop_verify_{kind}", target=site_key))
        return {"phone_verified": shop.phone_verified_at is not None,
                "biz_verified": shop.biz_verified_at is not None}
