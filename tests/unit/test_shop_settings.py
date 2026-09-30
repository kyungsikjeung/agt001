"""가게별 설정 저장·문자 키 (OWNER_SETTINGS_PLAN §1.2·§1.3·§1.4)."""
import logging
import secrets

import pytest
from sqlalchemy import delete, update

from app import store
from app.config import settings
from app.db.models import SessionRow, ShopSettingsRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import shop_settings, sms
from app.services.shop_settings import SettingsError


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-enc-key-0123456789abcdef")
    monkeypatch.setattr(settings, "solapi_api_key", None)
    monkeypatch.setattr(settings, "solapi_api_secret", None)
    monkeypatch.setattr(settings, "sms_sender", None)
    monkeypatch.setattr(settings, "sms_dev_mode", False)
    monkeypatch.setattr(settings, "public_base_url", None)
    monkeypatch.setattr(settings, "portone_store_id", None)
    monkeypatch.setattr(settings, "portone_channel_key", None)
    monkeypatch.setattr(settings, "portone_api_secret", None)
    monkeypatch.setattr(settings, "portone_webhook_secret", None)
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


def _user_with_claim(room_id, member_id="owner", user_id=None):
    uid = user_id or f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id=member_id))
    return uid


def test_owned_sites_only_owner_rooms(client):
    room_id, key = _room(client, shop_name="단정손끝", published=True)
    uid = _user_with_claim(room_id, "owner")
    other_room, _ = _room(client, shop_name="다른 가게")
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=other_room, member_id="guest"))
    sites = shop_settings.owned_sites(uid)
    assert len(sites) == 1
    assert sites[0] == {"site_key": key, "room_id": room_id, "shop_name": "단정손끝", "published": True}
    assert shop_settings.can_edit(uid, key) is True


def test_owned_sites_shop_name_fallback_and_unpublished(client):
    room_id, key = _room(client, shop_name="", published=False)
    uid = _user_with_claim(room_id, "owner")
    sites = shop_settings.owned_sites(uid)
    assert sites[0]["shop_name"] == ""
    assert sites[0]["published"] is False
    assert shop_settings.can_edit("nobody", key) is False


def test_update_requires_ownership(client):
    _, key = _room(client)
    with pytest.raises(PermissionError):
        shop_settings.update("nobody", key, phone_verify=True)


def test_encrypt_roundtrip_and_get_hides_secrets(client):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    out = shop_settings.update(uid, key, solapi_key="SOLAPIKEY1234", solapi_secret="SECRET5678",
                               sms_sender="010-1234-5678")
    assert out["own_key"] is True and out["key_last4"] == "1234" and out["sms_sender"] == "01012345678"
    assert shop_settings.sms_credentials(key) == ("SOLAPIKEY1234", "SECRET5678", "01012345678")
    got = shop_settings.get(key)
    assert got["own_key"] is True and got["key_last4"] == "1234"
    blob = repr(got)
    assert "SOLAPIKEY1234" not in blob and "SECRET5678" not in blob
    assert "solapi_key" not in got and "secret" not in " ".join(got.keys())


def test_partial_key_set_rejected(client):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    with pytest.raises(SettingsError):
        shop_settings.update(uid, key, solapi_key="ONLYKEY12345", solapi_secret=None, sms_sender="01011112222")
    with pytest.raises(SettingsError):
        shop_settings.update(uid, key, solapi_key="ONLYKEY12345", solapi_secret="SECRET5678",
                             sms_sender=None)
    assert shop_settings.sms_credentials(key) is None


def test_clear_key_removes(client):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    shop_settings.update(uid, key, solapi_key="SOLAPIKEY1234", solapi_secret="SECRET5678",
                         sms_sender="01011112222")
    out = shop_settings.update(uid, key, clear_key=True)
    assert out["own_key"] is False and out["key_last4"] == "" and out["sms_sender"] == ""
    assert shop_settings.sms_credentials(key) is None


