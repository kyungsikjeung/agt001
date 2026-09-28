"""사장님 가게 설정 API·페이지 (OWNER_SETTINGS_PLAN §1.5)."""
import secrets

import pytest
from sqlalchemy import delete, update

from app import store
from app.config import settings
from app.db.models import SessionRow, ShopSettingsRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import sms as sms_svc

ORIGIN = "http://testserver"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-enc-key-0123456789abcdef")
    monkeypatch.setattr(settings, "solapi_api_key", None)
    monkeypatch.setattr(settings, "solapi_api_secret", None)
    monkeypatch.setattr(settings, "sms_sender", None)
    monkeypatch.setattr(settings, "sms_dev_mode", False)
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(ShopSettingsRow))


def _room(client, shop_name="우리 가게", published=False):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    room = store.read_room(room_id)
    key = store.read_session(room["session_id"])["requirement_id"]
    prd = {"slots": {"shop_name": {"value": shop_name}}}
    if published:
        prd["published"] = True
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
    return room_id, key


def _owner(room_id, member_id="owner"):
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id=member_id))
    return uid


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


def _origin():
    return {"Origin": ORIGIN}


def test_unauthorized(client):
    room_id, key = _room(client)
    assert client.get("/api/me/shops").status_code == 401
    assert client.put(f"/api/me/shops/{key}/settings", json={"phone_verify": True},
                      headers=_origin()).status_code == 401
    assert client.post(f"/api/me/shops/{key}/sms-test", json={"solapi_key": "k", "solapi_secret": "s"},
                       headers=_origin()).status_code == 401
    assert room_id  # 방은 만들되 로그인 없이는 못 본다


def test_shops_list_only_owner_shops(client):
    room_id, key = _room(client, shop_name="단정손끝", published=True)
    other_room, _ = _room(client, shop_name="다른 가게")
    uid = _owner(room_id, "owner")
    with get_sessionmaker()() as db, db.begin():
        # 방장은 아닌 채로 붙은 방은 목록에 안 나온다
        db.add(UserRoomRow(user_id=uid, room_id=other_room, member_id="guest"))
    _login(client, uid)
    r = client.get("/api/me/shops")
    assert r.status_code == 200
    shops = r.json()["shops"]
    assert len(shops) == 1
    assert shops[0]["site_key"] == key
    assert shops[0]["room_id"] == room_id
    assert shops[0]["shop_name"] == "단정손끝"
    assert shops[0]["published"] is True
    assert shops[0]["settings"] == {"phone_verify": False, "own_key": False, "key_last4": "", "sms_sender": ""}


def test_put_phone_verify_toggle(client):
    room_id, key = _room(client)
    _login(client, _owner(room_id))
    r = client.put(f"/api/me/shops/{key}/settings", json={"phone_verify": True}, headers=_origin())
    assert r.status_code == 200
    assert r.json()["settings"]["phone_verify"] is True
    r = client.put(f"/api/me/shops/{key}/settings", json={"phone_verify": False}, headers=_origin())
    assert r.status_code == 200
    assert r.json()["settings"]["phone_verify"] is False


def test_put_partial_key_400(client):
    room_id, key = _room(client)
    _login(client, _owner(room_id))
    r = client.put(f"/api/me/shops/{key}/settings",
                   json={"solapi_key": "ONLYKEY12345", "sms_sender": "01011112222"}, headers=_origin())
    assert r.status_code == 400
    assert "함께" in r.json()["detail"]


def test_put_other_shop_403(client):
    _, key = _room(client)
    stranger = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=stranger, nickname="낯선 사장님"))
    _login(client, stranger)
    r = client.put(f"/api/me/shops/{key}/settings", json={"phone_verify": True}, headers=_origin())
    assert r.status_code == 403


def test_response_never_contains_secret(client):
    room_id, key = _room(client)
    _login(client, _owner(room_id))
    secret = "VERY-SECRET-99"
    r = client.put(f"/api/me/shops/{key}/settings",
                   json={"solapi_key": "SOLAPIKEY1234", "solapi_secret": secret,
                         "sms_sender": "010-1234-5678"}, headers=_origin())
    assert r.status_code == 200
    body = r.json()["settings"]
    assert body["own_key"] is True and body["key_last4"] == "1234"
    assert secret not in r.text and "SOLAPIKEY1234" not in r.text
    shops = client.get("/api/me/shops")
    assert shops.status_code == 200
    assert secret not in shops.text and "SOLAPIKEY1234" not in shops.text


def test_sms_test_with_mocked_check_key(client, monkeypatch):
    room_id, key = _room(client)
    _login(client, _owner(room_id))
    monkeypatch.setattr(sms_svc, "check_key", lambda k, s: (k, s) == ("GOODKEY", "GOODSECRET"))
    r = client.post(f"/api/me/shops/{key}/sms-test",
                    json={"solapi_key": "GOODKEY", "solapi_secret": "GOODSECRET"}, headers=_origin())
    assert r.status_code == 200 and r.json() == {"ok": True}
    r = client.post(f"/api/me/shops/{key}/sms-test",
                    json={"solapi_key": "BAD", "solapi_secret": "BAD"}, headers=_origin())
    assert r.status_code == 200 and r.json() == {"ok": False}


def test_sms_test_other_shop_403(client, monkeypatch):
    _, key = _room(client)
    stranger = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=stranger, nickname="낯선 사장님"))
    _login(client, stranger)
    monkeypatch.setattr(sms_svc, "check_key", lambda k, s: True)
    r = client.post(f"/api/me/shops/{key}/sms-test",
                    json={"solapi_key": "k", "solapi_secret": "s"}, headers=_origin())
    assert r.status_code == 403


def test_settings_page(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert "가게 설정" in r.text
    assert "로그인이 필요해요" in r.text
    assert "/auth/kakao/start?next=/settings" in r.text
    assert "/auth/google/start?next=/settings" in r.text
    assert "예약 문자 인증" in r.text
