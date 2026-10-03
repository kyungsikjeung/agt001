"""휴대폰 알림(웹 푸시, OWNER_NOTIFY_PLAN N1~N7): 암호화·서명 표준, 구독 API, 보내기, 알림 허브."""
import base64
import json
import os
import secrets
import struct

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select

from app import store
from app.api import push as push_api
from app.config import settings
from app.db.models import PushSubscriptionRow, ShopRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.services import accounts, keystore, notify, push
from app.services import auth as auth_svc

ORIGIN = {"Origin": "http://testserver"}
FCM = "https://fcm.googleapis.com/fcm/send/"


def _b64d(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


class Device:
    """브라우저 쪽 흉내: 구독 열쇠를 갖고, 받은 본문을 RFC 8291대로 푼다."""

    def __init__(self, endpoint=None):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.auth = os.urandom(16)
        self.pub = self.key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.endpoint = endpoint or FCM + secrets.token_hex(8)

    def sub(self, label="안드로이드 크롬"):
        return {"endpoint": self.endpoint, "keys": {"p256dh": _b64e(self.pub), "auth": _b64e(self.auth)}, "label": label}

    def decrypt(self, body: bytes) -> bytes:
        salt, rs, idlen = body[:16], struct.unpack("!I", body[16:20])[0], body[20]
        as_pub, ct = body[21:21 + idlen], body[21 + idlen:]
        assert rs == 4096 and idlen == 65
        shared = self.key.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub))
        hk = lambda salt_, ikm, info, n: HKDF(hashes.SHA256(), n, salt_, info).derive(ikm)  # noqa: E731
        ikm = hk(self.auth, shared, b"WebPush: info\x00" + self.pub + as_pub, 32)
        out = AESGCM(hk(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)).decrypt(
            hk(salt, ikm, b"Content-Encoding: nonce\x00", 12), ct, None)
        assert out.endswith(b"\x02")
        return out[:-1]


@pytest.fixture
def vapid(monkeypatch):
    key = push.generate_private_key()
    monkeypatch.setattr(settings, "vapid_private_key", key)
    monkeypatch.setattr(settings, "vapid_subject", "mailto:ops@example.com")
    push._key_cache.update(value=None, key=None)
    push_api._last_test.clear()
    return key


@pytest.fixture
def wire(monkeypatch):
    """푸시 회사 흉내: 받은 요청을 모으고, 주소별로 정한 응답 코드를 준다."""
    got, codes = [], {}

    def handler(request: httpx.Request):
        got.append(request)
        return httpx.Response(codes.get(str(request.url), 201))

    monkeypatch.setattr(push, "_TRANSPORT", httpx.MockTransport(handler))
    return got, codes


def _user(uid=None):
    uid = uid or f"u-{secrets.token_hex(4)}"
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id=uid, nickname="사장님"))
    return uid


def _login(client, uid):
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(uid))


def _subs(uid):
    with get_sessionmaker()() as db:
        return db.scalars(select(PushSubscriptionRow).where(PushSubscriptionRow.user_id == uid)
                          .order_by(PushSubscriptionRow.id)).all()


# ── 표준 ─────────────────────────────────────────────────────────────────

def test_encrypt_matches_rfc8291_vector():
    """RFC 8291 부록 A: 고정 salt·서버 키로 바이트까지 같아야 한다."""
    as_key = ec.derive_private_key(int.from_bytes(_b64d("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"), ec.SECP256R1())
    out = push.encrypt(b"When I grow up, I want to be a watermelon",
                       "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
                       "BTBZMqHH6r4Tts7J_aSIgg", salt=_b64d("DGv6ra1nlYgDCS1FRnbzlw"), server_key=as_key)
    assert _b64e(out) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95b"
        "Qpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN")


def test_encrypt_roundtrip_fresh_keys_each_time():
    d = Device()
    a = push.encrypt("새 문의가 왔어요".encode(), _b64e(d.pub), _b64e(d.auth))
    b = push.encrypt("새 문의가 왔어요".encode(), _b64e(d.pub), _b64e(d.auth))
    assert a != b  # salt·서버 임시 키가 매번 다르다
    assert d.decrypt(a).decode() == d.decrypt(b).decode() == "새 문의가 왔어요"


