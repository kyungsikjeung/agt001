"""사장님 스탬프·쿠폰 화면 (STAMP_WAVE4_CONTRACT §5 테스트 11)."""
import secrets

from sqlalchemy import select, update

from app import store
from app.db.models import CouponRow, SessionRow, ShopSettingsRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import stamps
from app.services.customers import touch

ORIGIN = {"Origin": "http://testserver"}
MENU = ["아메리카노", "카페라떼"]
PRICES = {"아메리카노": "4,500원", "카페라떼": "5,000원"}
PHONE = "010-1234-5678"


def _site(client):
    """주문 받는 가게 + 사장님 계정. (room_key, uid)를 돌려준다."""
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    uid = f"u-{secrets.token_hex(4)}"
    prd = {"slots": {"shop_name": {"value": "우리 가게", "status": "filled"},
                     "offerings": {"value": list(MENU), "status": "filled"}},
           "price_pairs": dict(PRICES), "published": "v1"}
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(SessionRow).where(SessionRow.requirement_id == key).values(prd=prd))
        db.add(ShopSettingsRow(site_key=key, phone_verify=False, order_on=True))
        db.add(UserRow(id=uid, nickname="사장님"))
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=room_id, member_id="owner"))
    stamps.set_rule(uid, key, active=True, goal=10, per="order")
    return key, uid


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


def _coupon(key, phone=PHONE):
    """쿠폰 한 장을 직접 만들고 번호를 돌려준다."""
    with get_sessionmaker()() as db, db.begin():
        cid = touch(db, key, phone, "손님")
        stamps.issue(db, key, cid, source="owner")
    with get_sessionmaker()() as db:
        return db.scalar(select(CouponRow.code).where(
            CouponRow.site_key == key).order_by(CouponRow.id.desc()))


def test_rule_get_put_and_range_400(client):
    key, uid = _site(client)
    _login(client, uid)
    got = client.get(f"/api/owner/shops/{key}/stamps/rule").json()["rule"]
    assert got["active"] is True and got["goal"] == 10
    # 범위 밖은 400 (§5 테스트 11)
    r = client.put(f"/api/owner/shops/{key}/stamps/rule", json={"goal": 1}, headers=ORIGIN)
    assert r.status_code == 400
    r = client.put(f"/api/owner/shops/{key}/stamps/rule", json={"per": "week"}, headers=ORIGIN)
    assert r.status_code == 400
    r = client.put(f"/api/owner/shops/{key}/stamps/rule",
                   json={"goal": 5, "reward_title": "케이크 1개"}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["rule"]["goal"] == 5


def test_cross_shop_redeem_404(client):
    key_a, uid_a = _site(client)
    key_b, _uid_b = _site(client)
    code = _coupon(key_b)
    _login(client, uid_a)  # 가게 A 사장님이 가게 B 쿠폰을 씀
    r = client.post(f"/api/owner/shops/{key_a}/coupons/redeem", json={"code": code}, headers=ORIGIN)
    assert r.status_code == 404
    assert r.json()["detail"] == "없는 쿠폰 번호예요"


def test_redeem_then_second_400(client):
    key, uid = _site(client)
    code = _coupon(key)
    _login(client, uid)
    r = client.post(f"/api/owner/shops/{key}/coupons/redeem", json={"code": code}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json()["phone_last4"] == "5678"
    r = client.post(f"/api/owner/shops/{key}/coupons/redeem", json={"code": code}, headers=ORIGIN)
    assert r.status_code == 400


def test_redeem_limiter_429(client):
    key, uid = _site(client)
    _login(client, uid)
    last = None
    for i in range(11):
        last = client.post(f"/api/owner/shops/{key}/coupons/redeem",
                           json={"code": f"77770000{i:04d}"}, headers=ORIGIN)
    assert last.status_code == 429
    assert last.json()["detail"] == "잠시 뒤 다시 입력해 주세요"


def test_manual_count_range(client):
    key, uid = _site(client)
    _login(client, uid)
    r = client.post(f"/api/owner/shops/{key}/stamps/manual",
                    json={"phone": PHONE, "count": 11}, headers=ORIGIN)
    assert r.status_code == 400  # §5 테스트 11: 11개 거절
    r = client.post(f"/api/owner/shops/{key}/stamps/manual",
                    json={"phone": PHONE, "count": 2}, headers=ORIGIN)
    assert r.status_code == 200, r.text
    assert r.json() == {"balance": 2, "issued": 0}


def test_issue_needs_rule(client):
    key, uid = _site(client)
    _login(client, uid)
    with get_sessionmaker()() as db, db.begin():
        from app.db.models import StampRuleRow
        db.delete(db.get(StampRuleRow, key))
    r = client.post(f"/api/owner/shops/{key}/coupons/issue",
                    json={"phone": PHONE}, headers=ORIGIN)
    assert r.status_code == 400
    assert r.json()["detail"] == "스탬프 규칙을 먼저 정해 주세요"


def test_coupon_list_hides_full_code(client):
    key, uid = _site(client)
    code = _coupon(key)
    _login(client, uid)
    r = client.get(f"/api/owner/shops/{key}/coupons")
    assert r.status_code == 200
    assert code not in r.text  # §5 테스트 11: 번호 전체 없음
    one = r.json()["coupons"][0]
    assert one["code_last4"] == code[-4:] and one["phone_last4"] == "5678"


def test_rule_activate_republishes(client, monkeypatch):
    from app.services import design

    key, uid = _site(client)
    _login(client, uid)
    calls = []
    monkeypatch.setattr(design, "publish_choice",
                        lambda site, card, choice: calls.append((site, choice)))
    r = client.put(f"/api/owner/shops/{key}/stamps/rule", json={"active": False}, headers=ORIGIN)
    assert r.status_code == 200
    assert calls == [(key, "v1")]  # 켜기·끄기가 바뀌고 공개본이 있으면 다시 공개
