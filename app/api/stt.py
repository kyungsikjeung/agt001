import threading
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile

from app.security import sanitize_token
from app.services import stt

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


@router.post("/api/stt")
def speech_to_text(request: Request, audio: UploadFile = File(...), x_member_id: Optional[str] = Header(default=None)):
    """녹음 → 글자. 글자는 입력창에 넣기만 하고 사장님이 고친 뒤 보낸다 (static/voice.js)."""
    if not sanitize_token(x_member_id or ""):
        raise HTTPException(status_code=400, detail="member required")
    if not _allow(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="too many requests")
    ctype = (audio.content_type or "").split(";")[0].strip().lower()
    if ctype not in stt.ALLOWED_TYPES:
        raise HTTPException(status_code=415, detail="unsupported audio type")
    data = audio.file.read(stt.MAX_BYTES + 1)
    if len(data) > stt.MAX_BYTES:
        raise HTTPException(status_code=413, detail="audio too large")
    if not data:
        raise HTTPException(status_code=400, detail="empty audio")
    try:
        text = stt.transcribe(data)
    except stt.BadAudio:
        raise HTTPException(status_code=400, detail="bad audio")
    except stt.SttUnavailable:
        raise HTTPException(status_code=503, detail="speech recognition unavailable")
    finally:
        del data  # 녹음은 저장하지 않는다
    return {"text": text}
