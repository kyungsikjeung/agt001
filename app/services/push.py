"""휴대폰 알림 — 웹 푸시 (OWNER_NOTIFY_PLAN N1·N2). 무료. 홈 화면에 둔 사장님 화면이 앱처럼 울린다.

표준을 그대로 따른다(cryptography + httpx만, 새 의존성 없음):
- RFC 8030 보내기: 기기 구독 주소(endpoint)에 POST. TTL(하루)·Urgency(high) 헤더.
- RFC 8292 VAPID: 우리 서버임을 ES256 서명(JWT)으로 밝힌다. 비밀 키는 keystore "vapid_private_key".
- RFC 8291 내용 암호화(aes128gcm): 기기 공개 키(p256dh)·인증 비밀(auth)로만 풀린다. 푸시 회사는 내용을 못 본다.

잠금 화면에 보이므로 손님 이름·연락처는 싣지 않는다(lock_screen_line). 받는 사람은 카톡과 같은 방장 계정이다.
"""
import base64
import datetime
import json
import logging
import os
import re
import struct
import time
from typing import Optional
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import delete, select

from app.config import settings
from app.db.models import PushSubscriptionRow, RoomRow, SessionRow, ShopRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

# 브라우저 회사 푸시 서버만 부른다(아무 주소나 받으면 우리 서버가 남의 서버를 두드리게 된다).
ALLOWED_HOSTS = ("fcm.googleapis.com", "android.googleapis.com", "push.services.mozilla.com",
                 "push.apple.com", "notify.windows.com")
MAX_DEVICES = 10  # 한 사람이 켤 수 있는 기기 수. 넘으면 가장 오래 안 쓴 것부터 지운다
MAX_FAILS = 10  # 이만큼 연달아 실패하면 구독을 지운다(404·410은 바로 지움)
TTL_SEC = 86400  # 휴대폰이 꺼져 있어도 하루는 기다렸다 보낸다
TIMEOUT = 5.0
RECORD_SIZE = 4096
MAX_PAYLOAD = 3000  # 푸시 회사 한도(4KB)에서 암호화 머리를 빼고 넉넉히

# 테스트에서 httpx.MockTransport를 넣어 가짜 응답을 쓴다.
_TRANSPORT: Optional[httpx.BaseTransport] = None


class PushError(Exception):
    """사용자에게 보여 줄 한 줄."""


