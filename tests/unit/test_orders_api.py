"""주문 손님 경로 (PAY_WAVE3_CONTRACT §6 테스트 7·8·9). 실제 포트원·문자는 부르지 않는다."""
import base64
import datetime
import hashlib
import hmac
import json
import re
import time

import httpx
from sqlalchemy import delete, select, update

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.db.models import PaymentRow, PhoneVerificationRow, SessionRow, ShopSettingsRow
from app.db.session import get_sessionmaker
from app.services import design, keystore, orders, payments
from app.services import publish_check, sms as sms_svc

MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}


import pytest


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


@pytest.fixture(autouse=True)
def _clean_verify(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-device-key")
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow))  # 하루 5번 제한이 테스트끼리 섞이지 않게


@pytest.fixture
def _sms(monkeypatch):
    sent = []
    monkeypatch.setattr(sms_svc, "send", lambda to, text, site_key=None: sent.append((to, text)) or True)
    return sent


@pytest.fixture
def _ready(monkeypatch):
    """결제 준비됨 (가짜 키, 실제 포트원은 안 부른다)."""
    monkeypatch.setattr(settings, "portone_store_id", "store-test")
    monkeypatch.setattr(settings, "portone_channel_key", "channel-test")
    monkeypatch.setattr(settings, "portone_api_secret", "secret-test")
    keystore.invalidate()


def _site(client, order_on=True):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "business_type": {"value": "카페", "status": "filled"},
                     "contact_method": {"value": "픽업 주문", "status": "filled"},
                     "phone": {"value": "010-1234-5678", "status": "filled"},
                     "hours": {"value": "매일 09~22시", "status": "filled"},
                     "location": {"value": "경기 수원시 행궁동 근처", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "industry": "cafe", "published": "v1"}
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=order_on))
    return key


def _card(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(SessionRow.prd).where(SessionRow.requirement_id == key))


def _form(phone, **over):
    form = {"item_0": "아메리카노", "qty_0": "2", "name": "김손님", "phone": phone, "website": ""}
    form.update(over)
    return form


def _code_of(text):
    return re.search(r"인증번호 (\d{6})", text).group(1)


def _cookie_value(set_cookie, name):
    first = (set_cookie or "").split(";")[0]
    k, _, v = first.partition("=")
    assert k.strip() == name
    return v.strip()


