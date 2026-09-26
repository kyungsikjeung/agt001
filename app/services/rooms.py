"""다인원 공유방 (MULTIUSER_CHAT_DESIGN.md §3, §4).

방은 session_id로 기존 세션을 가리키기만 한다. 상태머신은 chat_flow를 그대로 재사용한다.
"""
import datetime
import hashlib
import html
import uuid
from typing import Optional

from app import store
from app.config import settings
from app.security import sanitize_token
from app.services import chat_flow

MAX_MESSAGE_LEN = 2000
MAX_NICKNAME_LEN = 40
# 서버가 쓰는 발신자 ID. 사람의 member_id와 달리 비밀이 아니므로 그대로 내보낸다.
_SERVER_SENDERS = ("system", "ai")


class RoomNotFound(Exception):
    pass


class InvalidRequest(Exception):
    pass


class RoomFull(Exception):
    pass


class RoomClosed(Exception):
    pass


# 타이머가 남기는 시스템 메시지 (ROOM_POLICY §4.2). 같은 글이 마지막이면 다시 남기지 않는다.
MSG_VOTE_RESET = "투표가 24시간 동안 끝나지 않아 초기화됐습니다. 다시 '승인' 또는 '거절'을 보내 주세요"
MSG_QUOTE_EXPIRED = "견적 유효기간(7일)이 지났습니다. 요구사항이 바뀌지 않았다면 '다시 견적'을 보내 주세요"
MSG_CLOSED = "30일 동안 활동이 없어 방이 닫혔습니다. 방장이 메시지를 보내면 다시 열립니다"
MSG_REOPENED = "방장이 방을 다시 열었습니다."


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _idle(room_id: str, room: dict) -> tuple[Optional[datetime.timedelta], Optional[str]]:
    last_act, last_text = room.get("activity") or store.activity_info(room_id)
    if last_act is None:
        created = room.get("created_at")
        last_act = datetime.datetime.fromisoformat(created) if isinstance(created, str) else created
    return ((_utcnow() - last_act) if last_act else None), last_text


def _due_timers(session: dict, idle: Optional[datetime.timedelta], last_text: Optional[str]) -> list[str]:
    """지금 실행할 타이머 (T1·T2·T4/T5). 제작 중은 건드리지 않는다."""
    if idle is None or session.get("state") == "GENERATING":
        return []
    due = []
    if idle >= datetime.timedelta(days=settings.room_close_days) and last_text != MSG_CLOSED:
        due.append("close")
    elif session.get("state") == "AWAIT_APPROVAL" and idle >= datetime.timedelta(hours=settings.room_vote_reset_hours) \
            and last_text != MSG_VOTE_RESET:
        due.append("vote_reset")
    elif session.get("state") == "QUOTED" and idle >= datetime.timedelta(days=settings.room_quote_expire_days) \
            and last_text != MSG_QUOTE_EXPIRED:
        due.append("quote_expire")
    return due


def _run_timers(room: dict, session: dict, due: list[str]) -> None:
    for t in due:
        if t == "vote_reset":
            room["votes"] = {}
            _append(room, "system", "시스템", MSG_VOTE_RESET, kind="system")
        elif t == "quote_expire":
            session["quote"] = None
            session["state"] = "GATHERING"
            _append(room, "system", "시스템", MSG_QUOTE_EXPIRED, kind="system")
        elif t == "close":
            _append(room, "system", "시스템", MSG_CLOSED, kind="system")


def _is_closed(session: dict, idle: Optional[datetime.timedelta], last_text: Optional[str]) -> bool:
    if session.get("state") == "GENERATING":
        return False
    return last_text == MSG_CLOSED or (idle is not None and idle >= datetime.timedelta(days=settings.room_close_days))


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append(room: dict, member_id: str, nickname: str, text: str, kind: str = "chat") -> None:
    room["new_messages"].append({
        "seq": room["next_seq"],
        "member_id": member_id,
        "nickname": nickname,
        "text": text,
        "ts": _now_iso(),
        "kind": kind,
    })
    room["next_seq"] += 1