def _b64d(s: str) -> bytes:
    s = (s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _point(key: ec.EllipticCurvePublicKey) -> bytes:
    return key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# ── VAPID 키 ──────────────────────────────────────────────────────────────

def generate_private_key() -> str:
    """새 VAPID 비밀 키(base64url 32바이트). scripts/gen_vapid.py가 쓴다."""
    return _b64e(ec.generate_private_key(ec.SECP256R1()).private_numbers().private_value.to_bytes(32, "big"))


def _private_key(value: str) -> ec.EllipticCurvePrivateKey:
    try:
        raw = _b64d(value)
    except ValueError as e:
        raise ValueError("base64url이 아님") from e
    if len(raw) != 32:
        raise ValueError("32바이트가 아님")
    return ec.derive_private_key(int.from_bytes(raw, "big"), ec.SECP256R1())


def public_key(private_value: str) -> str:
    """비밀 키 → 브라우저에 줄 공개 키(applicationServerKey, base64url 65바이트). 키가 틀리면 ValueError."""
    return _b64e(_point(_private_key(private_value).public_key()))


_key_cache: dict = {"value": None, "key": None}


def _server_key() -> Optional[ec.EllipticCurvePrivateKey]:
    from app.services import keystore
    value = (keystore.get("vapid_private_key") or "").strip()
    if not value:
        return None
    if _key_cache["value"] != value:
        try:
            _key_cache["key"] = _private_key(value)
        except ValueError:
            log.error("VAPID 비밀 키 형식이 틀림 — 휴대폰 알림을 끕니다")
            _key_cache["key"] = None
        _key_cache["value"] = value
    return _key_cache["key"]


def configured() -> bool:
    return _server_key() is not None


def application_server_key() -> Optional[str]:
    key = _server_key()
    return _b64e(_point(key.public_key())) if key else None


def _subject() -> str:
    sub = (settings.vapid_subject or "").strip() or (settings.public_base_url or "").strip()
    if sub.startswith(("mailto:", "https://")):
        return sub
    return "mailto:noreply@example.com"  # 애플은 sub가 없으면 거절한다. 운영에서는 VAPID_SUBJECT를 넣는다


def vapid_header(endpoint: str, key: ec.EllipticCurvePrivateKey, now: Optional[float] = None) -> str:
    """Authorization 헤더(RFC 8292 §3). aud = 구독 주소의 출처, 12시간 유효."""
    parts = urlsplit(endpoint)
    claims = {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": _subject()}
    head = _b64e(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = _b64e(json.dumps(claims, separators=(",", ":")).encode())
    r, s = decode_dss_signature(key.sign(f"{head}.{body}".encode(), ec.ECDSA(hashes.SHA256())))
    sig = _b64e(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={head}.{body}.{sig}, k={_b64e(_point(key.public_key()))}"


# ── 내용 암호화 (RFC 8291, aes128gcm) ──────────────────────────────────────

def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt(payload: bytes, p256dh: str, auth: str, *, salt: Optional[bytes] = None,
            server_key: Optional[ec.EllipticCurvePrivateKey] = None) -> bytes:
    """기기만 풀 수 있게 암호화한 본문. salt·server_key는 시험용(보낼 때마다 새로 만든다)."""
    ua_pub = _b64d(p256dh)
    secret = _b64d(auth)
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub = _point(as_key.public_key())
    shared = as_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(secret, shared, b"WebPush: info\x00" + ua_pub + as_pub, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    body = AESGCM(cek).encrypt(nonce, payload + b"\x02", None)  # 0x02 = 마지막 기록
    return salt + struct.pack("!IB", RECORD_SIZE, len(as_pub)) + as_pub + body


# ── 구독 ─────────────────────────────────────────────────────────────────

def check_endpoint(endpoint: str) -> str:
    e = (endpoint or "").strip()
    if not e or len(e) > 1024:
        raise PushError("알림 주소가 비었거나 너무 길어요.")
    p = urlsplit(e)
    host = (p.hostname or "").lower()
    if p.scheme != "https" or p.username or p.password or p.port not in (None, 443):
        raise PushError("알림 주소 형식이 맞지 않아요.")
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise PushError("지원하지 않는 브라우저 알림 주소예요.")
    return e


def check_keys(p256dh: str, auth: str) -> tuple[str, str]:
    try:
        pub, secret = _b64d(p256dh), _b64d(auth)
        if len(pub) != 65 or pub[0] != 4 or len(secret) != 16:
            raise ValueError
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pub)
    except (ValueError, TypeError):
        raise PushError("기기 알림 열쇠가 맞지 않아요. 알림을 껐다 다시 켜 주세요.")
    return _b64e(pub), _b64e(secret)


def _label(label: Optional[str]) -> Optional[str]:
    s = re.sub(r"[\x00-\x1f\x7f]", "", (label or "")).strip()[:40]
    return s or None


def subscribe(user_id: str, endpoint: str, p256dh: str, auth: str, label: Optional[str] = None) -> int:
    """이 기기를 켠다(이미 있으면 열쇠·이름만 새로). 한 기기는 마지막에 켠 사람에게만 간다. 켜진 기기 수를 돌려준다."""
    endpoint = check_endpoint(endpoint)
    p256dh, auth = check_keys(p256dh, auth)
    with get_sessionmaker()() as db, db.begin():
        row = db.scalar(select(PushSubscriptionRow).where(PushSubscriptionRow.endpoint == endpoint))
        if row is None:
            db.add(PushSubscriptionRow(user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, label=_label(label)))
        else:
            row.user_id, row.p256dh, row.auth, row.fail_count = user_id, p256dh, auth, 0
            row.label = _label(label) or row.label  # 서비스워커가 다시 알릴 때는 이름이 없다
        db.flush()
        rows = db.scalars(select(PushSubscriptionRow).where(PushSubscriptionRow.user_id == user_id)
                          .order_by(PushSubscriptionRow.last_ok_at.desc().nulls_last(),
                                    PushSubscriptionRow.created_at.desc(), PushSubscriptionRow.id.desc())).all()
        others = [r for r in rows if r.endpoint != endpoint]
        for old in others[MAX_DEVICES - 1:]:
            db.delete(old)
        return min(len(others) + 1, MAX_DEVICES)


def unsubscribe(user_id: str, endpoint: Optional[str] = None, device_id: Optional[int] = None) -> bool:
    """이 사람의 기기 하나를 끈다(구독 주소 또는 화면의 기기 번호로)."""
    cond = [PushSubscriptionRow.user_id == user_id]
    if endpoint:
        cond.append(PushSubscriptionRow.endpoint == endpoint.strip())
    elif device_id is not None:
        cond.append(PushSubscriptionRow.id == device_id)
    else:
        return False
    with get_sessionmaker()() as db, db.begin():
        return db.execute(delete(PushSubscriptionRow).where(*cond)).rowcount > 0


def _iso(ts: Optional[datetime.datetime]) -> Optional[str]:
    return ts.isoformat() if ts else None


def devices(user_id: str, endpoint: Optional[str] = None) -> list[dict]:
    """화면용 기기 목록. 구독 주소는 내보내지 않는다(this = 지금 이 기기인지)."""
    with get_sessionmaker()() as db:
        rows = db.scalars(select(PushSubscriptionRow).where(PushSubscriptionRow.user_id == user_id)
                          .order_by(PushSubscriptionRow.created_at, PushSubscriptionRow.id)).all()
        return [{"id": r.id, "label": r.label or "이름 없는 기기", "created_at": _iso(r.created_at),
                 "last_ok_at": _iso(r.last_ok_at), "failing": r.fail_count > 0,
                 "this": bool(endpoint) and r.endpoint == endpoint} for r in rows]


# ── 보내기 ────────────────────────────────────────────────────────────────

def _post(endpoint: str, body: bytes, key: ec.EllipticCurvePrivateKey, urgency: str = "high") -> int:
    with httpx.Client(timeout=TIMEOUT, transport=_TRANSPORT) as c:
        r = c.post(endpoint, content=body, headers={
            "Authorization": vapid_header(endpoint, key),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SEC),
            "Urgency": urgency,
        })
    return r.status_code


def send_to_user(user_id: str, message: dict) -> int:
    """이 사람의 켜진 기기 모두에 보낸다. 받은 기기 수를 돌려준다. 키가 없으면 아무것도 안 한다.

    message = {title, body, url, tag}. 404·410(기기가 알림을 껐음)은 구독을 지우고, 다른 실패는 세다가 지운다.
    """
    key = _server_key()
    if key is None or not user_id:
        return 0
    payload = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode()
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("알림 내용이 너무 깁니다")
    with get_sessionmaker()() as db:
        subs = [(r.id, r.endpoint, r.p256dh, r.auth) for r in
                db.scalars(select(PushSubscriptionRow).where(PushSubscriptionRow.user_id == user_id)).all()]
    ok, gone, failed = [], [], []
    for sid, endpoint, p256dh, auth in subs:
        try:
            status = _post(endpoint, encrypt(payload, p256dh, auth), key)
        except (httpx.HTTPError, ValueError) as e:
            log.warning("휴대폰 알림 보내기 실패 sub=%s (%s)", sid, type(e).__name__)
            failed.append(sid)
            continue
        if 200 <= status < 300:
            ok.append(sid)
        elif status in (404, 410):
            gone.append(sid)
        else:
            log.warning("휴대폰 알림 거절 sub=%s status=%s", sid, status)
            failed.append(sid)
    if ok or gone or failed:
        now = datetime.datetime.now(datetime.timezone.utc)
        with get_sessionmaker()() as db, db.begin():
            for r in db.scalars(select(PushSubscriptionRow).where(PushSubscriptionRow.id.in_(ok + gone + failed))).all():
                if r.id in gone:
                    db.delete(r)
                elif r.id in ok:
                    r.last_ok_at, r.fail_count = now, 0
                else:
                    r.fail_count += 1
                    if r.fail_count >= MAX_FAILS:
                        db.delete(r)
    return len(ok)


# ── 사장님 알림 글 → 휴대폰 알림 ─────────────────────────────────────────────

def lock_screen_line(text: str) -> str:
    """잠금 화면에 보일 한 줄: 첫 줄의 ':' 앞까지(손님 이름·연락처·내용은 ':' 뒤나 다음 줄에 있다)."""
    first = (text or "").strip().split("\n", 1)[0]
    first = first.split(":", 1)[0].strip()
    return (first[:60] or "새 알림이 있어요.")


def click_url(room_id: str, text: str) -> str:
    """눌렀을 때 열 우리 사이트 안 주소. 글에 사장님 화면 링크가 있으면 그곳, 없으면 그 가게 채팅방."""
    base = (settings.public_base_url or "").rstrip("/")
    for m in re.finditer(r"(https?://\S+|(?<!\S)/owner\S*)", text or ""):
        u = m.group(1)
        if base and u.startswith(base + "/"):
            u = u[len(base):]
        if u.startswith("/owner"):
            return u
    return f"/room.html?room={room_id}"


def shop_name(room_id: str) -> Optional[str]:
    with get_sessionmaker()() as db:
        return db.scalar(select(ShopRow.name).join(SessionRow, SessionRow.requirement_id == ShopRow.site_key)
                         .join(RoomRow, RoomRow.session_id == SessionRow.id).where(RoomRow.id == room_id))


def send_to_room_owner(room_id: str, text: str) -> int:
    """카톡과 같은 받는 사람(방장 계정)의 휴대폰에 보낸다."""
    if not configured():
        return 0
    from app.services import kakao_talk
    user_id = kakao_talk.owner_user_id(room_id)
    if not user_id:
        return 0
    return send_to_user(user_id, {
        "title": (shop_name(room_id) or "한마디")[:40],
        "body": lock_screen_line(text),
        "url": click_url(room_id, text),
        "tag": f"agt-{room_id}",
    })