def test_vapid_header_is_valid_es256_jwt(vapid):
    key = push._private_key(vapid)
    h = push.vapid_header(FCM + "abc", key, now=1_700_000_000)
    token, k = h.removeprefix("vapid t=").split(", k=")
    head, body, sig = token.split(".")
    raw = _b64d(sig)
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), _b64d(k))
    pub.verify(encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big")),
               f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256()))
    claims = json.loads(_b64d(body))
    assert json.loads(_b64d(head)) == {"typ": "JWT", "alg": "ES256"}
    assert claims == {"aud": "https://fcm.googleapis.com", "exp": 1_700_000_000 + 12 * 3600, "sub": "mailto:ops@example.com"}
    assert k == push.public_key(vapid)


def test_private_key_format():
    assert len(_b64d(push.public_key(push.generate_private_key()))) == 65
    for bad in ("", "short", _b64e(b"\x00" * 31), "!!!!"):
        with pytest.raises(ValueError):
            push.public_key(bad)


@pytest.mark.parametrize("url", [
    FCM + "x", "https://updates.push.services.mozilla.com/wpush/v2/x", "https://web.push.apple.com/QH",
    "https://wns2-par02p.notify.windows.com/w/?token=x", "https://android.googleapis.com/gcm/send/x"])
def test_endpoint_allowed(url):
    assert push.check_endpoint(url) == url


@pytest.mark.parametrize("url", [
    "", "http://fcm.googleapis.com/fcm/send/x", "https://evil.example/x", "https://fcm.googleapis.com.evil.example/x",
    "https://user:pw@fcm.googleapis.com/x", "https://fcm.googleapis.com:8443/x", "https://evilfcm.googleapis.com.example/x",
    "https://127.0.0.1/x", "https://" + "a" * 1100])
def test_endpoint_rejected(url):
    with pytest.raises(push.PushError):
        push.check_endpoint(url)


def test_keys_checked():
    d = Device()
    assert push.check_keys(_b64e(d.pub), _b64e(d.auth)) == (_b64e(d.pub), _b64e(d.auth))
    for p, a in ((_b64e(d.pub[:64]), _b64e(d.auth)), (_b64e(b"\x04" + b"\x01" * 64), _b64e(d.auth)),
                 (_b64e(d.pub), _b64e(d.auth[:8])), ("", "")):
        with pytest.raises(push.PushError):
            push.check_keys(p, a)


def test_lock_screen_line_hides_customer_details():
    assert push.lock_screen_line("사이트로 새 문의가 왔어요.\n이름: 홍길동\n연락처: 010-1111-2222") == "사이트로 새 문의가 왔어요."
    assert push.lock_screen_line("예약을 바꾸셨어요: 10/5 15:00 홍길동님 (컷)") == "예약을 바꾸셨어요"
    assert push.lock_screen_line("새 주문: 아메리카노 · 4,500원") == "새 주문"
    assert push.lock_screen_line("") == "새 알림이 있어요."


def test_click_url_stays_on_our_site(monkeypatch):
    monkeypatch.setattr(settings, "public_base_url", "https://shop.example")
    assert push.click_url("r1", "새 채팅이 왔어요.\nhttps://shop.example/owner?tab=chats") == "/owner?tab=chats"
    assert push.click_url("r1", "새 문의\nhttps://evil.example/owner") == "/room.html?room=r1"
    assert push.click_url("r1", "사이트로 새 문의가 왔어요.") == "/room.html?room=r1"


# ── API ──────────────────────────────────────────────────────────────────

def test_state_without_key_or_login(client):
    st = client.get("/api/push").json()
    assert st == {"configured": False, "key": None, "logged_in": False, "devices": []}


