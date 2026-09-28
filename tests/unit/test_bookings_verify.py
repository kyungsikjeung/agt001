"""예약 문자 인증 경로 (CUSTOMER_PLAN §4.1·§4.3 V2 + OWNER_SETTINGS_PLAN §1.4·§1.5):

인증 켜기는 가게별 설정(shop_settings.phone_verify + 문자 보낼 수 있음)이다. 기본 끔(바로 저장).
"""
import datetime
import re

import pytest
from sqlalchemy import delete, update

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.db.models import BookingRow, CustomerRow, PhoneVerificationRow, ShopSettingsRow
from app.db.session import get_sessionmaker
from app.services import bookings
from app.services import sms as sms_svc


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


@pytest.fixture(autouse=True)
def _verify_settings(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-device-key")
    monkeypatch.setattr(settings, "solapi_api_key", None)
    monkeypatch.setattr(settings, "solapi_api_secret", None)
    monkeypatch.setattr(settings, "sms_sender", None)
    monkeypatch.setattr(settings, "sms_dev_mode", False)
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow))  # 하루 5번 제한이 테스트끼리 섞이지 않게


@pytest.fixture
def _sms(monkeypatch):
    sent = []
    monkeypatch.setattr(sms_svc, "send", lambda to, text, site_key=None: sent.append((to, text)) or True)
    return sent


def _verify_on(monkeypatch, key):
    """이 가게에 문자 인증을 켠다(개발 모드라 실제 문자는 안 나간다)."""
    monkeypatch.setattr(settings, "sms_dev_mode", True)
    with get_sessionmaker()() as db, db.begin():
        row = db.get(ShopSettingsRow, key)
        if row is None:
            db.add(ShopSettingsRow(site_key=key, phone_verify=True))
        else:
            row.phone_verify = True