def test_no_enc_key_blocks_key_save_but_toggle_saves(client, monkeypatch):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    monkeypatch.setattr(settings, "token_enc_key", None)
    with pytest.raises(SettingsError, match="서버 설정 때문에 지금은 자기 키를 넣을 수 없어요"):
        shop_settings.update(uid, key, solapi_key="SOLAPIKEY1234", solapi_secret="SECRET5678",
                             sms_sender="01011112222")
    out = shop_settings.update(uid, key, phone_verify=True)
    assert out["phone_verify"] is True


class _Resp:
    def __init__(self, status_code):
        self.status_code = status_code


def test_sms_send_uses_shop_creds_first(client, monkeypatch):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    shop_settings.update(uid, key, solapi_key="SHOPKEY9999", solapi_secret="SHOPSECRET99",
                         sms_sender="01099998888")
    monkeypatch.setattr(settings, "solapi_api_key", "PLATFORMKEY1")
    monkeypatch.setattr(settings, "solapi_api_secret", "PLATFORMSEC1")
    monkeypatch.setattr(settings, "sms_sender", "01000001111")
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["url"] = url
        seen["json"] = json
        seen["headers"] = headers
        return _Resp(200)

    monkeypatch.setattr(sms.httpx, "post", fake_post)
    assert sms.send("010-1234-5678", "본문", site_key=key) is True
    assert seen["json"]["message"]["from"] == "01099998888"
    assert "SHOPKEY9999" in seen["headers"]["Authorization"]
    assert "PLATFORMKEY1" not in seen["headers"]["Authorization"]


def test_sms_send_falls_back_to_platform(client, monkeypatch):
    _, key = _room(client)
    monkeypatch.setattr(settings, "solapi_api_key", "PLATFORMKEY1")
    monkeypatch.setattr(settings, "solapi_api_secret", "PLATFORMSEC1")
    monkeypatch.setattr(settings, "sms_sender", "01000001111")
    seen = {}
    monkeypatch.setattr(sms.httpx, "post",
                        lambda url, json=None, headers=None, timeout=None: seen.update(
                            json=json, headers=headers) or _Resp(200))
    assert sms.send("010-1234-5678", "본문", site_key=key) is True
    assert seen["json"]["message"]["from"] == "01000001111"


def test_sms_send_dev_mode_logs_last4_only(client, caplog):
    with caplog.at_level(logging.WARNING):
        assert sms.send("010-1234-5678", "인증번호 123456", site_key="no-such-site") is True
    assert "5678" in caplog.text
    assert "010-1234-5678" not in caplog.text and "01012345678" not in caplog.text


def test_sms_send_failure_false_no_raise(client, monkeypatch):
    _, key = _room(client)
    monkeypatch.setattr(settings, "solapi_api_key", "PLATFORMKEY1")
    monkeypatch.setattr(settings, "solapi_api_secret", "PLATFORMSEC1")
    monkeypatch.setattr(settings, "sms_sender", "01000001111")

    def boom(url, json=None, headers=None, timeout=None):
        raise sms.httpx.ConnectError("끊김")

    monkeypatch.setattr(sms.httpx, "post", boom)
    assert sms.send("010-1234-5678", "본문", site_key=key) is False
    monkeypatch.setattr(sms.httpx, "post", lambda *a, **k: _Resp(400))
    assert sms.send("010-1234-5678", "본문", site_key=key) is False


def test_available_cases(client, monkeypatch):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    assert sms.available(key) is False
    monkeypatch.setattr(settings, "sms_dev_mode", True)
    assert sms.available(key) is True
    monkeypatch.setattr(settings, "sms_dev_mode", False)
    monkeypatch.setattr(settings, "solapi_api_key", "PLATFORMKEY1")
    monkeypatch.setattr(settings, "solapi_api_secret", "PLATFORMSEC1")
    monkeypatch.setattr(settings, "sms_sender", "01000001111")
    assert sms.available(key) is True
    monkeypatch.setattr(settings, "solapi_api_key", None)
    assert sms.available(key) is False
    shop_settings.update(uid, key, solapi_key="SHOPKEY9999", solapi_secret="SHOPSECRET99",
                         sms_sender="01099998888")
    assert sms.available(key) is True