# §6 테스트 7: 주문 폼 → 인증 → /pay + 기기 쿠키
def test_order_post_goes_to_verify_and_creates_pay(client, _sms, _ready):
    key = _site(client)
    phone = "010-2000-0001"
    r = client.post(f"/api/orders/{key}", data=_form(phone), follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith(f"/api/orders/{key}/verify/")
    page = client.get(loc)
    assert page.status_code == 200
    assert f"/api/orders/{key}/verify/" in page.text and "/api/bookings/" not in page.text
    bad = client.post(loc, data={"code": "000000"})
    assert bad.status_code == 400
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    assert done.status_code == 303
    assert done.headers["location"].startswith("/pay/ord_")
    jar = (done.headers.get("set-cookie") or "").lower()
    assert f"pv_{key}=" in jar and "httponly" in jar and "secure" in jar
    assert "samesite=lax" in jar and f"path=/api/orders/{key}" in jar
    cookie = _cookie_value(done.headers.get("set-cookie"), f"pv_{key}")
    _sms.clear()
    again = client.post(f"/api/orders/{key}", data=_form(phone),
                        cookies={f"pv_{key}": cookie}, follow_redirects=False)
    assert again.status_code == 303 and again.headers["location"].startswith("/pay/ord_")
    assert not _sms  # 기기 기억이면 인증 건너뜀


def test_order_honeypot_returns_to_site_quietly(client, _sms, _ready):
    key = _site(client)
    r = client.post(f"/api/orders/{key}", data=_form("010-2000-0002", website="http://spam"),
                    follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/site/{key}/"
    assert not _sms


def test_order_bad_qty_400_before_sms(client, _sms, _ready):
    key = _site(client)
    r = client.post(f"/api/orders/{key}", data=_form("010-2000-0003", qty_0="99"))
    assert r.status_code == 400 and not _sms


def test_order_rate_limited(client, _sms, _ready):
    key = _site(client)
    for i in range(5):
        r = client.post(f"/api/orders/{key}", data=_form(f"010-2001-{i:04d}"), follow_redirects=False)
        assert r.status_code == 303
    over = client.post(f"/api/orders/{key}", data=_form("010-2001-9999"), follow_redirects=False)
    assert over.status_code == 429


def test_order_verify_resend(client, _sms, _ready):
    key = _site(client)
    r = client.post(f"/api/orders/{key}", data=_form("010-2000-0004"), follow_redirects=False)
    loc = r.headers["location"]
    old_token = loc.rsplit("/", 1)[-1]
    with get_sessionmaker()() as db, db.begin():  # 다시 보내기 1분 제한을 지난 것으로
        db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == old_token)
                   .values(created_at=datetime.datetime.now(datetime.timezone.utc)
                           - datetime.timedelta(minutes=2)))
    _sms.clear()
    again = client.post(f"{loc}/resend", follow_redirects=False)
    assert again.status_code == 303
    new_loc = again.headers["location"]
    assert new_loc.startswith(f"/api/orders/{key}/verify/") and new_loc != loc
    old = client.post(loc, data={"code": "000000"})
    assert old.status_code == 400 and "인증 요청을 찾을 수 없어요" in old.text
    done = client.post(new_loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"].startswith("/pay/ord_")


# §6 테스트 8: /pay 화면·헤더·전화번호 없음·만료·완료 이동
def _order(key, phone="010-2000-0011"):
    return orders.create(key, [("아메리카노", 2)], "김손님", phone)


def test_pay_page_banner_csp_no_phone(client, _ready):
    key = _site(client)
    pay_id = _order(key)
    r = client.get(f"/pay/{pay_id}")
    assert r.status_code == 200
    assert "테스트 결제예요. 실제로 돈이 나가지 않아요" in r.text
    assert "cdn.portone.io/v2/browser-sdk.js" in r.text and "PortOne.requestPayment" in r.text
    assert "store-test" in r.text and pay_id in r.text
    assert "9,000원 결제하기" in r.text
    assert "01020000011" not in r.text and "010-2000-0011" not in r.text  # 전화번호 없음
    assert "https://cdn.portone.io" in r.headers.get("content-security-policy", "")
    assert r.headers.get("referrer-policy") == "no-referrer"
    assert r.headers.get("cache-control") == "no-store"


def test_pay_page_shop_name_cannot_break_out_of_script(client, _ready):
    """가게 이름은 사장님이 정한다. 앱 주소 결제 페이지의 인라인 스크립트 밖으로 못 나가야 한다."""
    key = _site(client)
    prd = _card(key)
    prd["slots"]["shop_name"]["value"] = "가게</script><script>alert(1)</script>"
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
    r = client.get(f"/pay/{_order(key)}")
    assert r.status_code == 200
    assert "<script>alert(1)" not in r.text
    assert r.text.count("</script>") == 2  # SDK 한 개 + 우리 스크립트 한 개


def test_unknown_menu_rejected_before_sms(client, _sms, _ready):
    """메뉴에 없는 항목·주문 꺼짐은 인증 문자를 보내기 전에 거절 (문자 비용·헛걸음)."""
    key = _site(client)
    r = client.post(f"/api/orders/{key}", data=_form("010-2000-0004", item_0="없는메뉴"))
    assert r.status_code == 400 and not _sms
    off = _site(client, order_on=False)
    r = client.post(f"/api/orders/{off}", data=_form("010-2000-0005"))
    assert r.status_code == 400 and not _sms


def test_pay_page_paid_goes_to_done(client, _ready):
    key = _site(client)
    pay_id = _order(key)
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(PaymentRow).where(PaymentRow.provider_payment_id == pay_id)
                   .values(status="paid"))
    r = client.get(f"/pay/{pay_id}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith(f"/pay/{pay_id}/done")


def test_pay_page_expired(client, _ready):
    key = _site(client)
    pay_id = _order(key)
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(PaymentRow).where(PaymentRow.provider_payment_id == pay_id)
                   .values(created_at=datetime.datetime.now(datetime.timezone.utc)
                           - datetime.timedelta(minutes=16)))
    r = client.get(f"/pay/{pay_id}")
    assert r.status_code == 200 and "주문 시간이 지났어요. 가게 사이트에서 다시 주문해 주세요" in r.text


