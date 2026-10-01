"""운영자 텔레그램 알림 (OPS_ALERT_CONTRACT, D33·D49·O-4).

토큰(keystore telegram_bot_token)과 대화방(.env TELEGRAM_CHAT_ID)이 둘 다 있을 때만 보낸다.
알림 글에는 사건 종류·사이트 키·업종·사유·숫자만 넣고, 보내기 직전에 한 번 더 가린다.
같은 종류는 10분에 한 번만 보내고, 그사이 생긴 건수는 다음 알림에 붙인다. 보내기는 뒤(스레드)에서 한다.
"""
import logging
import threading
import time
from typing import Optional

import httpx

from app.config import settings
from app.services import keystore

log = logging.getLogger(__name__)

COOLDOWN_SEC = 600
_lock = threading.Lock()
_last: dict = {}
_skipped: dict = {}
_quiet = threading.local()  # 알림을 보내는 동안 생긴 로그는 다시 알리지 않는다(되돌이 방지)
_installed = False


class _HideTelegramUrl(logging.Filter):
    """텔레그램 API 주소에는 봇 토큰이 들어 있다. httpx가 남기는 요청 줄을 지운다(키 연결 테스트 포함)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            return "api.telegram.org/bot" not in record.getMessage()
        except Exception:
            return True


logging.getLogger("httpx").addFilter(_HideTelegramUrl())


def configured() -> bool:
    try:
        token = keystore.get("telegram_bot_token")
    except Exception:
        token = None
    return bool(token and (settings.telegram_chat_id or "").strip())


def _mask(text: str) -> str:
    try:
        from evals.live_metrics import mask_pii
        return mask_pii(text)
    except Exception:
        return text


def _post(text: str) -> bool:
    _quiet.on = True
    try:
        token = keystore.get("telegram_bot_token")
        r = httpx.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=5,
                       json={"chat_id": (settings.telegram_chat_id or "").strip(), "text": text,
                             "disable_web_page_preview": True})
        return r.status_code == 200
    except Exception as e:
        log.warning("텔레그램 알림 실패: %s", type(e).__name__)  # 예외 글에는 토큰 든 주소가 있을 수 있어 종류만
        return False
    finally:
        _quiet.on = False


def _dispatch(body: str) -> None:
    threading.Thread(target=_post, args=(body,), daemon=True).start()


def send(kind: str, text: str, wait: bool = False) -> bool:
    """알림 한 건. 보냈으면(또는 뒤에서 보내는 중이면) True. 꺼져 있거나 10분 안에 같은 종류를 보냈으면 False.

    wait=True는 바로 보내고 결과를 돌려준다(서버에서 시험할 때, 쉬는 시간 무시).
    """
    if not configured():
        return False
    now = time.monotonic()
    with _lock:
        last = _last.get(kind)
        if not wait and last is not None and now - last < COOLDOWN_SEC:
            _skipped[kind] = _skipped.get(kind, 0) + 1
            return False
        _last[kind] = now
        extra = _skipped.pop(kind, 0)
    body = _mask(text)[:500] + (f"\n(그사이 같은 알림 {extra}건 더)" if extra else "")
    if wait:
        return _post(body)
    _dispatch(body)
    return True


_EVENTS = {
    "site_published": lambda p: f"[공개] 새 사이트 {p.get('site', '')} · {p.get('industry', '')} · {p.get('variant', '')}안",
    "payment_mismatch": lambda p: f"[결제] 금액 불일치로 실패 처리 · 가게 {p.get('site', '')} · {p.get('reason', '')}",
    "webhook_bad_signature": lambda p: f"[결제] 웹훅 서명 실패 · {p.get('reason', '')}",
    "quota_exceeded": lambda p: (f"[한도] 가게 {p.get('site', '')} · "
                                 f"{ {'design': '시안 만들기', 'restyle': '디자인 고치기'}.get(p.get('kind'), p.get('kind', '')) } "
                                 f"무료 횟수 넘김 {p.get('over', '')}회 (지불 의사 신호)"),
}


def on_event(event: str, props: Optional[dict]) -> None:
    """사건 기록(funnel.record) 중 운영자가 알아야 할 것만 알린다. 실패해도 기록은 그대로."""
    make = _EVENTS.get(event)
    if make is None:
        return
    try:
        send(event, make(props if isinstance(props, dict) else {}))
    except Exception:
        pass


class _ErrorHandler(logging.Handler):
    """ERROR 이상 로그를 알린다. 알림 모듈·httpx 자신의 로그는 빼서 되돌이가 없게 한다."""

    _last_record = None  # 루트와 uvicorn.error 둘 다에 붙어 있어 같은 기록이 두 번 올 수 있다

    def emit(self, record: logging.LogRecord) -> None:
        if record is self._last_record or getattr(_quiet, "on", False) \
                or record.name.startswith((__name__, "httpx", "httpcore")):
            return
        self._last_record = record
        try:
            msg = (record.getMessage().splitlines() or [""])[0][:200]
            exc = record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else ""
            send("error:" + record.name, f"[오류] {record.name} · {msg}" + (f" ({exc})" if exc else ""))
        except Exception:
            pass


def install() -> None:
    """서버가 뜰 때 한 번: ERROR 로그를 알림으로. uvicorn의 처리 안 된 예외 로그는 루트로 안 오므로 따로 붙인다."""
    global _installed
    if _installed:
        return
    _installed = True
    handler = _ErrorHandler(level=logging.ERROR)
    for name in ("", "uvicorn.error"):
        logging.getLogger(name).addHandler(handler)
