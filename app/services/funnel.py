"""유입·전환 단계 기록 (DECISIONS.md D16).

방문 → 시작하기 → 첫 메시지 → 요구사항 확정 → 가입 → 제작. 브라우저 단계는 POST /events로,
서버 단계(대화 상태 전이)는 chat_flow가 같은 트랜잭션 안에서 남긴다. 개인정보(IP, 이름, 연락처,
대화 내용)는 저장하지 않는다. 90일이 지나면 지운다.
"""
import datetime
import logging
import re
import threading
import time
from collections import deque
from typing import Optional

from sqlalchemy import delete

from app import store
from app.db.models import FunnelEventRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

RETENTION_DAYS = 90

# 브라우저가 보낼 수 있는 이벤트. 목록 밖 이름은 버린다(아무 문자열로 DB를 채우지 못하게).
CLIENT_EVENTS = frozenset({"landing_view", "start_click", "template_click", "login_click", "chat_open"})
# 서버가 대화 상태 전이에서 남기는 이벤트.
SERVER_EVENTS = frozenset({"request_submitted", "requirement_approved", "generate_start", "generate_done", "signup"})

_TOKEN = re.compile(r"[^A-Za-z0-9_.:-]")
_MAX_LEN = 64

# IP당 분당 요청 상한. IP는 이 메모리 안에서만 쓰고 저장하지 않는다.
RATE_LIMIT_PER_MIN = 60
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _clean(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = _TOKEN.sub("", str(value))[:_MAX_LEN]
    return cleaned or None


def allow(client_key: str) -> bool:
    now = time.monotonic()
    with _hits_lock:
        q = _hits.setdefault(client_key, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            return False
        q.append(now)
        if len(_hits) > 10_000:  # 오래된 키가 쌓여 메모리를 먹지 않게
            for k in [k for k, v in _hits.items() if not v]:
                _hits.pop(k, None)
        return True


def record(event: str, *, visitor_id=None, session_id=None, source=None, campaign=None, template_id=None) -> bool:
    """이벤트 한 건을 남긴다. 요청 트랜잭션 안이면 그 트랜잭션에 합류한다. 알 수 없는 이벤트는 버린다."""
    if event not in CLIENT_EVENTS and event not in SERVER_EVENTS:
        return False
    row = FunnelEventRow(
        event=event, visitor_id=_clean(visitor_id), session_id=_clean(session_id),
        source=_clean(source), campaign=_clean(campaign), template_id=_clean(template_id),
    )
    with store._transaction() as tx:
        tx.db.add(row)
    return True


def purge_expired(now: Optional[datetime.datetime] = None) -> int:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=RETENTION_DAYS)
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(FunnelEventRow).where(FunnelEventRow.ts < cutoff)).rowcount
    if n:
        log.info("유입 기록 %d건 삭제 (%d일 경과)", n, RETENTION_DAYS)
    return n
