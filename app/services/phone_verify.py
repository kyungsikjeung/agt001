"""문자 인증 바탕 (CUSTOMER_PLAN §4.1·§4.2 V1, 기기 기억 + 자동 입력).

예약 API(V2)가 쓴다. DB 세션은 안에서 직접 연다(bookings.py와 같게).
- start: 폼 내용·번호·인증번호 해시·만료(3분)를 저장하고 토큰을 돌려준다. 같은 가게·번호로 60초 안에는 거절.
- check: 맞으면 저장했던 폼 내용을 돌려주고 행을 '다 쓴' 표시로 남긴다. 5번 틀리면 잠김, 3분 지나면 만료.
- resend: 같은 내용으로 새 행을 만들고 새 토큰을 돌려준다. 예전 토큰은 못 쓰게 된다.
- 행은 '보낸 문자 기록'이기도 하다: 하루 상한(번호당·가게당)이 행 수로 세므로 지우지 않고 하루 뒤 청소한다.
  (10/13 점검: 다시 보내기·인증 성공 때 행을 지워서 상한이 늘 0으로 세어져 문자 폭탄이 됐다)
- device_cookie/device_ok: 이 기기 기억 쿠키(90일). 서명 키는 token_enc_key → 없으면 kakao_client_secret.
"""
import datetime
import hashlib
import hmac
import logging
import re
import secrets
from typing import Optional
from urllib.parse import urlparse

from sqlalchemy import delete, func, select, update

from app.config import settings
from app.db.models import PhoneVerificationRow
from app.db.session import get_sessionmaker
from app.services import customers
from app.services import sms as sms_svc

log = logging.getLogger(__name__)

CODE_TTL = datetime.timedelta(minutes=3)
RESEND_WAIT = datetime.timedelta(seconds=60)
MAX_ATTEMPTS = 5
DEVICE_DAYS = 90
PURGE_AFTER = datetime.timedelta(days=1)
DAILY_MAX = 5  # 한 번호로 하루에 보내는 인증 문자 수(가게 상관없이). 문자 폭탄·비용 막기


class VerifyError(Exception):
    """손님에게 보여 줄 한 줄 사유."""


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _code_hash(token: str, code: str) -> str:
    return hashlib.sha256(f"{token}{code}".encode()).hexdigest()


def _public_host() -> Optional[str]:
    base = (settings.public_base_url or "").strip()
    if not base:
        return None
    try:
        return urlparse(base).hostname or None
    except Exception:
        return None


_URLISH = re.compile(r"(?:https?://|www\.)\S*|[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}\S*", re.I)  # 주소·도메인 모양 통째로(3.5평 같은 숫자는 둔다)


def _sms_label(shop_name: Optional[str]) -> str:
    """문자 머리 [가게 이름]. 가게 이름은 사장님이 정하는 값이라 우리 발신번호로 피싱 글이 나가지 않게
    줄바꿈·괄호·주소 모양을 빼고 20자로 자른다(10/13 점검). 남는 게 없으면 '예약'."""
    shop = re.sub(r"[\r\n\t\[\]<>]+", " ", str(shop_name or ""))
    shop = " ".join(_URLISH.sub(" ", shop).split())[:20].strip()
    return shop or "예약"


def _sms_text(code: str, shop_name: Optional[str]) -> str:
    text = f"[{_sms_label(shop_name)}] 인증번호 {code}"
    host = _public_host()
    if host:
        text += f"\n\n@{host} #{code}"
    return text


def _device_key() -> Optional[str]:
    key = settings.token_enc_key or settings.kakao_client_secret
    if not key or not key.strip():
        return None
    return key


def start(site_key: str, phone_raw: Optional[str], payload: dict, shop_name: Optional[str] = None) -> str:
    """인증번호를 보내고 토큰을 돌려준다. 입력이 틀리면 VerifyError."""
    phone = customers.normalize_phone(phone_raw)
    if not phone or not site_key:
        raise VerifyError("전화번호를 다시 확인해 주세요.")
    return _issue(site_key, phone, {**(payload or {}), "_shop": (shop_name or "").strip()})


def _issue(site_key: str, phone: str, payload: dict, old_token: Optional[str] = None) -> str:
    """1분·하루 제한을 보고 문자를 보낸 뒤 새 행을 만든다(old_token이 있으면 그 행을 지운다)."""
    now = _now()
    with get_sessionmaker()() as db:
        recent = db.scalar(select(PhoneVerificationRow.id).where(  # 1분 제한은 아직 기다리는 요청만(다 쓴 것은 하루 상한에서 센다)
            PhoneVerificationRow.site_key == site_key,
            PhoneVerificationRow.phone == phone,
            PhoneVerificationRow.code_hash != "",
            PhoneVerificationRow.created_at > now - RESEND_WAIT))
        today = db.scalar(select(func.count()).select_from(PhoneVerificationRow).where(
            PhoneVerificationRow.phone == phone,
            PhoneVerificationRow.created_at > now - datetime.timedelta(days=1))) or 0
    if recent is not None:
        raise VerifyError("인증번호는 1분 뒤에 다시 받을 수 있어요.")
    if today >= DAILY_MAX:
        raise VerifyError("오늘은 인증번호를 더 받을 수 없어요. 가게에 전화로 예약해 주세요.")
    code = f"{secrets.randbelow(1000000):06d}"
    token = secrets.token_urlsafe(24)
    if not sms_svc.send(phone, _sms_text(code, payload.get("_shop")), site_key=site_key):
        raise VerifyError("인증번호를 보내지 못했어요. 잠시 뒤 다시 시도해 주세요.")
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(PhoneVerificationRow).where(PhoneVerificationRow.expires_at < now - PURGE_AFTER))
        if old_token:  # 예전 토큰은 못 쓰게만 한다(지우면 하루 상한에서 빠진다)
            db.execute(update(PhoneVerificationRow).where(PhoneVerificationRow.token == old_token)
                       .values(code_hash="", payload={}, expires_at=now))
        db.add(PhoneVerificationRow(token=token, site_key=site_key, phone=phone,
                                    code_hash=_code_hash(token, code), payload=payload,
                                    attempts=0, expires_at=now + CODE_TTL))
    return token