def test_subscribe_needs_login_origin_and_key(client, vapid):
    d = Device()
    assert client.post("/api/push/subscribe", json=d.sub(), headers=ORIGIN).status_code == 401
    uid = _user()
    _login(client, uid)
    assert client.post("/api/push/subscribe", json=d.sub()).status_code == 403  # Origin 없음(CSRF)
    bad = d.sub()
    bad["endpoint"] = "https://evil.example/x"
    r = client.post("/api/push/subscribe", json=bad, headers=ORIGIN)
    assert r.status_code == 400 and "지원하지 않는" in r.json()["detail"]
    assert client.post("/api/push/subscribe", json=d.sub(), headers=ORIGIN).json() == {"ok": True, "count": 1}
    st = client.get("/api/push").json()
    assert st["configured"] and st["key"] == push.public_key(vapid) and st["logged_in"]
    assert [x["label"] for x in st["devices"]] == ["안드로이드 크롬"]
    assert "endpoint" not in st["devices"][0]  # 구독 주소는 화면에 내보내지 않는다
    mine = client.post("/api/push/state", json={"endpoint": d.endpoint}, headers=ORIGIN).json()
    assert mine["devices"][0]["this"] is True


def test_subscribe_unconfigured_is_503(client):
    _login(client, _user())
    assert client.post("/api/push/subscribe", json=Device().sub(), headers=ORIGIN).status_code == 503


def test_resubscribe_updates_same_row_and_moves_between_accounts(client, vapid):
    d = Device()
    a, b = _user(), _user()
    _login(client, a)
    client.post("/api/push/subscribe", json=d.sub("아이폰 사파리"), headers=ORIGIN)
    client.post("/api/push/subscribe", json={**d.sub(), "label": None}, headers=ORIGIN)
    rows = _subs(a)
    assert len(rows) == 1 and rows[0].label == "아이폰 사파리"  # 이름 없이 다시 알리면 이름은 그대로
    _login(client, b)
    client.post("/api/push/subscribe", json=d.sub(), headers=ORIGIN)
    assert _subs(a) == [] and len(_subs(b)) == 1  # 한 기기는 마지막에 켠 사람에게만


def test_device_limit_drops_oldest(client, vapid):
    uid = _user()
    _login(client, uid)
    devs = [Device() for _ in range(push.MAX_DEVICES + 2)]
    for d in devs:
        client.post("/api/push/subscribe", json=d.sub(), headers=ORIGIN)
    ends = {r.endpoint for r in _subs(uid)}
    assert len(ends) == push.MAX_DEVICES and devs[-1].endpoint in ends and devs[0].endpoint not in ends


def test_unsubscribe_only_own_devices(client, vapid):
    a, b = _user(), _user()
    da, db_ = Device(), Device()
    _login(client, a)
    client.post("/api/push/subscribe", json=da.sub(), headers=ORIGIN)
    _login(client, b)
    client.post("/api/push/subscribe", json=db_.sub(), headers=ORIGIN)
    a_id = _subs(a)[0].id
    assert client.post("/api/push/unsubscribe", json={"id": a_id}, headers=ORIGIN).json() == {"ok": False}
    assert len(_subs(a)) == 1
    assert client.post("/api/push/unsubscribe", json={"endpoint": db_.endpoint}, headers=ORIGIN).json() == {"ok": True}
    assert _subs(b) == []


# ── 보내기 ────────────────────────────────────────────────────────────────

def test_send_encrypts_signs_and_cleans_up(client, vapid, wire):
    got, codes = wire
    uid = _user()
    ok, gone, broken = Device(), Device(), Device()
    for d in (ok, gone, broken):
        push.subscribe(uid, d.endpoint, *d.sub()["keys"].values())
    codes[gone.endpoint], codes[broken.endpoint] = 410, 500
    assert push.send_to_user(uid, {"title": "가게", "body": "새 문의가 왔어요.", "url": "/owner", "tag": "t"}) == 1
    req = next(r for r in got if str(r.url) == ok.endpoint)
    assert req.headers["Content-Encoding"] == "aes128gcm" and req.headers["TTL"] == "86400"
    assert req.headers["Authorization"].startswith("vapid t=") and req.headers["Urgency"] == "high"
    assert json.loads(ok.decrypt(req.content)) == {"title": "가게", "body": "새 문의가 왔어요.", "url": "/owner", "tag": "t"}
    rows = {r.endpoint: r for r in _subs(uid)}
    assert gone.endpoint not in rows  # 410 = 기기가 알림을 끔 → 지운다
    assert rows[ok.endpoint].last_ok_at is not None and rows[ok.endpoint].fail_count == 0
    assert rows[broken.endpoint].fail_count == 1