def test_phone_verify_on_needs_flag_and_available(client, monkeypatch):
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    assert shop_settings.phone_verify_on(key) is False
    shop_settings.update(uid, key, phone_verify=True)
    assert shop_settings.phone_verify_on(key) is False  # 키 없음 + 개발 모드 끔
    monkeypatch.setattr(settings, "sms_dev_mode", True)
    assert shop_settings.phone_verify_on(key) is True
    monkeypatch.setattr(settings, "sms_dev_mode", False)
    shop_settings.update(uid, key, solapi_key="SHOPKEY9999", solapi_secret="SHOPSECRET99",
                         sms_sender="01099998888")
    assert shop_settings.phone_verify_on(key) is True
    shop_settings.update(uid, key, phone_verify=False)
    assert shop_settings.phone_verify_on(key) is False


def test_check_key(monkeypatch):
    seen = {}
    monkeypatch.setattr(sms.httpx, "get",
                        lambda url, headers=None, timeout=None: seen.update(
                            url=url, headers=headers) or _Resp(200))
    assert sms.check_key("MYKEY12345", "MYSECRET12") is True
    assert seen["url"] == sms.BALANCE_URL
    assert "MYKEY12345" in seen["headers"]["Authorization"]
    monkeypatch.setattr(sms.httpx, "get", lambda *a, **k: _Resp(401))
    assert sms.check_key("MYKEY12345", "MYSECRET12") is False

    def boom(*a, **k):
        raise sms.httpx.ConnectError("끊김")

    monkeypatch.setattr(sms.httpx, "get", boom)
    assert sms.check_key("MYKEY12345", "MYSECRET12") is False
    assert sms.check_key("", "MYSECRET12") is False


def test_order_on_needs_payments_ready(client):
    """PAY_WAVE3_CONTRACT §6 테스트 1: 준비 안 되면 켜기 거절, 끄기는 됨."""
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    assert shop_settings.get(key)["order_on"] is False
    with pytest.raises(ValueError, match="결제 준비 중"):
        shop_settings.update(uid, key, order_on=True)
    out = shop_settings.update(uid, key, order_on=False)
    assert out["order_on"] is False
    assert shop_settings.get(key)["order_on"] is False


def test_order_on_ready_on_off(client, monkeypatch):
    """준비되면(상점 ID·채널 키·API 시크릿) 켜짐·끄기 가능."""
    from app.services import keystore
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    monkeypatch.setattr(settings, "portone_store_id", "store-test-123")
    monkeypatch.setattr(settings, "portone_channel_key", "channel-test-123")
    monkeypatch.setattr(settings, "portone_api_secret", "secret-test-123")
    keystore.invalidate()
    out = shop_settings.update(uid, key, order_on=True)
    assert out["order_on"] is True
    assert shop_settings.get(key)["order_on"] is True
    out = shop_settings.update(uid, key, order_on=False)
    assert out["order_on"] is False
    assert shop_settings.get(key)["order_on"] is False


def test_order_on_api_400_when_not_ready(client):
    """준비 안 되면 API는 400."""
    from app.services import auth as auth_svc
    room_id, key = _room(client)
    uid = _user_with_claim(room_id)
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    r = client.put(f"/api/me/shops/{key}/settings", json={"order_on": True},
                   headers={"Origin": "http://testserver"})
    assert r.status_code == 400
    assert "결제 준비 중" in r.json()["detail"]


def test_migration_0017_adds_order_on_column(client):
    """0017: shop_settings.order_on 칸이 not null default false로 있다."""
    from sqlalchemy import text
    with get_sessionmaker()() as db:
        row = db.execute(text(
            "SELECT is_nullable, column_default FROM information_schema.columns "
            "WHERE table_name='shop_settings' AND column_name='order_on'")).one()
    assert row[0] == "NO"
    assert row[1] is not None
