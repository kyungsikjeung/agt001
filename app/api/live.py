"""실시간 대화·미리보기 (COMPOSE_INTERVIEW_CONTRACT §4).

POST /api/rooms/{room_id}/live/turn   {"text": "..."}  방장만. 빈 글이면 지금 질문만 돌려준다.
GET  /api/rooms/{room_id}/live/preview                 확정된 부품으로 그린 미리보기 HTML.

대화는 채팅방 기록에도 그대로 남는다(사장님 말·AI 답). 부품을 다 정하고 엔진 질문까지 끝나면
기존 요약·승인 흐름(chat_flow)으로 넘겨, 채팅방에서 시안 3안·공개로 이어 간다.
"""
import gzip
import json
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from app import store
from app.security import sanitize_token
from app.services import chat_flow, compose, prd_engine, rooms

router = APIRouter()

MAX_TEXT = 500
DONE_NOTE = "필요한 내용은 다 모았어요. 채팅방에서 요약을 확인하고 시안을 받아 보세요."


class LiveIn(BaseModel):
    text: Optional[str] = ""


def _owner_room(room_id: str, member_id_raw: Optional[str]) -> tuple[str, str]:
    safe = sanitize_token(room_id or "")
    member_id = sanitize_token(member_id_raw or "")
    room = store.read_room(safe) if safe else None
    if room is None:
        raise HTTPException(status_code=404, detail="room not found")
    if not member_id or rooms.owner_id(room) != member_id:
        raise HTTPException(status_code=403, detail="owner only")
    return safe, member_id


def _json(request: Request, content: dict) -> Response:
    """미리보기·시안 HTML은 크고(선택지마다 CSS 포함) 잘 줄어서 gzip으로 보낸다. 전역 압축은 SSE 때문에 켜지 않는다."""
    body = json.dumps(content, ensure_ascii=False).encode("utf-8")
    headers = {"Cache-Control": "no-store", "Vary": "Accept-Encoding"}
    if "gzip" in (request.headers.get("accept-encoding") or "") and len(body) > 2048:
        body = gzip.compress(body, compresslevel=6)
        headers["Content-Encoding"] = "gzip"
    return Response(content=body, media_type="application/json", headers=headers)


def _view(card: dict, out: dict) -> dict:
    q = out.get("question")
    return {
        "reply": out.get("reply") or "",
        "question": compose.format_text(q) if q else "",
        "question_text": (q or {}).get("text", ""),
        "speech": " ".join(x for x in (out.get("reply") or "", compose.speech_text(q)) if x).strip(),
        "options": [o for o in (q or {}).get("options") or [] if o],
        "option_desc": list((q or {}).get("option_desc") or []),
        "speech_parts": ([out["reply"]] if out.get("reply") else []) + list((q or {}).get("speech_parts") or []),
        "has_previews": (q or {}).get("kind") == "compose",
        "phase": out.get("phase"),
        "done": bool(out.get("done")),
        "last": out.get("last"),
        "components": compose.components(card),
    }


@router.post("/api/rooms/{room_id}/live/turn")
def live_turn(room_id: str, body: LiveIn, x_member_id: Optional[str] = Header(default=None)):
    safe, member_id = _owner_room(room_id, x_member_id)
    text = (body.text or "").strip()[:MAX_TEXT]
    with store.room_tx(safe) as (room, session):
        if room is None or session is None:
            raise HTTPException(status_code=404, detail="room not found")
        if session.get("state") not in ("GREETING", "GATHERING"):
            raise HTTPException(status_code=409, detail="interview finished")
        card = session.get("prd")
        if card is None:
            card = prd_engine.new_card()
            session["prd"] = card
        session["state"] = "GATHERING"
        nickname = next((m["nickname"] for m in room["members"] if m["member_id"] == member_id), "사장님")
        if not text:
            # 처음 열었거나 다시 들어온 경우: 지금 물을 것만 보여 준다 (대화를 진전시키지 않는다).
            q = compose.pending_question(card)
            out = {"question": q, "phase": "compose"} if q else compose.next_step(card)
            return _view(card, out)
        rooms._append(room, member_id, nickname, text, kind="chat", meta={"live": True})
        out = compose.live_turn(card, text, by=rooms.member_handle(safe, member_id), is_owner=True)
        if out.get("done"):
            summary = chat_flow._gate_or_summary(session, card, room, None)
            out["reply"] = "\n\n".join(x for x in (out.get("reply"), summary) if x)
            if session.get("state") == "AWAIT_APPROVAL":
                out["reply"] += "\n\n" + DONE_NOTE
            else:
                out["done"] = False  # 게이트가 확인 질문을 냈다
                out["question"] = card.get("pending")
        view = _view(card, out)
        ai_text = "\n\n".join(x for x in (view["reply"], view["question"]) if x)
        if ai_text:
            rooms._append(room, "ai", "AI 어시스턴트", ai_text, kind="ai_reply", meta={"live": True})
        return view


@router.get("/api/rooms/{room_id}/live/preview")
def live_preview(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    safe, _member_id = _owner_room(room_id, x_member_id)
    room = store.read_room(safe)
    session = store.read_session(room["session_id"]) or {}
    card = session.get("prd") or prd_engine.new_card()
    html = compose.preview_html(card, site_key=session.get("requirement_id") or "")
    st = compose.state(card)
    return _json(request, {"html": html, "components": compose.components(card),
                           "tone": st.get("tone"), "last": (st.get("order") or [None])[-1]})


@router.get("/api/rooms/{room_id}/live/options")
def live_options(room_id: str, request: Request, x_member_id: Optional[str] = Header(default=None)):
    """지금 질문의 선택지별 작은 시안 (지금 분위기 토큰으로 그린 부품 하나씩)."""
    safe, _member_id = _owner_room(room_id, x_member_id)
    room = store.read_room(safe)
    session = store.read_session(room["session_id"]) or {}
    card = session.get("prd") or prd_engine.new_card()
    st = compose.state(card)
    return _json(request, {"component": st.get("pending"), "options": compose.option_previews(card)})
