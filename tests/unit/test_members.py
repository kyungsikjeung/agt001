"""손님 회원 (FEATURE_PLATFORM_PLAN §7.1, 10/4 대표 결정: 전화번호 인증 · 내역 보기까지만).

빌더 칩으로 켜면 공개 사이트 '내 정보' → 번호 인증 + 동의로 가입 → 이 가게의 내 예약·주문·스탬프 보기.
이 기기에서 나가기·탈퇴, 사장님 '손님' 탭, 우리 문자 키일 때 가게당 하루 30건.
"""
import datetime
import re
import secrets

import pytest
from sqlalchemy import delete, select, update

from app import store
from app.config import settings
from app.db.models import BookingRow, CustomerRow, PhoneVerificationRow, SessionRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import members, site_render, sms

ORIGIN = {"Origin": "http://testserver"}
PHONE = "010-2222-3333"


@pytest.fixture(autouse=True)
def _sms(monkeypatch):
    monkeypatch.setattr(settings, "solapi_api_key", None)
    monkeypatch.setattr(settings, "solapi_api_secret", None)
    monkeypatch.setattr(settings, "sms_sender", None)
    monkeypatch.setattr(settings, "token_enc_key", "test-enc-key-0123456789abcdef")
    monkeypatch.setattr(settings, "sms_dev_mode", True)  # 문자 키 없이도 인증 흐름을 본다(보내기는 아래 가짜)
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow))
    sent = []
    monkeypatch.setattr(sms, "send", lambda to, text, site_key=None: sent.append(text) or True)
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    return sent


def _pension(client):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    body = client.post("/api/start", json={"template": "pension"}).json()
    rid = body["room_id"]
    key = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    return rid, {"X-Member-Id": body["member_id"]}, key


def _join(client, key, sent, phone=PHONE):
    r = client.post(f"/api/members/{key}", data={"phone": phone, "agree": "1"}, follow_redirects=False)
    assert r.status_code == 303, r.text
    verify = r.headers["location"]
    code = re.search(r"인증번호 (\d{6})", sent[-1]).group(1)
    r = client.post(verify, data={"code": code}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/api/members/{key}"
    cookie = re.search(rf"mb_{key}=([^;]+)", r.headers["set-cookie"]).group(1)
    assert "HttpOnly" in r.headers["set-cookie"] and f"Path=/api/members/{key}" in r.headers["set-cookie"]
    client.cookies.set(f"mb_{key}", cookie)
    return cookie


def test_chip_and_first_question_state(client):
    rid, h, key = _pension(client)
    assert client.get(f"/api/rooms/{rid}/card", headers=h).json()["members"] is None  # 아직 안 정함 → 빌더가 묻는다
    chip = {f["key"]: f for f in client.get(f"/api/rooms/{rid}/features", headers=h).json()["features"]}["members"]
    assert chip == {"key": "members", "label": "회원", "kind": "shop", "on": False, "members": True}
    assert client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": False}, headers=h).status_code == 200
    assert client.get(f"/api/rooms/{rid}/card", headers=h).json()["members"] == {"signup": False, "method": "phone"}
    r = client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": True}, headers=h)
    assert {f["key"]: f for f in r.json()["features"]}["members"]["on"] is True
    html = client.get(f"/api/rooms/{rid}/card/preview", headers=h).json()["html"]
    assert f'href="/api/members/{key}"' in html and "내 정보" in html


def test_off_shop_has_no_member_page(client):
    _rid, _h, key = _pension(client)
    assert client.get(f"/api/members/{key}").status_code == 404


def test_join_view_history_logout_leave(client, _sms):
    rid, h, key = _pension(client)
    client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": True}, headers=h)
    page = client.get(f"/api/members/{key}")
    assert page.status_code == 200 and "개인정보 수집·이용에 동의해요 (필수)" in page.text
    assert page.headers["content-security-policy"].startswith("default-src 'none'")
    # 동의 없이는 안 됨
    r = client.post(f"/api/members/{key}", data={"phone": PHONE})
    assert r.status_code == 400 and "동의해야" in r.text
    # 예약 하나(가게 장부) → 가입하면 내 정보에 보인다
    from app.services import customers
    with get_sessionmaker()() as db, db.begin():
        cid = customers.touch(db, key, PHONE, "김손님")
        db.add(BookingRow(site_key=key, visit_date=datetime.date(2026, 10, 9), visit_time="15:00", service="별채",
                          party=2, name="김손님", phone=PHONE, status="confirmed", customer_id=cid))
    _join(client, key, _sms)
    mine = client.get(f"/api/members/{key}")
    assert "내 정보" in mine.text and "010-****-3333" in mine.text
    assert "2026-10-09 15:00" in mine.text and "확정" in mine.text and "별채 · 2명" in mine.text
    assert "아직 주문이 없어요" in mine.text and "회원 탈퇴" in mine.text
    with get_sessionmaker()() as db:
        row = db.scalar(select(CustomerRow).where(CustomerRow.site_key == key))
        assert row.member_since is not None and row.phone_verified_at is not None
    # 사장님 '손님' 탭
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=rid, member_id=h["X-Member-Id"]))
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    lst = client.get(f"/api/owner/shops/{key}/members").json()
    assert lst["on"] is True and [(m["name"], m["phone"], m["bookings"]) for m in lst["members"]] == [("김손님", "010-****-3333", 1)]
    # 이 기기에서 나가기 → 다시 가입 폼
    r = client.post(f"/api/members/{key}/logout")
    assert "나갔어요" in r.text and f"mb_{key}=" in r.headers["set-cookie"]
    client.cookies.delete(f"mb_{key}")
    assert "인증번호 받기" in client.get(f"/api/members/{key}").text
    # 다시 들어와 탈퇴 → 회원 표시·이름 지움, 예약 기록은 남음
    _join(client, key, _sms)
    assert "회원 탈퇴했어요" in client.post(f"/api/members/{key}/leave").text
    with get_sessionmaker()() as db:
        row = db.scalar(select(CustomerRow).where(CustomerRow.site_key == key))
        assert row.member_since is None and row.name is None
        assert db.scalar(select(BookingRow.id).where(BookingRow.site_key == key)) is not None
    assert client.get(f"/api/owner/shops/{key}/members").json()["members"] == []


