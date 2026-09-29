"""가게·권한 (BOOKING_BOT_IMPL_PLAN OWN-1~OWN-5)."""
import secrets

import pytest
from sqlalchemy import select

from app import store
from app.db.models import AdminAuditRow, ShopMemberRow, ShopRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import shops


def _room(client, member_id="owner"):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": member_id, "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    return room_id, key


def _user():
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사람"))
    return uid


def _claim(uid, room_id, member_id):
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id=member_id))


def test_claimed_owner_becomes_shop_owner(client):
    room_id, key = _room(client)
    uid = _user()
    _claim(uid, room_id, "owner")
    sites = shops.member_sites(uid)
    assert [(s["site_key"], s["role"], s["room_id"]) for s in sites] == [(key, "owner", room_id)]
    assert shops.require_member(uid, key) == sites[0]["shop_id"]


def test_non_owner_member_gets_nothing(client):
    room_id, key = _room(client)
    client.post(f"/room/{room_id}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    uid = _user()
    _claim(uid, room_id, "guest")
    assert shops.member_sites(uid) == []
    with pytest.raises(shops.NotMember):
        shops.require_member(uid, key)


def test_owner_is_sticky_and_not_stolen(client):
    room_id, key = _room(client)
    first = _user()
    _claim(first, room_id, "owner")
    shops.member_sites(first)
    # 두 번째 계정이 같은 방장 기기로 붙여도 주인은 바뀌지 않는다.
    second = _user()
    _claim(second, room_id, "owner")
    assert shops.member_sites(second) == []
    assert shops.require_member(first, key)


def test_unknown_or_anonymous(client):
    _, key = _room(client)
    with pytest.raises(shops.NotMember):
        shops.require_member(None, key)
    with pytest.raises(shops.NotMember):
        shops.require_member(_user(), "../etc")


def test_staff_role_filter(client):
    room_id, key = _room(client)
    owner = _user()
    _claim(owner, room_id, "owner")
    shop_id = shops.require_member(owner, key)
    staff = _user()
    with get_sessionmaker()() as db, db.begin():
        db.add(ShopMemberRow(site_key=shop_id, user_id=staff, role="staff"))
    assert shops.require_member(staff, key) == shop_id
    with pytest.raises(shops.NotMember):
        shops.require_member(staff, key, roles=("owner",))


def test_mark_verified_records_audit(client):
    _, key = _room(client)
    admin = _user()
    assert shops.mark_verified(admin, key, "phone") == {"phone_verified": True, "biz_verified": False}
    assert shops.mark_verified(admin, key, "biz", "123-45-67890") == {"phone_verified": True, "biz_verified": True}
    with pytest.raises(ValueError):
        shops.mark_verified(admin, key, "biz", "123")
    with get_sessionmaker()() as db:
        shop = db.scalar(select(ShopRow).where(ShopRow.site_key == key))
        assert shop.biz_no == "1234567890" and shop.verified_by == admin
        actions = db.scalars(select(AdminAuditRow.action).where(AdminAuditRow.target == key)).all()
    assert sorted(actions) == ["shop_verify_biz", "shop_verify_phone"]
