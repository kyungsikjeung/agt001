"""주문→결제→스탬프→쿠폰→환불→웹훅 끝까지 한 번에 (WAVE5_CONTRACT §2.4). 실제 포트원·문자는 부르지 않는다."""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time

import httpx
import pytest
from sqlalchemy import delete, select, update

from app import store
from app.api import inquiries as inquiries_api
from app.config import settings
from app.db.models import (
    CouponRow,
    OrderRow,
    PaymentRow,
    PhoneVerificationRow,
    SessionRow,
    ShopSettingsRow,
    UserRoomRow,
    UserRow,
)
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import design, keystore, payments, stamps
from app.services import sms as sms_svc

MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}
ORIGIN = {"Origin": "http://testserver"}
PHONE = "010-2000-0001"


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


@pytest.fixture(autouse=True)
def _clean_verify(monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-device-key")
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow))


@pytest.fixture
def _sms(monkeypatch):
    sent = []
    monkeypatch.setattr(sms_svc, "send", lambda to, text, site_key=None: sent.append((to, text)) or True)
    return sent


@pytest.fixture
def _ready(monkeypatch):
    monkeypatch.setattr(settings, "portone_store_id", "store-test")
    monkeypatch.setattr(settings, "portone_channel_key", "channel-test")
    monkeypatch.setattr(settings, "portone_api_secret", "secret-test")
    keystore.invalidate()


def _site(client):
    """주문 받는 카페 + 사장님 계정 + 스탬프 규칙(목표 2, 주문당 1, 무료 음료)."""
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    uid = f"u-{secrets.token_hex(4)}"
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
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=True))
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    stamps.set_rule("tester", key, active=True, goal=2, per="order")
    return key, uid


def _card(key):
    with get_sessionmaker()() as db:
        return db.scalar(select(SessionRow.prd).where(SessionRow.requirement_id == key))


def _form():
    return {"item_0": "아메리카노", "qty_0": "1", "name": "김손님", "phone": PHONE, "website": ""}


def _code_of(text):
    return re.search(r"인증번호 (\d{6})", text).group(1)


def _cookie_value(set_cookie, name):
    first = (set_cookie or "").split(";")[0]
    k, _, v = first.partition("=")
    assert k.strip() == name
    return v.strip()


def _customer_id(key):
    from app.db.models import CustomerRow
    with get_sessionmaker()() as db:
        return db.scalar(select(CustomerRow.id).where(
            CustomerRow.site_key == key, CustomerRow.phone == PHONE.replace("-", "")))


def _balance(key, cid):
    with get_sessionmaker()() as db:
        return stamps.balance(db, key, cid)


def _pay_status(pay_id):
    with get_sessionmaker()() as db:
        return db.scalar(select(PaymentRow.status).where(PaymentRow.provider_payment_id == pay_id))


def _handler(request: httpx.Request) -> httpx.Response:
    """포트원 가짜: 취소는 성공, 조회는 DB 금액 그대로 PAID."""
    if request.url.path.endswith("/cancel"):
        return httpx.Response(200, json={"id": "cancel_1"})
    pid = request.url.path.rsplit("/", 1)[-1]
    with get_sessionmaker()() as db:
        total = db.scalar(select(PaymentRow.amount).where(PaymentRow.provider_payment_id == pid))
    return httpx.Response(200, json={"status": "PAID", "amount": {"total": total}, "currency": "KRW"})


def _webhook_secret(monkeypatch):
    raw = b"test-webhook-secret-0123456789ab"
    monkeypatch.setattr(settings, "portone_webhook_secret", "whsec_" + base64.b64encode(raw).decode())
    keystore.invalidate()
    return raw


def _sign(raw: bytes, wid: str, ts: str, body: bytes) -> dict:
    msg = f"{wid}.{ts}.{body.decode()}".encode()
    digest = base64.b64encode(hmac.new(raw, msg, hashlib.sha256).digest()).decode()
    return {"webhook-id": wid, "webhook-timestamp": ts, "webhook-signature": f"v1,{digest}"}