def _site(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    session = store.read_session(store.read_room(room_id)["session_id"])
    return room_id, session["requirement_id"]


def _day(offset=3):
    return (bookings._today() + datetime.timedelta(days=offset)).isoformat()


def _form(phone, **over):
    form = {"date": _day(), "time": "14:30", "service": "컷트", "party": "2", "name": "김손님",
            "phone": phone, "memo": "", "agree": "yes", "website": ""}
    form.update(over)
    return form


def _code_of(text):
    return re.search(r"인증번호 (\d{6})", text).group(1)


def _count(key):
    with get_sessionmaker()() as db:
        return db.query(BookingRow).filter(BookingRow.site_key == key).count()


def _cookie_value(set_cookie, name):
    first = (set_cookie or "").split(";")[0]
    k, _, v = first.partition("=")
    assert k.strip() == name
    return v.strip()


def _start(client, key, phone, **over):
    r = client.post(f"/api/bookings/{key}", data=_form(phone, **over), follow_redirects=False)
    assert r.status_code == 303
    return r.headers["location"]


def test_verify_off_behaves_as_today(client, _sms):
    _, key = _site(client)
    r = client.post(f"/api/bookings/{key}", data=_form("010-2000-0001"), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/api/bookings/{key}/done"
    assert _count(key) == 1 and not _sms


def test_honeypot_with_verify_on_not_saved(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    r = client.post(f"/api/bookings/{key}", data=_form("010-2000-0011", website="http://spam"),
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/api/bookings/{key}/done"
    assert _count(key) == 0 and not _sms


def test_verify_on_redirects_to_verify_page(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    loc = _start(client, key, "010-2000-0002")
    assert loc.startswith(f"/api/bookings/{key}/verify/")
    assert _count(key) == 0 and len(_sms) == 1
    page = client.get(loc)
    assert page.status_code == 200
    assert 'autocomplete="one-time-code"' in page.text
    assert 'name="code"' in page.text and 'pattern="[0-9]{6}"' in page.text
    assert 'maxlength="6"' in page.text and "인증번호 다시 받기" in page.text
    assert "3분 안에 입력해 주세요" in page.text
    assert "<script" not in page.text


def test_wrong_code_400_with_remaining(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    loc = _start(client, key, "010-2000-0003")
    bad = client.post(loc, data={"code": "000000"})
    assert bad.status_code == 400 and "남은 횟수 4번" in bad.text
    assert 'autocomplete="one-time-code"' in bad.text
    assert _count(key) == 0


def test_right_code_stores_booking_verifies_customer_and_sets_cookie(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    phone = "010-2000-0004"
    loc = _start(client, key, phone)
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"] == f"/api/bookings/{key}/done"
    assert _count(key) == 1
    with get_sessionmaker()() as db:
        cust = db.query(CustomerRow).filter(CustomerRow.site_key == key, CustomerRow.phone == "01020000004").one()
        assert cust.phone_verified_at is not None
    jar = (done.headers.get("set-cookie") or "").lower()
    assert f"pv_{key}=" in jar and "httponly" in jar and "secure" in jar
    assert "samesite=lax" in jar and f"path=/api/bookings/{key}" in jar


def test_cookie_skips_sms_for_same_phone(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    phone = "010-2000-0005"
    loc = _start(client, key, phone)
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    cookie = _cookie_value(done.headers.get("set-cookie"), f"pv_{key}")
    _sms.clear()
    r = client.post(f"/api/bookings/{key}", data=_form(phone),
                    cookies={f"pv_{key}": cookie}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/api/bookings/{key}/done"
    assert _count(key) == 2 and not _sms


def test_cookie_different_phone_goes_to_verify(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    loc = _start(client, key, "010-2000-0006")
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    cookie = _cookie_value(done.headers.get("set-cookie"), f"pv_{key}")
    _sms.clear()
    r = client.post(f"/api/bookings/{key}", data=_form("010-2000-0007"),
                    cookies={f"pv_{key}": cookie}, follow_redirects=False)
    assert r.status_code == 303 and "/verify/" in r.headers["location"]
    assert _count(key) == 1 and len(_sms) == 1


def test_resend_after_minute(client, monkeypatch, _sms):
    _, key = _site(client)
    _verify_on(monkeypatch, key)
    loc = _start(client, key, "010-2000-0008")
    old_token = loc.rsplit("/", 1)[-1]
    with get_sessionmaker()() as db, db.begin():  # 다시 보내기 1분 제한을 지난 것으로
        db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == old_token)
                   .values(created_at=datetime.datetime.now(datetime.timezone.utc)
                           - datetime.timedelta(minutes=2)))
    _sms.clear()
    r = client.post(f"{loc}/resend", follow_redirects=False)
    assert r.status_code == 303
    new_loc = r.headers["location"]
    assert new_loc.startswith(f"/api/bookings/{key}/verify/") and new_loc != loc
    old = client.post(loc, data={"code": "000000"})
    assert old.status_code == 400 and "인증 요청을 찾을 수 없어요" in old.text
    done = client.post(new_loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"] == f"/api/bookings/{key}/done"
    assert _count(key) == 1


def test_full_slot_rejected_before_sms(client, monkeypatch, _sms):
    """마감된 시간은 문자를 보내기 전에 거절한다."""
    room_id, key = _site(client)
    day = _day()
    r = client.post(f"/api/bookings/{key}", data=_form("010-2000-0009", date=day, time="14:30"),
                    follow_redirects=False)
    assert r.status_code == 303
    with get_sessionmaker()() as db:
        bid = db.query(BookingRow).filter(BookingRow.site_key == key).one().id
    assert client.post(f"/room/{room_id}/bookings/{bid}/decision", json={"decision": "confirm"},
                       headers={"X-Member-Id": "owner"}).status_code == 200
    _verify_on(monkeypatch, key)
    bad = client.post(f"/api/bookings/{key}", data=_form("010-2000-0010", date=day, time="14:30"),
                      follow_redirects=False)
    assert bad.status_code == 400 and "이미 마감된 시간이에요. 다른 시간을 골라 주세요." in bad.text
    assert _sms == []
    assert _count(key) == 1


def test_invalid_form_rejected_before_sms(client, monkeypatch, _sms):
    """동의 빠짐 같은 틀린 폼은 문자를 보내기 전에 알린다(헛문자 없음)."""
    _room_id, key = _site(client)
    _verify_on(monkeypatch, key)
    res = client.post(f"/api/bookings/{key}", data=_form("010-3333-4444", agree=""), follow_redirects=False)
    assert res.status_code == 400 and "동의" in res.text
    assert _sms == []
