"""문자 발송 (CUSTOMER_PLAN §4.2 V1).

솔라피 키·발신번호가 다 있으면 실제로 보내고, 하나라도 없으면 개발 모드로 로그만 남기고 보낸 걸로 친다.
비밀값과 전체 전화번호는 절대 로그에 남기지 않는다(끝 4자리만).
"""
import datetime
import hashlib
import hmac
import logging
import secrets

import httpx

from app.config import settings

log = logging.getLogger(__name__)

SOLAPI_URL = "https://api.solapi.com/messages/v4/send"
TIMEOUT_SEC = 10.0


def _last4(to: str) -> str:
    digits = "".join(ch for ch in (to or "") if ch.isdigit())
    return digits[-4:] if digits else "????"


def send(to: str, text: str) -> bool:
    """보냈으면 True, 실패면 False(예외는 내지 않는다)."""
    key = (settings.solapi_api_key or "").strip()
    secret = (settings.solapi_api_secret or "").strip()
    sender = (settings.sms_sender or "").strip()
    if not (key and secret and sender):
        log.warning("문자 개발 모드(솔라피 키 없음): 끝 %s에 보낼 본문: %s", _last4(to), text)
        return True
    date = datetime.datetime.now(datetime.timezone.utc).isoformat()
    salt = secrets.token_hex(16)
    signature = hmac.new(secret.encode(), (date + salt).encode(), hashlib.sha256).hexdigest()
    headers = {"Authorization": f"HMAC-SHA256 apiKey={key}, date={date}, salt={salt}, signature={signature}"}
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