def test_commerce_end_to_end(client, monkeypatch, _sms, _ready):
    from app.services import notify
    key, uid = _site(client)
    raw = _webhook_secret(monkeypatch)
    monkeypatch.setattr(payments, "_TRANSPORT", httpx.MockTransport(_handler))
    calls = []
    monkeypatch.setattr(notify, "owner_kakao", lambda room_id, text: calls.append(text))

    # 1. 공개본에 주문 폼·스탬프 링크
    design.publish_choice(key, _card(key), "v1")
    page = (settings.generated_dir / key / "published" / "index.html").read_text(encoding="utf-8")
    assert 'action="/api/orders/' in page and 'name="qty_0"' in page
    assert "스탬프" in page and f"/api/orders/{key}/my" in page

    # 2. 주문 폼 → 인증 → /pay (기기 쿠키 경로 확인)
    r = client.post(f"/api/orders/{key}", data=_form(), follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith(f"/api/orders/{key}/verify/")
    done = client.post(loc, data={"code": _code_of(_sms[-1][1])}, follow_redirects=False)
    assert done.status_code == 303 and done.headers["location"].startswith("/pay/ord_")
    pay1 = done.headers["location"].rsplit("/", 1)[-1]
    jar = (done.headers.get("set-cookie") or "").lower()
    assert f"pv_{key}=" in jar and f"path=/api/orders/{key}" in jar
    cookie = _cookie_value(done.headers.get("set-cookie"), f"pv_{key}")

    def _order_again():
        rr = client.post(f"/api/orders/{key}", data=_form(),
                         cookies={f"pv_{key}": cookie}, follow_redirects=False)
        assert rr.status_code == 303 and rr.headers["location"].startswith("/pay/ord_")
        return rr.headers["location"].rsplit("/", 1)[-1]

    # 3. 첫 결제 확정 → paid, 도장 1
    assert "주문이 들어갔어요" in client.get(f"/pay/{pay1}/done").text
    assert _pay_status(pay1) == "paid"
    cid = _customer_id(key)
    assert _balance(key, cid) == 1

    # 4. 두 번째 주문 결제 → 목표 달성, 도장 0, 쿠폰 1장 issued
    pay2 = _order_again()
    assert not _sms[1:]  # 기기 기억이면 인증 문자 없음
    assert "주문이 들어갔어요" in client.get(f"/pay/{pay2}/done").text
    assert _balance(key, cid) == 0
    with get_sessionmaker()() as db:
        rows = db.scalars(select(CouponRow).where(
            CouponRow.site_key == key, CouponRow.customer_id == cid)).all()
        assert len(rows) == 1 and rows[0].status == "issued"
        coid, code = rows[0].id, rows[0].code

    # 5. 세 번째 주문에서 쿠폰 잡기 → 가장 비싼 한 개 할인, 합계 0 → /free 완료
    pay3 = _order_again()
    hold = client.post(f"/pay/{pay3}/coupon", data={"coupon_id": str(coid)},
                       headers=ORIGIN, follow_redirects=False)
    assert hold.status_code == 303
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pay3))
        order = db.get(OrderRow, pay.order_id)
        assert (pay.amount, order.discount, order.total) == (0, 4500, 0)
    free = client.post(f"/pay/{pay3}/free", headers=ORIGIN, follow_redirects=False)
    assert free.status_code == 303 and free.headers["location"].endswith(f"/pay/{pay3}/done")
    with get_sessionmaker()() as db:
        assert db.get(CouponRow, coid).status == "used"
    assert _balance(key, cid) == 1

    # 6. 사장님 매장 사용에 같은 쿠폰 번호 → 400 이미 쓴 쿠폰
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))
    r = client.post(f"/api/owner/shops/{key}/coupons/redeem", json={"code": code}, headers=ORIGIN)
    assert r.status_code == 400 and "이미 쓴 쿠폰" in r.json()["detail"]

    # 7. 두 번째 주문 전액 환불 → 도장 회수(화면엔 0), 결제 canceled
    with get_sessionmaker()() as db:
        oid2 = db.scalar(select(PaymentRow.order_id).where(PaymentRow.provider_payment_id == pay2))
    r = client.post(f"/api/owner/shops/{key}/orders/{oid2}/refund",
                    json={"amount": None, "reason": "변심"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["remaining"] == 0 and r.json()["status"] == "canceled"
    assert _pay_status(pay2) == "canceled"
    assert _balance(key, cid) == 0

    # 8. 웹훅 중복 → 변화 없음, 알림 수 그대로
    n_calls, bal = len(calls), _balance(key, cid)
    body = json.dumps({"data": {"paymentId": pay1}}).encode()
    r = client.post("/api/payments/webhook", content=body,
                    headers=_sign(raw, "msg_again", str(int(time.time())), body))
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(calls) == n_calls and _balance(key, cid) == bal
    assert _pay_status(pay1) == "paid"
