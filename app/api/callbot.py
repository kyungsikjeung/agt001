"""음성 콜봇 PoC — 브라우저로 AI와 통화하며 요구사항 답하기 (VOICE_QA_REQUIREMENTS §8).

1. 방장이 통화권을 받는다: 참여자가 나 혼자(1:1)이고 요구사항 대화 중일 때만.
2. 브라우저(Twilio Voice SDK)가 전화를 건다. 휴대폰 번호·통화료가 필요 없다.
3. Twilio가 /twiml을 물어오면 서명을 확인하고 ConversationRelay(한국어 받아쓰기·읽기)로 잇는다.
4. Twilio가 받아쓴 말을 /ws로 보내면 채팅방에 방장 말로 넣고, AI 답장을 읽을 말로 돌려준다.
   전화로 한 말과 답은 채팅에도 그대로 남는다.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from html import escape
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from app import store
from app.config import settings
from app.security import sanitize_token
from app.services import rooms, voice_turn

log = logging.getLogger(__name__)
router = APIRouter()

TICKET_TTL = 600  # 통화권 10분 (체험 계정 통화 상한과 같다)
CALL_STATES = ("GREETING", "GATHERING")  # 요구사항 대화 중
# 한국어: Twilio 문서의 ko-KR 기본 조합 (ElevenLabs 읽기 + Google 받아쓰기)
RELAY_VOICE = ('language="ko-KR" ttsProvider="ElevenLabs" voice="uyVNoMrnUku1dZyVEXwD" '
               'transcriptionProvider="Google" speechModel="telephony"')
MSG_GROUP = "다른 분이 들어오셔서 전화를 마칠게요. 채팅에서 이어 주세요."
MSG_WAIT = "네, 잠시만요."

# ponytail: 통화권은 메모리 표 — 백엔드 워커 1개 기준. 워커를 늘리면 DB 표로.
_tickets: dict[str, tuple[str, str, float]] = {}
_lock = threading.Lock()


def configured() -> bool:
    return all((settings.twilio_account_sid, settings.twilio_auth_token, settings.twilio_api_key_sid,
                settings.twilio_api_key_secret, settings.twilio_twiml_app_sid))


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def access_token(identity: str, now: Optional[int] = None) -> str:
    """Twilio Voice SDK 통화권(JWT HS256). 나가는 통화만, 우리 TwiML 앱으로만 걸 수 있다."""
    now = int(time.time()) if now is None else now
    header = {"typ": "JWT", "alg": "HS256", "cty": "twilio-fpa;v=1"}
    payload = {
        "jti": f"{settings.twilio_api_key_sid}-{now}",
        "iss": settings.twilio_api_key_sid,
        "sub": settings.twilio_account_sid,
        "iat": now,
        "exp": now + TICKET_TTL,
        "grants": {"identity": identity,
                   "voice": {"outgoing": {"application_sid": settings.twilio_twiml_app_sid}}},
    }
    signing = ".".join(_b64(json.dumps(p, separators=(",", ":")).encode()) for p in (header, payload))
    sig = hmac.new(settings.twilio_api_key_secret.encode(), signing.encode(), hashlib.sha256).digest()
    return f"{signing}.{_b64(sig)}"


def valid_signature(url: str, params: dict, signature: str) -> bool:
    """Twilio 요청 서명: 주소 + (이름·값을 이름순으로 이어 붙임)의 HMAC-SHA1."""
    data = url + "".join(k + params[k] for k in sorted(params))
    expected = base64.b64encode(hmac.new(settings.twilio_auth_token.encode(), data.encode(), hashlib.sha1).digest())
    return hmac.compare_digest(expected.decode(), signature or "")


def _ticket(ticket: str) -> Optional[tuple[str, str]]:
    now = time.time()
    with _lock:
        for k in [k for k, v in _tickets.items() if v[2] < now]:
            del _tickets[k]
        hit = _tickets.get(ticket)
    return (hit[0], hit[1]) if hit else None


def _refusal(room: Optional[dict], session: dict, member_id: str) -> Optional[str]:
    """통화할 수 없는 이유. 되면 None. 화면만 믿지 않고 서버가 같은 규칙을 강제한다(§8.2)."""
    if room is None or not any(m["member_id"] == member_id for m in room["members"]):
        return "not_found"
    if rooms.owner_id(room) != member_id:
        return "owner_only"
    if len(room["members"]) != 1:
        return "one_to_one_only"
    if session.get("state") not in CALL_STATES:
        return "not_gathering"
    return None


def _load(room_id: str) -> tuple[Optional[dict], dict]:
    room = store.read_room(room_id)
    session = (store.read_session(room["session_id"]) if room else None) or {}
    return room, session


@router.post("/api/callbot/token/{room_id}")
def callbot_token(room_id: str, x_member_id: Optional[str] = Header(default=None)):
    if not configured():
        raise HTTPException(status_code=503, detail="callbot off")
    safe_id, member_id = sanitize_token(room_id), sanitize_token(x_member_id or "")
    reason = _refusal(*_load(safe_id), member_id)
    if reason:
        raise HTTPException(status_code=404 if reason == "not_found" else 403, detail=reason)
    ticket = secrets.token_hex(16)
    with _lock:
        _tickets[ticket] = (safe_id, member_id, time.time() + TICKET_TTL)
    return {"token": access_token(ticket), "ttl": TICKET_TTL}


def _last_ai(msgs: list[dict]) -> str:
    return next((m["text"] for m in reversed(msgs) if m.get("kind") == "ai_reply"), "")


def _greeting(room_id: str) -> str:
    """전화 첫마디: 채팅에서 마지막으로 물은 말을 이어서 읽는다."""
    last = _last_ai(store.read_messages(room_id, 0))  # ponytail: 방 기록 전체 읽기, 길어지면 최근 N개만
    ask = voice_turn.speech_text(last)[:400] or "어떤 가게 사이트를 만들까요?"
    return f"안녕하세요, 한마디 AI예요. 답하신 내용은 채팅에도 남아요. {ask}"


def _xml(body: str) -> Response:
    return Response(f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>', media_type="text/xml")


@router.post("/api/callbot/twiml")
async def callbot_twiml(request: Request):
    if not configured():
        raise HTTPException(status_code=503, detail="callbot off")
    params = {k: str(v) for k, v in (await request.form()).items()}
    if not valid_signature(str(request.url), params, request.headers.get("x-twilio-signature", "")):
        log.warning("callbot: 서명 불일치 url=%s", request.url)
        raise HTTPException(status_code=403, detail="bad signature")
    ticket = params.get("From", "").removeprefix("client:")
    hit = _ticket(ticket)
    if not hit:
        return _xml("<Say language=\"ko-KR\">통화권이 만료됐어요. 채팅방에서 다시 눌러 주세요.</Say><Hangup/>")
    room, session = _load(hit[0])
    if _refusal(room, session, hit[1]):
        return _xml("<Say language=\"ko-KR\">지금은 전화로 답할 수 없어요. 채팅에서 이어 주세요.</Say><Hangup/>")
    ws_url = f"wss://{request.url.netloc}/api/callbot/ws"
    return _xml(
        f'<Connect><ConversationRelay url="{escape(ws_url)}" welcomeGreeting="{escape(_greeting(hit[0]))}" '
        f'{RELAY_VOICE}><Parameter name="ticket" value="{escape(ticket)}"/></ConversationRelay></Connect>'
    )


def _turn(room_id: str, member_id: str, said: str, base_url: str) -> tuple[str, bool]:
    """받아쓴 말 한 번 → (읽을 답, 계속 통화할지). 채팅에 쓴 것과 똑같이 엔진에 넣는다."""
    room, session = _load(room_id)
    reason = _refusal(room, session, member_id)
    if reason == "one_to_one_only":
        return MSG_GROUP, False
    if reason:
        return "요구사항 대화가 끝났어요. 이어지는 건 채팅에서 확인해 주세요.", False
    nickname = room["members"][0]["nickname"]
    seen = store.read_messages(room_id, 0)
    rooms.post_message(room_id, member_id, nickname, said, base_url)
    reply = _last_ai(store.read_messages(room_id, seen[-1]["seq"] + 1 if seen else 0))
    _, session = _load(room_id)
    if session.get("state") not in CALL_STATES:
        return (voice_turn.speech_text(reply) + " 요약은 채팅에 남겼어요. 전화를 마칠게요.").strip(), False
    return voice_turn.speech_text(reply) or "잘 들었어요.", True


@router.websocket("/api/callbot/ws")
async def callbot_ws(ws: WebSocket):
    await ws.accept()
    hit = None
    base_url = f"https://{ws.url.netloc}/"

    async def say(text: str, end: bool = False):
        await ws.send_text(json.dumps({"type": "text", "token": text, "last": True}, ensure_ascii=False))
        if end:
            # ponytail: 읽기가 끝났다는 신호가 없어 글자 수로 기다린 뒤 끊는다(초당 약 6자). 잘리면 늘린다.
            await asyncio.sleep(min(len(text) / 6 + 1, 20))
            await ws.send_text(json.dumps({"type": "end"}))

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            kind = msg.get("type")
            if kind == "setup":
                hit = _ticket(str((msg.get("customParameters") or {}).get("ticket", "")))
                if not hit:
                    await ws.close()
                    return
            elif kind == "prompt" and hit and msg.get("last", True):
                said = (msg.get("voicePrompt") or "").strip()
                if not said:
                    continue
                await say(MSG_WAIT)
                try:
                    reply, keep = await run_in_threadpool(_turn, hit[0], hit[1], said, base_url)
                except Exception:
                    log.exception("callbot turn")
                    reply, keep = "잠깐 문제가 생겼어요. 채팅에서 이어 주세요.", False
                await say(reply, end=not keep)
            elif kind == "error":
                log.warning("callbot relay error: %s", msg.get("description"))
    except WebSocketDisconnect:
        pass