def test_wrong_cookie_or_other_shop_cookie_is_not_member(client, _sms):
    rid, h, key = _pension(client)
    client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": True}, headers=h)
    rid2, h2, key2 = _pension(client)
    client.put(f"/api/rooms/{rid2}/features", json={"key": "members", "on": True}, headers=h2)
    cookie = _join(client, key, _sms)
    client.cookies.set(f"mb_{key2}", cookie)  # 다른 가게 쿠키로는 못 봄(서명에 가게 키)
    assert "인증번호 받기" in client.get(f"/api/members/{key2}").text
    client.cookies.set(f"mb_{key}", cookie[:-2] + "00")
    assert "인증번호 받기" in client.get(f"/api/members/{key}").text


def test_platform_sms_daily_cap(client, monkeypatch):
    rid, h, key = _pension(client)
    client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": True}, headers=h)
    monkeypatch.setattr(members, "DAILY_SMS_MAX", 2)
    now = datetime.datetime.now(datetime.timezone.utc)
    with get_sessionmaker()() as db, db.begin():
        for i in range(2):
            db.add(CustomerRow(site_key=key, phone=f"0101111000{i}", phone_verified_at=now))
    r = client.post(f"/api/members/{key}", data={"phone": PHONE, "agree": "1"})
    assert r.status_code == 429 and "오늘은 회원 확인 문자를" in r.text
    # 가게 문자 키가 있으면 가게 비용이라 상한 없음
    from app.services import shop_settings
    monkeypatch.setattr(shop_settings, "sms_credentials", lambda site_key: ("k", "s", "01000000000"))
    assert members.sms_quota_ok(key) is True


def test_render_link_replaces_stamp_link_and_only_live_pages():
    spec = {"version": 3, "tokens": {"palette": "forest", "font_pair": "serif-warm", "density": "comfortable",
                                     "radius": "soft", "image_style": "card"},
            "members": True,
            "navbar": {"title": "t", "top": "#x", "links": [{"label": "스탬프", "href": "/api/orders/k1/my"}]},
            "sections": [{"id": "inquiry", "type": "contact", "variant": "form", "content": {}}]}
    page = site_render.render_site(spec, site_key="k1", title="t", kind="cafe", public=True)
    assert 'href="/api/members/k1"' in page and "/api/orders/k1/my" not in page
    design = site_render.render_site(spec, site_key="k1", title="t", kind="cafe")  # 시안 미리보기엔 안 붙임
    assert "/api/members/" not in design


def test_without_signing_key_shows_once_instead_of_bouncing(client, _sms, monkeypatch):
    """서명 키(TOKEN_ENC_KEY)가 없어 기기 기억을 못 하면 인증 뒤 가입 폼으로 돌려보내지 않고 바로 보여 준다."""
    rid, h, key = _pension(client)
    client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": True}, headers=h)
    monkeypatch.setattr(settings, "token_enc_key", None)
    monkeypatch.setattr(settings, "kakao_client_secret", None)
    r = client.post(f"/api/members/{key}", data={"phone": PHONE, "agree": "1"}, follow_redirects=False)
    code = re.search(r"인증번호 (\d{6})", _sms[-1]).group(1)
    r = client.post(r.headers["location"], data={"code": code}, follow_redirects=False)
    assert r.status_code == 200 and "내 정보" in r.text and "다시 인증해 주세요" in r.text


def test_no_sms_keys_means_no_signup(client, monkeypatch):
    """문자 키가 하나도 없으면(개발 모드도 아님) 인증번호가 실제로 안 가므로 가입을 열지 않고, 사장님 탭에 알린다."""
    rid, h, key = _pension(client)
    client.put(f"/api/rooms/{rid}/features", json={"key": "members", "on": True}, headers=h)
    monkeypatch.setattr(settings, "sms_dev_mode", False)
    r = client.get(f"/api/members/{key}")
    assert r.status_code == 503 and "지금은 회원 가입을 받을 수 없어요" in r.text
    assert client.post(f"/api/members/{key}", data={"phone": PHONE, "agree": "1"}).status_code == 503
    uid = f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=rid, member_id=h["X-Member-Id"]))
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    assert client.get(f"/api/owner/shops/{key}/members").json()["sms_ready"] is False
