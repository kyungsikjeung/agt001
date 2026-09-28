"""문자 발송 (CUSTOMER_PLAN §4.2 V1 + OWNER_SETTINGS_PLAN §1.4).

가게 키가 있으면 그것, 없으면 플랫폼 키(settings.solapi_*, settings.sms_sender),
둘 다 없으면 개발 모드(로그만 남기고 보낸 걸로 친다).
비밀값과 전체 전화번호는 절대 로그에 남기지 않는다(끝 4자리만).
"""
import datetime
import hashlib
import hmac
import logging
import secrets
from typing import Optional

import httpx

from app.config import settings

log = logging.getLogger(__name__)

SOLAPI_URL = "https://api.solapi.com/messages/v4/send"
BALANCE_URL = "https://api.solapi.com/cash/v1/balance"
TIMEOUT_SEC = 10.0


def _last4(to: str) -> str:
    digits = "".join(ch for ch in (to or "") if ch.isdigit())
    return digits[-4:] if digits else "????"


def _auth_headers(key: str, secret: str) -> dict:
    date = datetime.datetime.now(datetime.timezone.utc).isoformat()
    salt = secrets.token_hex(16)
    signature = hmac.new(secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    return {"Authorization": f"HMAC-SHA256 apiKey={key}, date={date}, salt={salt}, signature={signature}"}


def _platform_creds() -> Optional[tuple]:
    key = (settings.solapi_api_key or "").strip()
    secret = (settings.solapi_api_secret or "").strip()
    sender = (settings.sms_sender or "").strip()
    return (key, secret, sender) if (key and secret and sender) else None


def _creds(site_key: Optional[str] = None) -> Optional[tuple]:
    if site_key:
        try:
            from app.services import shop_settings
            got = shop_settings.sms_credentials(site_key)
        except Exception:
            got = None
        if got:
            return got
    return _platform_creds()


def send(to: str, text: str, site_key: Optional[str] = None) -> bool:
    """보냈으면 True, 실패면 False(예외는 내지 않는다)."""
    creds = _creds(site_key)
    if creds is None:
        log.warning("문자 개발 모드(솔라피 키 없음): 끝 %s에 보낼 본문: %s", _last4(to), text)
        return True
    key, secret, sender = creds
    headers = _auth_headers(key, secret)
    try:
        resp = httpx.post(SOLAPI_URL, json={"message": {"to": to, "from": sender, "text": text}},
                          headers=headers, timeout=TIMEOUT_SEC)
    except httpx.HTTPError as e:
        log.warning("문자 보내기 실패(통신 %s): 끝 %s", type(e).__name__, _last4(to))
        return False
    except Exception:
        log.warning("문자 보내기 실패(통신): 끝 %s", _last4(to))
        return False
    if 200 <= resp.status_code < 300:
        return True
    log.warning("문자 보내기 실패(상태 %s): 끝 %s", resp.status_code, _last4(to))
    return False


def available(site_key: Optional[str] = None) -> bool:
    """가게 키 또는 플랫폼 키가 있으면 True. 개발 모드(settings.sms_dev_mode)면 True."""
    if _creds(site_key) is not None:
        return True
    return bool(settings.sms_dev_mode)


def check_key(key: str, secret: str) -> bool:
    """저장 전 연결 테스트. 잔액 조회가 200이면 True. 실패해도 예외는 내지 않는다."""
    k = (key or "").strip()
    s = (secret or "").strip()
    if not (k and s):
        return False
    try:
        resp = httpx.get(BALANCE_URL, headers=_auth_headers(k, s), timeout=TIMEOUT_SEC)
    except Exception:
        return False
    return resp.status_code == 200
