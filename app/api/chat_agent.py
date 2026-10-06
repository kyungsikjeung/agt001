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


# 사장님 답 받아 가기(4초마다)는 따로 센다: 10분 150번이 보통이라 넉넉히 300번
POLL_LIMIT = 300
# 즉시 반영 연결 열기(§7): 연결 하나가 5분이라 10분에 몇 번이면 된다. 끊겨 다시 붙는 것까지 넉넉히
STREAM_LIMIT = 60


def _allow(key: str, limit: int = RATE_LIMIT) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= limit:
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
    out = chat_agent.respond(key, token, text=body.text, action=body.action)
    # AI가 답한 건만 센다(사장님 대기 중인 글은 AI를 거치지 않는다). 포함량은 요금제에서(D61).
    # 넘어도 막지 않는다 — 안내와 지불 의사 신호만 남긴다(D40).
    if isinstance(out, dict) and out.get("reply") and out.get("mode") != "owner":
        from app.services import usage
        usage.safe_use(key, "chat_ai")
    return out


@router.get("/api/chat/{site_key}/stream")
def chat_stream(site_key: str, request: Request, after: int = 0):
    """손님 화면 즉시 반영 (GUEST_CHAT_CONTRACT §7): 이 브라우저 쿠키 대화의 새 글·상태를 SSE로 보낸다."""
    from app.services import guest_chat, sse
    key = sanitize_token(site_key or "")
    if not key:
        raise HTTPException(status_code=404)
    if not _allow("stream:" + (request.client.host if request.client else "?"), STREAM_LIMIT):
        raise HTTPException(status_code=429, detail="잠시 뒤에 다시 보내 주세요.")
    token = request.cookies.get(cookie_name(key))
    th = chat_agent.token_hash(token) if token and len(token) <= 100 else None
    state = {"after": max(0, int(after or 0), sse.last_event_id(request)), "status": None}

    def step():
        data = guest_chat.messages_after(key, th, state["after"])
        out = []
        for m in data["messages"]:
            out.append(sse.event("message", m, m["id"]))
            state["after"] = m["id"]
        if data["status"] != state["status"]:
            state["status"] = data["status"]
            out.append(sse.event("status", {"status": data["status"]}))
        return out, data["status"] in guest_chat.CLOSED_STATES

    return sse.response(request, step)


@router.get("/api/chat/{site_key}/messages")
def chat_messages(site_key: str, request: Request, after: int = 0):
    """손님 화면이 사장님 답을 받아 간다 (GUEST_CHAT_CONTRACT §2-5). 이 브라우저 쿠키의 대화만."""
    from app.services import guest_chat
    key = sanitize_token(site_key or "")
    if not key:
        raise HTTPException(status_code=404)
    if not _allow("poll:" + (request.client.host if request.client else "?"), POLL_LIMIT):
        raise HTTPException(status_code=429, detail="잠시 뒤에 다시 보내 주세요.")
    token = request.cookies.get(cookie_name(key))
    th = chat_agent.token_hash(token) if token and len(token) <= 100 else None
    return guest_chat.messages_after(key, th, max(0, int(after or 0)))
