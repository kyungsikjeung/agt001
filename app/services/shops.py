"""가게와 가게 권한 (BOOKING_BOT_IMPL_PLAN OWN-1~OWN-5).

권한 확인은 require_member 한 곳을 지난다. 멤버 행이 없어도 옛 방식(방장이 방을 계정에 붙임)으로
주인이면 그 자리에서 가게·owner 행을 만든다(지연 이행). 한 번 붙은 뒤에는 방장을 넘겨도 가게 주인은 그대로다.
"""
import datetime
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import store
from app.db.models import AdminAuditRow, RoomRow, SessionRow, ShopMemberRow, ShopRow, UserRoomRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token

log = logging.getLogger(__name__)

ROLES = ("owner", "staff")


class NotMember(Exception):
    """권한 없음. API는 404로 답한다(남의 가게가 있는지 알리지 않음)."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def ensure(db, site_key: str, name: Optional[str] = None) -> int:
    """가게 ID (없으면 만든다). 넘겨받은 트랜잭션 안에서 쓴다."""
    row_id = db.scalar(pg_insert(ShopRow).values(site_key=site_key, name=name)
                       .on_conflict_do_nothing(index_elements=["site_key"]).returning(ShopRow.id))
    if row_id is None:
        row_id = db.scalar(select(ShopRow.id).where(ShopRow.site_key == site_key))
    return row_id


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
            shop_id = ensure(db, key, _shop_name(session) or None)
            has_owner = db.scalar(select(ShopMemberRow.user_id).where(
                ShopMemberRow.shop_id == shop_id, ShopMemberRow.role == "owner"))
            if has_owner is None:
                db.execute(pg_insert(ShopMemberRow).values(shop_id=shop_id, user_id=user_id, role="owner")
                           .on_conflict_do_nothing())


def member_sites(user_id: str) -> list[dict]:
    """이 계정이 멤버인 가게 {shop_id, site_key, role, room_id, shop_name, published}."""
    if not user_id:
        return []
    _adopt_legacy(user_id)
    with get_sessionmaker()() as db:
        rows = db.execute(
            select(ShopRow.id, ShopRow.site_key, ShopMemberRow.role, RoomRow.id.label("room_id"), SessionRow.prd)
            .join(ShopMemberRow, ShopMemberRow.shop_id == ShopRow.id)
            .outerjoin(SessionRow, SessionRow.requirement_id == ShopRow.site_key)
            .outerjoin(RoomRow, RoomRow.session_id == SessionRow.id)
            .where(ShopMemberRow.user_id == user_id, ShopRow.closed_at.is_(None))
            .order_by(ShopRow.id)).all()
    out = []
    for r in rows:
        prd = r.prd if isinstance(r.prd, dict) else {}
        out.append({"shop_id": r.id, "site_key": r.site_key, "role": r.role, "room_id": r.room_id,
                    "shop_name": _shop_name({"prd": prd}), "published": bool(prd.get("published"))})
    return out


def require_member(user_id: Optional[str], site_key: str, roles: tuple = ROLES) -> int:
    """가게 ID. 멤버가 아니거나 역할이 맞지 않으면 NotMember."""
    key = sanitize_token(site_key or "")
    if not user_id or not key:
        raise NotMember()
    for s in member_sites(user_id):
        if s["site_key"] == key and s["role"] in roles:
            return s["shop_id"]
    raise NotMember()


def shop_id_for(site_key: str) -> Optional[int]:
    with get_sessionmaker()() as db:
        return db.scalar(select(ShopRow.id).where(ShopRow.site_key == site_key))


def mark_verified(admin_user_id: str, site_key: str, kind: str, biz_no: Optional[str] = None) -> dict:
    """고객센터로 받은 가게 확인(phone)·사업자 확인(biz)을 운영자가 처리한다. admin_audit에 남긴다."""
    if kind not in ("phone", "biz"):
        raise ValueError("kind는 phone 또는 biz")
    digits = "".join(ch for ch in (biz_no or "") if ch.isdigit())
    if kind == "biz" and len(digits) != 10:
        raise ValueError("사업자등록번호는 숫자 10자리")
    with get_sessionmaker()() as db, db.begin():
        shop = db.get(ShopRow, ensure(db, site_key))
        if kind == "phone":
            shop.phone_verified_at = _now()
        else:
            shop.biz_no = digits
            shop.biz_verified_at = _now()
        shop.verified_by = admin_user_id
        db.add(AdminAuditRow(user_id=admin_user_id, action=f"shop_verify_{kind}", target=site_key))
        return {"phone_verified": shop.phone_verified_at is not None,
                "biz_verified": shop.biz_verified_at is not None}