def _same_shop(row, site_key: Optional[str]) -> bool:
    """토큰이 이 주소의 가게 것인가. 가게 A의 토큰으로 가게 B에 가입·예약·주문하지 못하게(10/13 점검)."""
    return site_key is None or (row.site_key or "") == (site_key or "")


def check(token: str, code: Optional[str], site_key: Optional[str] = None) -> dict:
    """맞으면 저장했던 폼 내용을 돌려주고 행을 '다 쓴' 표시로 남긴다. 틀리면 VerifyError.
    site_key를 주면 그 가게 토큰만 받는다."""
    now = _now()
    with get_sessionmaker()() as db:
        row = db.scalar(select(PhoneVerificationRow).where(PhoneVerificationRow.token == (token or ""))
                        .with_for_update())
        if row is None or not row.code_hash or not _same_shop(row, site_key):  # 없거나 이미 쓴·다른 가게 토큰
            raise VerifyError("인증 요청을 찾을 수 없어요.")
        if now > row.expires_at:
            raise VerifyError("인증 시간이 지났어요. 인증번호를 다시 받아 주세요.")
        if row.attempts >= MAX_ATTEMPTS:
            raise VerifyError("여러 번 틀려서 잠겼어요. 인증번호를 다시 받아 주세요.")
        want = _code_hash(row.token, (code or "").strip())
        if not hmac.compare_digest(row.code_hash, want):
            row.attempts += 1
            db.commit()
            if row.attempts >= MAX_ATTEMPTS:
                raise VerifyError("여러 번 틀려서 잠겼어요. 인증번호를 다시 받아 주세요.")
            raise VerifyError(f"인증번호가 맞지 않아요. (남은 횟수 {MAX_ATTEMPTS - row.attempts}번)")
        payload = {k: v for k, v in (row.payload or {}).items() if k != "_shop"}
        # 다 쓴 표시만 남긴다: 폼 내용은 비우고 바로 만료. 행은 하루 상한 셈에 남았다가 하루 뒤 청소된다.
        row.code_hash, row.payload, row.expires_at = "", {}, now
        db.commit()
        return payload


def resend(token: str, site_key: Optional[str] = None) -> str:
    """같은 내용으로 새로 보내고 새 토큰을 돌려준다. 예전 토큰은 못 쓰게 된다. site_key를 주면 그 가게 토큰만."""
    with get_sessionmaker()() as db:
        row = db.scalar(select(PhoneVerificationRow).where(PhoneVerificationRow.token == (token or "")))
        if row is None or not row.code_hash or not _same_shop(row, site_key):
            raise VerifyError("인증 요청을 찾을 수 없어요.")
        site_key, phone, payload = row.site_key, row.phone, dict(row.payload or {})
    return _issue(site_key, phone, payload, old_token=token)


def device_cookie(site_key: str, phone: str) -> Optional[str]:
    """이 기기 기억 쿠키 값. 서명 키가 없으면 None(기기 기억 끔)."""
    key = _device_key()
    norm = customers.normalize_phone(phone)
    if key is None or not norm or not site_key:
        return None
    expires = int(_now().timestamp()) + DEVICE_DAYS * 86400
    sig = hmac.new(key.encode(), f"{site_key}:{norm}:{expires}".encode(), hashlib.sha256).hexdigest()
    return f"{norm}.{expires}.{sig}"


def device_ok(cookie: Optional[str], site_key: str, phone_raw: Optional[str]) -> bool:
    """쿠키 서명이 맞고, 만료 전이고, 안의 번호가 폼 번호와 같고, 가게가 맞으면 True."""
    try:
        key = _device_key()
        if not key or not cookie or not site_key:
            return False
        phone = customers.normalize_phone(phone_raw)
        if phone is None:
            return False
        parts = cookie.split(".")
        if len(parts) != 3:
            return False
        c_phone, c_expires, c_sig = parts
        if c_phone != phone:
            return False
        if int(c_expires) <= int(_now().timestamp()):
            return False
        want = hmac.new(key.encode(), f"{site_key}:{c_phone}:{c_expires}".encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(want, c_sig)
    except (ValueError, TypeError):
        return False


def device_phone(cookie: Optional[str], site_key: str) -> Optional[str]:
    """기기 기억 쿠키 안의 번호. device_ok와 같은 서명·만료 검사, 맞으면 번호."""
    try:
        key = _device_key()
        if not key or not cookie or not site_key:
            return None
        parts = cookie.split(".")
        if len(parts) != 3:
            return None
        c_phone, c_expires, c_sig = parts
        if customers.normalize_phone(c_phone) != c_phone:
            return None
        if int(c_expires) <= int(_now().timestamp()):
            return None
        want = hmac.new(key.encode(), f"{site_key}:{c_phone}:{c_expires}".encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(want, c_sig):
            return None
        return c_phone
    except (ValueError, TypeError):
        return None


def purge() -> int:
    """만료 1일이 지난 요청을 지운다."""
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(PhoneVerificationRow)
                       .where(PhoneVerificationRow.expires_at < _now() - PURGE_AFTER)).rowcount
    if n:
        log.info("인증 요청 %d건 삭제 (만료 1일 경과)", n)
    return n