def member_handle(room_id: str, member_id: str) -> str:
    """응답에 내보내는 공개 식별자 (ROOM_POLICY.md §1 R-0).

    member_id는 본인 확인용 비밀값(브라우저에만 저장)이라 응답에 담으면 같은 방 참여자가 남의
    이름으로 투표할 수 있다. 무작위 UUID의 해시라 공개 식별자에서 원래 값을 알아낼 수 없다.
    """
    if member_id in _SERVER_SENDERS:
        return member_id
    return hashlib.sha256(f"{room_id}:{member_id}".encode()).hexdigest()[:12]


def _public_message(room_id: str, msg: dict) -> dict:
    out = {k: v for k, v in msg.items() if k != "member_id"}
    out["member_handle"] = member_handle(room_id, msg["member_id"])
    return out


def _room_id(room_id: str) -> str:
    safe_id = sanitize_token(room_id)
    if not safe_id:
        raise RoomNotFound(room_id)
    return safe_id


def create_room(template_id: Optional[str] = None) -> str:
    room_id = str(uuid.uuid4())[:8]
    session_id = str(uuid.uuid4())
    store.create_room(room_id, session_id, chat_flow.new_session(sanitize_token(template_id or "") or None))
    return room_id


def tally(votes: dict) -> tuple[int, int]:
    approve_n = sum(1 for v in votes.values() if v == "approve")
    reject_n = sum(1 for v in votes.values() if v == "reject")
    return approve_n, reject_n


def post_message(room_id: str, member_id_raw, nickname_raw, message_raw, base_url: str) -> dict:
    safe_id = _room_id(room_id)
    member_id = sanitize_token(member_id_raw or "")
    nickname = html.escape((nickname_raw or "익명")[:MAX_NICKNAME_LEN])
    user_text = (message_raw or "").strip()[:MAX_MESSAGE_LEN]

    # 방 잠금 안에서 처리한다: 같은 방의 요청은 순서대로, 다른 방은 병렬로 (STAGE0_DESIGN.md §6.3).
    with store.room_tx(safe_id) as (room, session):
        if room is None or session is None:
            raise RoomNotFound(room_id)
        if not member_id:
            raise InvalidRequest("member_id required")

        # 입장 전에 기록을 볼 수 없으므로, 첫 화면 안내를 띄울지는 입장 응답으로 알려준다.
        fresh = room["next_seq"] == 0
        now = _now_iso()
        existing = next((m for m in room["members"] if m["member_id"] == member_id), None)
        idle, last_text = _idle(safe_id, room)
        if _is_closed(session, idle, last_text) and user_text:
            # T4: 닫힌 방은 읽기 전용. 방장이 말하면 다시 연다(ROOM_POLICY §4.2).
            is_owner_now = bool(room["members"]) and room["members"][0]["member_id"] == member_id
            if not is_owner_now:
                raise RoomClosed(room_id)
            _append(room, "system", "시스템", MSG_REOPENED, kind="system")
        elif user_text:
            _run_timers(room, session, _due_timers(session, idle, last_text))
        if existing is None:
            if len(room["members"]) >= settings.room_max_members:
                raise RoomFull(room_id)  # D8
            room["members"].append({"member_id": member_id, "nickname": nickname, "joined_at": now, "last_seen": now})
            _append(room, "system", "시스템", f"{nickname}님이 입장했습니다.", kind="system")
        else:
            existing["last_seen"] = now
            existing["nickname"] = nickname

        if not user_text:
            return {"ai_status": room["ai_status"], "fresh": fresh}

        _append(room, member_id, nickname, user_text, kind="chat")

        # 승인 게이트는 과반 투표. 동점·미달이면 투표만 기록하고 AI는 호출하지 않는다.
        vote_reject = chat_flow.intent(user_text, "reject")
        if session["state"] == "AWAIT_APPROVAL" and (vote_reject or chat_flow.intent(user_text, "approve")):
            vote = "reject" if vote_reject else "approve"
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
            # 공유방의 사실 정보(전화·주소·가격·영업시간)는 방장 확인을 거친다 (DECISIONS.md D24).
            # 역할 기능(R-2) 전까지는 가장 먼저 들어온 사람이 방장이다.
            is_owner = bool(room["members"]) and room["members"][0]["member_id"] == member_id
            reply = chat_flow.process_turn(room["session_id"], session, user_text, base_url, room=room,
                                           by=member_handle(safe_id, member_id), is_owner=is_owner)
            _append(room, "ai", "AI 어시스턴트", reply, kind="ai_reply")

        return {"ai_status": room["ai_status"], "fresh": fresh}