def test_pay_page_not_ready(client, monkeypatch):
    key = _site(client)
    monkeypatch.setattr(settings, "portone_store_id", "")
    monkeypatch.setattr(settings, "portone_channel_key", "")
    monkeypatch.setattr(settings, "portone_api_secret", "")
    keystore.invalidate()
    pay_id = _order(key)
    r = client.get(f"/pay/{pay_id}")
    assert r.status_code == 200 and "결제 준비 중이에요. 전화로 주문해 주세요" in r.text


def test_pay_page_unknown_404(client, _ready):
    assert client.get("/pay/ord_nope").status_code == 404


def _transport(status, total):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": status, "amount": {"total": total}, "currency": "KRW"})
    return httpx.MockTransport(handler)


def test_pay_done_statuses(client, monkeypatch, _ready):
    key = _site(client)
    assert client.get("/pay/ord_nope/done").status_code == 404
    pay_id = _order(key, "010-2000-0021")
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    monkeypatch.setattr(payments, "_TRANSPORT", _transport("READY", total))
    assert "결제를 확인하고 있어요" in client.get(f"/pay/{pay_id}/done").text
    monkeypatch.setattr(payments, "_TRANSPORT", _transport("PAID", total))
    assert "주문이 들어갔어요" in client.get(f"/pay/{pay_id}/done").text
    pay_id2 = _order(key, "010-2000-0022")
    monkeypatch.setattr(payments, "_TRANSPORT", _transport("PAID", 1))  # 금액 다름
    assert "결제가 확인되지 않았어요" in client.get(f"/pay/{pay_id2}/done").text


def _webhook_secret(monkeypatch):
    raw = b"test-webhook-secret-0123456789ab"
    monkeypatch.setattr(settings, "portone_webhook_secret", "whsec_" + base64.b64encode(raw).decode())
    keystore.invalidate()
    return raw


def _sign(raw: bytes, wid: str, ts: str, body: bytes) -> dict:
    msg = f"{wid}.{ts}.{body.decode()}".encode()
    digest = base64.b64encode(hmac.new(raw, msg, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}


def test_webhook_bad_signature_400(client, monkeypatch, _ready):
    raw = _webhook_secret(monkeypatch)
    body = json.dumps({"data": {"paymentId": "ord_x"}}).encode()
    ts = str(int(time.time()))
    bad = _sign(raw, "msg_1", ts, body)
    bad["webhook-signature"] = "v1,AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
    r = client.post("/api/payments/webhook", content=body, headers=bad)
    assert r.status_code == 400


def test_webhook_good_paid_once_and_unknown_200(client, monkeypatch, _ready):
    from app.services import notify
    raw = _webhook_secret(monkeypatch)
    key = _site(client)
    pay_id = _order(key, "010-2000-0031")
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pay_id))
    monkeypatch.setattr(payments, "_TRANSPORT", _transport("PAID", total))
    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append(text))
    body = json.dumps({"data": {"paymentId": pay_id}}).encode()
    headers = _sign(raw, "msg_2", str(int(time.time())), body)
    r = client.post("/api/payments/webhook", content=body, headers=headers)
    assert r.status_code == 200 and r.json() == {"ok": True}
    r2 = client.post("/api/payments/webhook", content=body, headers=headers)
    assert r2.status_code == 200 and r2.json() == {"ok": True}  # 두 번 와도 200
    assert len(calls) == 1
    unknown = json.dumps({"data": {"paymentId": "ord_nope"}}).encode()
    r3 = client.post("/api/payments/webhook", content=unknown,
                     headers=_sign(raw, "msg_3", str(int(time.time())), unknown))
    assert r3.status_code == 200 and r3.json() == {"ok": True}  # 모르는 pay_id도 200


# §6 테스트 9: 공개본 주문 폼
def test_publish_with_order_form_when_on_and_ready(client, _ready):
    key = _site(client, order_on=True)
    design.publish_choice(key, _card(key), "v1")
    page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert 'action="/api/orders/' in page and 'name="qty_0"' in page
    assert 'name="item_0"' in page and 'name="phone"' in page
    publish_check.assert_publishable(page)  # 공개 전 검사 통과


def test_publish_keeps_soon_when_off(client, _ready):
    key = _site(client, order_on=False)
    design.publish_choice(key, _card(key), "v1")
    page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert 'href="#order-soon"' in page and 'name="qty_0"' not in page
