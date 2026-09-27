import threading
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from app.security import sanitize_token
from app.services import funnel, stt

router = APIRouter()

# IP당 분당 호출 상한. 음성 인식은 외부 API 호출이라 남용을 막는다. IP는 메모리에서만 쓴다.
RATE_LIMIT_PER_MIN = 12
_hits: dict[str, deque] = {}
_lock = threading.Lock()


def _allow(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT_PER_MIN:
            return False
        q.append(now)
        return True


# 음성 인식 카운터(전사 원문·IP 저장 없음, D16). 실패 사유·숫자 포함 여부만 센다.
def _count_ok(has_number: int) -> None:
    try:
        funnel.record("voice_stt_ok", props={"has_number": 1 if has_number else 0})
    except Exception:
        pass  # 카운터 실패가 음성 입력을 막지 않는다


def _count_fail(reason: str) -> None:
    try:
        funnel.record("voice_stt_fail", props={"reason": reason})
    except Exception:
        pass  # 카운터 실패가 음성 입력을 막지 않는다


@router.post("/api/stt")
def speech_to_text(request: Request, audio: UploadFile = File(...), x_member_id: Optional[str] = Header(default=None)):
    """녹음 → 글자. 글자는 입력창에 넣기만 하고 사장님이 고친 뒤 보낸다 (static/voice.js)."""
    if not sanitize_token(x_member_id or ""):
        _count_fail("bad_audio")  # 토큰 없음도 요청 오류로만 센다(원문·IP 없음)
        raise HTTPException(status_code=400, detail="member required")
    if not _allow(request.client.host if request.client else "unknown"):
        _count_fail("rate_limited")
        raise HTTPException(status_code=429, detail="too many requests")
    ctype = (audio.content_type or "").split(";")[0].strip().lower()
    if ctype not in stt.ALLOWED_TYPES:
        _count_fail("unsupported")
        raise HTTPException(status_code=415, detail="unsupported audio type")
    data = audio.file.read(stt.MAX_BYTES + 1)
    if len(data) > stt.MAX_BYTES:
        raise HTTPException(status_code=413, detail="audio too large")
    if not data:
        _count_fail("empty")
        raise HTTPException(status_code=400, detail="empty audio")
    try:
        text = stt.transcribe(data)
    except stt.BadAudio:
        _count_fail("bad_audio")
        raise HTTPException(status_code=400, detail="bad audio")
    except stt.SttUnavailable:
        _count_fail("unavailable")
        raise HTTPException(status_code=503, detail="speech recognition unavailable")
    finally:
        del data  # 녹음은 저장하지 않는다
    _count_ok(1 if any(ch.isdigit() for ch in text) else 0)  # 성공은 숫자 포함 여부만
    return {"text": text}