def get_messages(room_id: str, since: int, base_url: str, member_id_raw=None) -> dict:
    """참여자들이 4초마다 부르는 조회. 조회가 GET이라 GENERATING 완료를 확인할 트리거가
    따로 없으므로 여기서 상태머신을 한 번 돌려 완료 전이를 일으킨다.

    평소에는 잠그지 않고 읽는다. 잠금은 코드생성 결과가 도착해 전이가 실제로 일어날 때만 잡는다
    (결과가 없으면 상태머신은 "생성 중"만 답하고 아무것도 바꾸지 않으므로 건너뛰어도 같다).
    """
    safe_id = _room_id(room_id)
    room = store.read_room(safe_id)
    member_id = sanitize_token(member_id_raw or "")
    # 참여자가 아니면 방이 있는지도 알려주지 않는다 (404).
    if room is None or not any(m["member_id"] == member_id for m in room["members"]):
        raise RoomNotFound(room_id)
    session = store.read_session(room["session_id"]) or {}
    idle, last_text = _idle(safe_id, room)
    if _due_timers(session, idle, last_text):
        # 타이머가 된 방만 잠그고, 잠근 뒤 다시 판정한다(그 사이 누가 입력했을 수 있음).
        with store.room_tx(safe_id) as (locked_room, locked_session):
            if locked_session is not None:
                idle2, last2 = _idle(safe_id, locked_room)
                _run_timers(locked_room, locked_session, _due_timers(locked_session, idle2, last2))
        room = store.read_room(safe_id)
        session = store.read_session(room["session_id"]) or {}
        idle, last_text = _idle(safe_id, room)
    if session.get("state") == "GENERATING" and session.get("codegen") is not None:
        with store.room_tx(safe_id) as (locked_room, locked_session):
            # 잠금을 기다리는 사이 다른 요청이 이미 전이시켰을 수 있으므로 다시 확인한다.
            if locked_session is not None and locked_session.get("state") == "GENERATING":
                reply = chat_flow.process_turn(locked_room["session_id"], locked_session, "", base_url, room=locked_room)
                if locked_session.get("state") != "GENERATING":
                    _append(locked_room, "ai", "AI 어시스턴트", reply, kind="ai_reply")
        room = store.read_room(safe_id)
        session = store.read_session(room["session_id"]) or {}
    return {
        "messages": [_public_message(safe_id, m) for m in store.read_messages(safe_id, since)],
        "ai_status": room["ai_status"],
        "members": [
            {"member_handle": member_handle(safe_id, m["member_id"]), "nickname": m["nickname"],
             "joined_at": m["joined_at"], "last_seen": m["last_seen"]}
            for m in room["members"]
        ],
        "votes": {member_handle(safe_id, k): v for k, v in room["votes"].items()},
        "state": session.get("state"),
        "deploy_url": session.get("deploy_url"),
        "design_url": session.get("design_url"),
        "design_preview_url": session.get("design_preview_url"),
        "question": _pending_question(session),
        "closed": _is_closed(session, idle, last_text),
    }


def _pending_question(session: dict):
    """요구사항 엔진이 기다리는 질문의 선택지. 채팅방이 누르는 버튼으로 그린다 (휴대폰 타자 줄이기)."""
    pending = (session.get("prd") or {}).get("pending")
    if session.get("state") != "GATHERING" or not pending:
        return None
    return {"kind": pending["kind"], "options": pending["options"],
            "owner_only": pending["kind"] == "owner_confirm"}
