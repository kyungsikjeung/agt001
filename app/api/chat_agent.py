"""손님 예약 채팅 API (BOOKING_BOT_IMPL_PLAN CH-1·CH-2·CH-5·CH-7).

- GET /chat/{site_key}: 채팅 페이지(우리 도메인). 생성 사이트는 스크립트가 없어 여기로 링크한다.
- POST /api/chat/{site_key} {text?, action?} → {reply, buttons}. 이 브라우저 토큰은 가게별 HttpOnly 쿠키.
"""
import secrets
import threading
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.auth import _check_origin
from app.config import settings
from app.security import sanitize_token
from app.services import chat_agent

router = APIRouter()

COOKIE_DAYS = 90
RATE_LIMIT, RATE_WINDOW = 60, 600
_hits: dict[str, deque] = {}
_lock = threading.Lock()


def _allow(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        return True


def cookie_name(site_key: str) -> str:
    return f"agt_chat_{site_key[:40]}"


class ChatIn(BaseModel):
    text: Optional[str] = Field(default=None, max_length=300)
    action: Optional[str] = Field(default=None, max_length=80)


@router.get("/chat/{site_key}", include_in_schema=False)
def chat_page(site_key: str):
    if not sanitize_token(site_key):
        raise HTTPException(status_code=404)
    return FileResponse(settings.static_dir / "chat.html")


@router.post("/api/chat/{site_key}")
def chat(site_key: str, body: ChatIn, request: Request, response: Response):
    _check_origin(request)
    key = sanitize_token(site_key or "")
    if not key:
        raise HTTPException(status_code=404)
    if not _allow(request.client.host if request.client else "?"):
        raise HTTPException(status_code=429, detail="잠시 뒤에 다시 보내 주세요.")
    name = cookie_name(key)
    token = request.cookies.get(name)
    if not token or len(token) > 100:
        token = secrets.token_urlsafe(24)
    response.set_cookie(name, token, max_age=COOKIE_DAYS * 86400, path="/", secure=True, httponly=True,
                        samesite="lax")
    return chat_agent.respond(key, token, text=body.text, action=body.action)
