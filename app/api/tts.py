import threading
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel

from app.security import sanitize_token
from app.services import tts, voice_turn

router = APIRouter()

# IP당 분당 호출 상한. 음성 합성은 외부 API 호출이라 남용을 막는다. IP는 메모리에서만 쓴다.
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


class TtsBody(BaseModel):
    text: Optional[str] = None


@router.post("/api/tts")
def text_to_speech(request: Request, body: TtsBody, x_member_id: Optional[str] = Header(default=None)):
    """글자 → 음성. AI 답장을 읽어주는 선택 버튼용이다. 자동 재생하지 않는다 (static/voice.js)."""
    if not sanitize_token(x_member_id or ""):
        raise HTTPException(status_code=400, detail="member required")
    if not _allow(request.client.host if request.client else "unknown"):
        raise HTTPException(status_code=429, detail="too many requests")
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    # 화면용 안내·기호는 빼고 읽을 말만 (FR-1). 안내뿐인 조각("(질문 3/8 …)")은 읽지 않는다.
    text = voice_turn.speech_text(text)[: tts.MAX_CHARS]  # 300자가 넘으면 앞에서 자른다
    if not text:
        raise HTTPException(status_code=400, detail="empty text")
    try:
        wav = tts.synthesize(text)
    except tts.TtsUnavailable:
        raise HTTPException(status_code=503, detail="speech synthesis unavailable")
    except tts.TtsUpstream:
        raise HTTPException(status_code=502, detail="speech synthesis failed")
    return Response(content=wav, media_type="audio/wav", headers={"Cache-Control": "no-store"})