def test_repeated_failures_remove_subscription(client, vapid, wire):
    _got, codes = wire
    uid = _user()
    d = Device()
    push.subscribe(uid, d.endpoint, *d.sub()["keys"].values())
    codes[d.endpoint] = 503
    for _ in range(push.MAX_FAILS):
        push.send_to_user(uid, {"title": "t", "body": "b"})
    assert _subs(uid) == []


def test_send_without_key_does_nothing(client, wire):
    got, _ = wire
    uid = _user()
    with get_sessionmaker()() as db, db.begin():
        d = Device()
        db.add(PushSubscriptionRow(user_id=uid, endpoint=d.endpoint, p256dh=_b64e(d.pub), auth=_b64e(d.auth)))
    assert push.send_to_user(uid, {"title": "t"}) == 0 and got == []


def test_test_endpoint_sends_and_rate_limits(client, vapid, wire):
    got, _ = wire
    uid = _user()
    _login(client, uid)
    d = Device()
    client.post("/api/push/subscribe", json=d.sub(), headers=ORIGIN)
    assert client.post("/api/push/test", headers=ORIGIN).json() == {"ok": True, "sent": 1}
    assert json.loads(d.decrypt(got[-1].content))["url"] == "/owner"
    assert client.post("/api/push/test", headers=ORIGIN).status_code == 429


# ── 허브: 문의가 오면 방장 휴대폰이 울린다 ────────────────────────────────────

def _owner_room(client, uid):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    room = store.read_room(rid)
    key = store.read_session(room["session_id"])["requirement_id"]
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRoomRow(user_id=uid, room_id=rid, member_id="owner"))
        db.add(ShopRow(site_key=key, name="달빛 미용실"))
    return rid


def test_hub_pushes_to_room_owner_without_customer_details(client, vapid, wire, monkeypatch):
    got, _ = wire
    monkeypatch.setattr(notify, "SYNC", True)
    uid = _user()
    rid = _owner_room(client, uid)
    d = Device()
    push.subscribe(uid, d.endpoint, *d.sub()["keys"].values())
    notify.owner_kakao(rid, "사이트로 새 문의가 왔어요.\n이름: 홍길동\n연락처: 010-1111-2222\n내용: 커트 예약")
    msg = json.loads(d.decrypt(got[-1].content))
    assert msg == {"title": "달빛 미용실", "body": "사이트로 새 문의가 왔어요.", "url": f"/room.html?room={rid}", "tag": f"agt-{rid}"}
    assert "홍길동" not in got[-1].content.decode("latin-1")


def test_hub_push_failure_does_not_block_kakao(client, monkeypatch):
    monkeypatch.setattr(notify, "SYNC", True)
    sent = []
    monkeypatch.setattr(push, "send_to_room_owner", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    from app.services import kakao_talk
    monkeypatch.setattr(kakao_talk, "send_to_room_owner", lambda rid, text: sent.append(text) or True)
    notify.owner("r-x", "새 채팅이 왔어요.")
    assert sent == ["새 채팅이 왔어요."]


def test_withdraw_removes_devices(client, vapid):
    uid = _user()
    d = Device()
    push.subscribe(uid, d.endpoint, *d.sub()["keys"].values())
    accounts.withdraw(uid)
    assert _subs(uid) == []


def test_keystore_checks_vapid_key():
    ok, _ = keystore.test("vapid_private_key", push.generate_private_key())
    bad, msg = keystore.test("vapid_private_key", "not-a-key-at-all")
    assert ok and not bad and "P-256" in msg


def test_owner_page_is_installable_with_push(client):
    m = client.get("/manifest-owner.json").json()
    assert m["start_url"].startswith("/owner") and m["display"] == "standalone" and m["id"] == "/owner"
    html = client.get("/owner").text
    assert 'href="/manifest-owner.json"' in html and 'src="/push.js"' in html and 'id="pushbox"' in html
    sw = client.get("/sw.js").text
    assert "addEventListener('push'" in sw and "notificationclick" in sw and "pushsubscriptionchange" in sw
    assert "AgtPush" in client.get("/push.js").text
