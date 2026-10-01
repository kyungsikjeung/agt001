"""SSE(서버가 바로 밀어 주기) 공용 도구 (GUEST_CHAT_CONTRACT §7).

연결마다 POLL_SEC마다 DB를 보고(step은 스레드에서) 바뀐 것만 보낸다. 서버 프로세스가 여럿이어도 된다.
연결 하나는 MAX_SEC까지만 열고 닫는다. 브라우저 EventSource가 RETRY_MS 뒤 다시 붙으며 그때 권한도 다시 본다.
보낼 것이 없으면 PING_SEC마다 주석 한 줄을 보내 프록시가 연결을 끊지 않게 한다.
"""
import asyncio
import json
import time
from typing import Callable, Optional

from fastapi import Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

POLL_SEC = 1.0
MAX_SEC = 300.0
PING_SEC = 15.0
RETRY_MS = 2000


def event(name: str, data, event_id: Optional[int] = None) -> str:
    out = f"event: {name}\n"
    if event_id is not None:
        out += f"id: {event_id}\n"
    return out + "data: " + json.dumps(data, ensure_ascii=False, default=str) + "\n\n"


def last_event_id(request: Request) -> int:
    """브라우저가 다시 붙을 때 보내는 마지막 id (없거나 이상하면 0)."""
    raw = (request.headers.get("last-event-id") or "").strip()
    return int(raw) if raw.isdigit() and len(raw) < 18 else 0


def response(request: Request, step: Callable[[], tuple]) -> StreamingResponse:
    """step() → (보낼 글 목록, 끝낼지). step은 스레드에서 돈다(DB 읽기)."""

    async def stream():
        yield f"retry: {RETRY_MS}\n\n"
        start = last_sent = time.monotonic()
        while time.monotonic() - start < MAX_SEC:
            if await request.is_disconnected():
                return
            chunks, done = await run_in_threadpool(step)
            for chunk in chunks:
                yield chunk
            if done:
                return
            now = time.monotonic()
            if chunks:
                last_sent = now
            elif now - last_sent >= PING_SEC:
                yield ": ping\n\n"
                last_sent = now
            await asyncio.sleep(POLL_SEC)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
