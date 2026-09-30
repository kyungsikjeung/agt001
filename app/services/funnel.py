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
CLIENT_EVENTS = frozenset({"landing_view", "start_click", "template_click", "login_click", "chat_open",
                           # 음성 인식 카운터(전사 원문·IP 저장 없음): 성공·빈결과·실패 횟수만
                           "voice_stt_ok", "voice_stt_empty", "voice_stt_fail"})
# 서버가 대화 상태 전이에서 남기는 이벤트.
SERVER_EVENTS = frozenset({"request_submitted", "requirement_approved", "generate_start", "generate_done", "signup",
                           # 디자인 학습 기록(D44·D45, app/services/design_log.py)
                           "design_shown", "design_chosen", "design_restyled", "site_published", "inquiry_received",
                           "unmet_need",
                            # 사진 선택지 답·실제 업로드(D48·D45, 원문·개인정보 없음)
                            "photo_answered", "photo_uploaded",
                            # AI 예시 이미지 생성(업종·칸만, 개인정보 없음)
                            "ai_image_made",
                            # 빌더에서 사진 고치기 AI 편집(업종·칸·예시/AI 출처만)
                            "ai_image_edited",
                            # 빌더 시작·기능 칩(B1, 업종·칩 종류·켜기/끄기만)
                            "builder_start", "builder_feature",
                            # 빌더 말로 고치기(B5, 종류·출처만)
                            "builder_say",
                            # 온라인 결제 운영 신호(W5-B, 금액·결제 번호·전화 없음)
                            "payment_mismatch", "webhook_bad_signature"})

_TOKEN = re.compile(r"[^A-Za-z0-9_.:-]")
_MAX_LEN = 64
# props에 넣을 수 있는 칸. 값은 목록 키·사이트 키 같은 영문 토큰, 숫자, 참거짓만.
PROP_KEYS = frozenset({"site", "industry", "variant", "v1", "v2", "v3", "palette", "font_pair", "density", "radius",
                       "lead", "hero", "source", "kind", "ref", "verdict", "label", "choice",
                       # 음성 인식 카운터 전용: 실패 사유·숫자 포함 여부만(원문·IP 금지)
                       "reason", "has_number"})
# label만 한글을 받는다(못 담은 섹션 이름 등, D44). 숫자는 지운다(전화·주소·가격이 섞여 들어오지 않게).
_LABEL = re.compile(r"[^A-Za-z가-힣 ]")
_LABEL_MAX = 20

# IP당 분당 요청 상한. IP는 이 메모리 안에서만 쓰고 저장하지 않는다.
RATE_LIMIT_PER_MIN = 60
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _clean(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    cleaned = _TOKEN.sub("", str(value))[:_MAX_LEN]
    return cleaned or None


def _props(props: Optional[dict]) -> Optional[dict]:
    out = {}
    for k, v in (props or {}).items():
        if k not in PROP_KEYS or v is None:
            continue
        if isinstance(v, bool) or isinstance(v, int):
            out[k] = v
        elif k == "label":
            label = " ".join(_LABEL.sub(" ", str(v)).split())[:_LABEL_MAX]
            if label:
                out[k] = label
        elif _clean(v):
            out[k] = _clean(v)
    return out or None


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


def record(event: str, *, visitor_id=None, session_id=None, source=None, campaign=None, template_id=None,
           props: Optional[dict] = None) -> bool:
    """이벤트 한 건을 남긴다. 요청 트랜잭션 안이면 그 트랜잭션에 합류한다. 알 수 없는 이벤트는 버린다."""
    if event not in CLIENT_EVENTS and event not in SERVER_EVENTS:
        return False
    row = FunnelEventRow(
        event=event, visitor_id=_clean(visitor_id), session_id=_clean(session_id),
        source=_clean(source), campaign=_clean(campaign), template_id=_clean(template_id), props=_props(props),
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
