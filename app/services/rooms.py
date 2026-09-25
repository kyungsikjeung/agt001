"""다인원 공유방 (MULTIUSER_CHAT_DESIGN.md §3, §4).

방은 session_id로 기존 세션을 가리키기만 한다. 상태머신은 chat_flow를 그대로 재사용한다.
"""
import datetime
import html
import uuid

from app import store
from app.security import sanitize_token
from app.services import chat_flow

MAX_MESSAGE_LEN = 2000
MAX_NICKNAME_LEN = 40
VOTE_WORDS = ("승인", "거절", "네", "아니오", "yes", "no")
VOTE_APPROVE_WORDS = ("승인", "네", "yes")


class RoomNotFound(Exception):
    pass


class InvalidRequest(Exception):
    pass


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append(room: dict, member_id: str, nickname: str, text: str, kind: str = "chat") -> None:
    room["messages"].append({
        "seq": len(room["messages"]),
        "member_id": member_id,
        "nickname": nickname,
        "text": text,
        "ts": _now_iso(),
        "kind": kind,
    })


def _get_room(room_id: str) -> dict:
    safe_id = sanitize_token(room_id)
    room = store.rooms.get(safe_id) if safe_id else None
    if room is None:
        raise RoomNotFound(room_id)
    return room


def create_room() -> str:
    room_id = str(uuid.uuid4())[:8]
    session_id = str(uuid.uuid4())
    store.sessions.setdefault(session_id, chat_flow.new_session())
    store.rooms.set(room_id, {
        "room_id": room_id,
        "session_id": session_id,
        "created_at": _now_iso(),
        "members": [],
        "messages": [],
        "ai_status": "IDLE",
        "votes": {},
    })
    store.rooms.save()
    store.sessions.save()
    return room_id


def tally(votes: dict) -> tuple[int, int]:
    approve_n = sum(1 for v in votes.values() if v == "approve")
    reject_n = sum(1 for v in votes.values() if v == "reject")
    return approve_n, reject_n


def post_message(room_id: str, member_id_raw, nickname_raw, message_raw, base_url: str) -> dict:
    room = _get_room(room_id)
    member_id = sanitize_token(member_id_raw or "")
    if not member_id:
        raise InvalidRequest("member_id required")
    nickname = html.escape((nickname_raw or "익명")[:MAX_NICKNAME_LEN])
    user_text = (message_raw or "").strip()[:MAX_MESSAGE_LEN]

    session = store.sessions.get(room["session_id"])
    if session is None:
        raise RoomNotFound(room_id)

    now = _now_iso()
    existing = next((m for m in room["members"] if m["member_id"] == member_id), None)
    if existing is None:
        room["members"].append({"member_id": member_id, "nickname": nickname, "joined_at": now, "last_seen": now})
        _append(room, "system", "시스템", f"{nickname}님이 입장했습니다.", kind="system")
    else:
        existing["last_seen"] = now
        existing["nickname"] = nickname

    if not user_text:
        store.rooms.save()
        return {"ai_status": room["ai_status"]}

    _append(room, member_id, nickname, user_text, kind="chat")

    # 승인 게이트는 과반 투표. 동점·미달이면 투표만 기록하고 AI는 호출하지 않는다.
    if session["state"] == "AWAIT_APPROVAL" and user_text in VOTE_WORDS:
        vote = "approve" if user_text in VOTE_APPROVE_WORDS else "reject"
        room["votes"][member_id] = vote
        total = len(room["members"])
        approve_n, reject_n = tally(room["votes"])
        _append(
            room, "system", "시스템",
            f"{nickname}님이 {'승인' if vote == 'approve' else '거절'}했습니다 "
            f"(찬성 {approve_n}/{total}, 반대 {reject_n}/{total})",
            kind="vote",
        )
        decision = "승인" if approve_n > total / 2 else "거절" if reject_n > total / 2 else None
        if decision:
            reply = chat_flow.process_turn(room["session_id"], session, decision, base_url, room=room)
            _append(room, "ai", "AI 어시스턴트", reply, kind="ai_reply")
            room["votes"] = {}
    else:
        reply = chat_flow.process_turn(room["session_id"], session, user_text, base_url, room=room)
        _append(room, "ai", "AI 어시스턴트", reply, kind="ai_reply")

    store.rooms.save()
    store.sessions.save()
    return {"ai_status": room["ai_status"]}


def get_messages(room_id: str, since: int, base_url: str) -> dict:
    """참여자들이 4초마다 부르는 조회. 조회가 GET이라 GENERATING 완료를 확인할 트리거가
    따로 없으므로 여기서 상태머신을 한 번 돌려 완료 전이를 일으킨다."""
    room = _get_room(room_id)
    session = store.sessions.get(room["session_id"], {})
    if session.get("state") == "GENERATING":
        reply = chat_flow.process_turn(room["session_id"], session, "", base_url, room=room)
        if session.get("state") != "GENERATING":
            _append(room, "ai", "AI 어시스턴트", reply, kind="ai_reply")
            store.rooms.save()
            store.sessions.save()
    return {
        "messages": room["messages"][since:],
        "ai_status": room["ai_status"],
        "members": room["members"],
        "votes": room["votes"],
        "state": session.get("state"),
        "deploy_url": session.get("deploy_url"),
        "design_url": session.get("design_url"),
        "design_preview_url": session.get("design_preview_url"),
    }
