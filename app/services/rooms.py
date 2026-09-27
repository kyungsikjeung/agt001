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


class InviteRequired(Exception):
    pass


class InviteInvalid(Exception):
    pass


class NotOwner(Exception):
    pass


# 타이머가 남기는 시스템 메시지 (ROOM_POLICY §4.2). 같은 글이 마지막이면 다시 남기지 않는다.
MSG_VOTE_RESET = "투표가 24시간 동안 끝나지 않아 초기화됐습니다. 다시 '승인' 또는 '거절'을 보내 주세요"
MSG_QUOTE_EXPIRED = "견적 유효기간(7일)이 지났습니다. 요구사항이 바뀌지 않았다면 '다시 견적'을 보내 주세요"
MSG_CLOSED = "30일 동안 활동이 없어 방이 닫혔습니다. 방장이 메시지를 보내면 다시 열립니다"
MSG_REOPENED = "방장이 방을 다시 열었습니다."
# D52: 두 번째 사람이 들어와 공유방이 되면 한 번 안내한다.
MSG_GROUP_GUIDE = ("여러 분이 함께하는 방이 됐어요. 사람끼리 나누는 이야기는 입력칸 위 '우리끼리'로 보내면 AI가 읽지 않아요. "
                   "AI 질문에는 누구나 답할 수 있고, 정리가 끝나면 모두 '동의'를 눌러야 다음 단계로 넘어가요.")
# 사전 경고(ROOM_POLICY §4.2 "경고" 열). 마지막 활동 뒤 한 번만 남긴다.
MSG_WARN_VOTE = "투표가 4시간 뒤 초기화돼요. '승인' 또는 '거절'을 보내 주세요"
MSG_WARN_QUOTE = "견적이 하루 뒤 만료돼요. 이대로 만들려면 '진행'을 보내 주세요"
MSG_WARN_CLOSE = "3일 뒤 방이 닫혀요. 메시지를 보내면 연장돼요"


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _idle(room_id: str, room: dict) -> tuple[Optional[datetime.timedelta], Optional[str], frozenset]:
    last_act, last_text, warned = room.get("activity") or store.activity_info(room_id)
    if last_act is None:
        created = room.get("created_at")
        last_act = datetime.datetime.fromisoformat(created) if isinstance(created, str) else created
    return ((_utcnow() - last_act) if last_act else None), last_text, warned


def _due_timers(session: dict, idle: Optional[datetime.timedelta], last_text: Optional[str],
                warned: frozenset = frozenset()) -> list[str]:
    """지금 실행할 타이머 (T1·T2·T4/T5와 그 사전 경고). 제작 중은 건드리지 않는다."""
    if idle is None or session.get("state") == "GENERATING":
        return []
    h = datetime.timedelta(hours=1)
    d = datetime.timedelta(days=1)
    state = session.get("state")
    if idle >= settings.room_close_days * d:
        return ["close"] if last_text != MSG_CLOSED else []
    if state == "AWAIT_APPROVAL" and idle >= settings.room_vote_reset_hours * h:
        return ["vote_reset"] if last_text != MSG_VOTE_RESET else []
    if state == "QUOTED" and idle >= settings.room_quote_expire_days * d:
        return ["quote_expire"] if last_text != MSG_QUOTE_EXPIRED else []
    due = []
    if idle >= (settings.room_close_days - 3) * d and MSG_WARN_CLOSE not in warned:
        due.append("warn_close")
    if state == "AWAIT_APPROVAL" and idle >= (settings.room_vote_reset_hours - 4) * h and MSG_WARN_VOTE not in warned:
        due.append("warn_vote")
    if state == "QUOTED" and idle >= (settings.room_quote_expire_days - 1) * d and MSG_WARN_QUOTE not in warned:
        due.append("warn_quote")
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
        elif t.startswith("warn_"):
            text = {"warn_vote": MSG_WARN_VOTE, "warn_quote": MSG_WARN_QUOTE, "warn_close": MSG_WARN_CLOSE}[t]
            _append(room, "system", "시스템", text, kind="warning")
            _notify_owner_later(room, text)


def _is_closed(session: dict, idle: Optional[datetime.timedelta], last_text: Optional[str]) -> bool:
    if session.get("state") == "GENERATING":
        return False
    return last_text == MSG_CLOSED or (idle is not None and idle >= datetime.timedelta(days=settings.room_close_days))


def _now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append(room: dict, member_id: str, nickname: str, text: str, kind: str = "chat",
            meta: Optional[dict] = None) -> None:
    room["new_messages"].append({
        "seq": room["next_seq"],
        "member_id": member_id,
        "nickname": nickname,
        "text": text,
        "ts": _now_iso(),
        "kind": kind,
        "meta": meta,
    })
    room["next_seq"] += 1


def _notify_owner_later(room: dict, text: str) -> None:
    """방장 카톡 알림(켜져 있으면). 방 잠금 안에서 외부 호출을 하지 않으려고 커밋 뒤에 보낸다."""
    try:
        from app.services import notify
        room_id = room["room_id"]
        store.after_commit(lambda: notify.owner_kakao(room_id, text))
    except Exception:
        pass


def owner_id(room: dict) -> Optional[str]:
    """방장 = 참여자 목록 맨 앞(ROOM_POLICY §2). 넘기기·나가기는 순서를 바꾼다."""
    return room["members"][0]["member_id"] if room["members"] else None


def member_handle(room_id: str, member_id: str) -> str:
    """응답에 내보내는 공개 식별자 (ROOM_POLICY.md §1 R-0).

    member_id는 본인 확인용 비밀값(브라우저에만 저장)이라 응답에 담으면 같은 방 참여자가 남의
    이름으로 투표할 수 있다. 무작위 UUID의 해시라 공개 식별자에서 원래 값을 알아낼 수 없다.
    """
    if member_id in _SERVER_SENDERS:
        return member_id
    return hashlib.sha256(f"{room_id}:{member_id}".encode()).hexdigest()[:12]


def _public_message(room_id: str, msg: dict) -> dict:
    out = {k: v for k, v in msg.items() if k not in ("member_id", "meta")}
    out["member_handle"] = member_handle(room_id, msg["member_id"])
    if msg.get("kind") in ("booking", "booking_result"):
        # 예약 알림 말풍선의 확정·거절 버튼용(BOOKING_PLAN §2.4). 저장소는 meta를 메시지에 풀어 돌려준다.
        meta = msg.get("meta") or msg
        bid = out.pop("booking_id", None) or meta.get("booking_id")
        status = out.pop("status", None) or meta.get("status") or "requested"
        if bid:
            out["booking"] = {"id": bid, "status": status}
    return out


def _room_id(room_id: str) -> str:
    safe_id = sanitize_token(room_id)
    if not safe_id:
        raise RoomNotFound(room_id)
    return safe_id


def create_room(template_id: Optional[str] = None) -> str:
    room_id = str(uuid.uuid4())[:8]
    session_id = str(uuid.uuid4())
    store.create_room(room_id, session_id, chat_flow.new_session(sanitize_token(template_id or "") or None),
                      invite_required=settings.room_invite_required)
    return room_id


def _member(room: dict, member_id: str) -> Optional[dict]:
    return next((m for m in room["members"] if m["member_id"] == member_id), None)


def transfer_owner(room_id: str, member_id_raw, to_handle: str) -> str:
    safe_id = _room_id(room_id)
    member_id = sanitize_token(member_id_raw or "")
    with store.room_tx(safe_id) as (room, _session):
        if room is None or not _member(room, member_id):
            raise RoomNotFound(room_id)
        if owner_id(room) != member_id:
            raise NotOwner(room_id)
        target = next((m for m in room["members"] if member_handle(safe_id, m["member_id"]) == to_handle), None)
        if target is None:
            raise InvalidRequest("member not found")
        room["members"].remove(target)
        room["members"].insert(0, target)
        _append(room, "system", "시스템", f"{target['nickname']}님이 방장이 됐어요.", kind="system")
        return member_handle(safe_id, target["member_id"])


def leave(room_id: str, member_id_raw) -> None:
    safe_id = _room_id(room_id)
    member_id = sanitize_token(member_id_raw or "")
    with store.room_tx(safe_id) as (room, _session):
        if room is None or not _member(room, member_id):
            raise RoomNotFound(room_id)
        was_owner = owner_id(room) == member_id
        me = _member(room, member_id)
        room["members"].remove(me)
        room["votes"].pop(member_id, None)
        text = f"{me['nickname']}님이 나갔어요."
        if was_owner and room["members"]:
            # 방장이 나가면 가장 먼저 들어온 참여자에게 넘어간다(ROOM_POLICY §2).
            text += f" 이제 {room['members'][0]['nickname']}님이 방장이에요."
        _append(room, "system", "시스템", text, kind="system")


def create_invite(room_id: str, member_id_raw, days: int) -> dict:
    safe_id = _room_id(room_id)
    member_id = sanitize_token(member_id_raw or "")
    room = store.read_room(safe_id)
    if room is None or not _member(room, member_id):
        raise RoomNotFound(room_id)
    if owner_id(room) != member_id:
        raise NotOwner(room_id)
    days = days if days in (0, 1, 7, 30) else 7
    invite_id, token, expires = store.create_invite(safe_id, member_handle(safe_id, member_id), days)
    return {"invite_id": invite_id, "url": f"/room.html?room={safe_id}&invite={token}", "expires_at": expires}


def list_invites(room_id: str, member_id_raw) -> list[dict]:
    safe_id = _room_id(room_id)
    room = store.read_room(safe_id)
    if room is None or owner_id(room) != sanitize_token(member_id_raw or ""):
        raise NotOwner(room_id)
    return store.list_invites(safe_id)


def revoke_invite(room_id: str, member_id_raw, invite_id: str) -> None:
    safe_id = _room_id(room_id)
    room = store.read_room(safe_id)
    if room is None or owner_id(room) != sanitize_token(member_id_raw or ""):
        raise NotOwner(room_id)
    if not store.revoke_invite(safe_id, sanitize_token(invite_id or "")):
        raise InvalidRequest("invite not found")


def tally(votes: dict) -> tuple[int, int]:
    approve_n = sum(1 for v in votes.values() if v == "approve")
    reject_n = sum(1 for v in votes.values() if v == "reject")
    return approve_n, reject_n


def post_message(room_id: str, member_id_raw, nickname_raw, message_raw, base_url: str,
                 invite_raw: Optional[str] = None, to_ai: bool = True) -> dict:
    safe_id = _room_id(room_id)
    member_id = sanitize_token(member_id_raw or "")
    nickname = html.escape((nickname_raw or "익명")[:MAX_NICKNAME_LEN])
    user_text = (message_raw or "").strip()[:MAX_MESSAGE_LEN]

    # 초대 확인은 방 잠금 밖에서 먼저 한다(잠금 중에 연결을 하나 더 잡지 않게).
    peek = store.read_room(safe_id)
    if (peek is not None and member_id and peek.get("invite_required") and peek["members"]
            and not _member(peek, member_id)):
        if not invite_raw:
            raise InviteRequired(room_id)
        if not store.use_invite(safe_id, invite_raw):
            raise InviteInvalid(room_id)

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
        idle, last_text, warned = _idle(safe_id, room)
        if _is_closed(session, idle, last_text) and user_text:
            # T4: 닫힌 방은 읽기 전용. 방장이 말하면 다시 연다(ROOM_POLICY §4.2).
            is_owner_now = bool(room["members"]) and room["members"][0]["member_id"] == member_id
            if not is_owner_now:
                raise RoomClosed(room_id)
            _append(room, "system", "시스템", MSG_REOPENED, kind="system")
        elif user_text:
            # 사람이 말하면 활동이 이어지므로, 이미 된 초기화·만료만 먼저 처리한다(경고는 필요 없다).
            _run_timers(room, session, [t for t in _due_timers(session, idle, last_text, warned) if not t.startswith("warn_")])
        if existing is None:
            if len(room["members"]) >= settings.room_max_members:
                raise RoomFull(room_id)  # D8
            room["members"].append({"member_id": member_id, "nickname": nickname, "joined_at": now, "last_seen": now})
            _append(room, "system", "시스템", f"{nickname}님이 입장했습니다.", kind="system")
            if len(room["members"]) == 2:
                _append(room, "system", "시스템", MSG_GROUP_GUIDE, kind="system")
        else:
            existing["last_seen"] = now
            existing["nickname"] = nickname

        if not user_text:
            return {"ai_status": room["ai_status"], "fresh": fresh}

        if not to_ai:
            # D52: 사람끼리 나누는 이야기. 기록만 하고 AI·투표에는 넣지 않는다.
            _append(room, member_id, nickname, user_text, kind="chat", meta={"aside": True})
            return {"ai_status": room["ai_status"], "fresh": fresh}

        _append(room, member_id, nickname, user_text, kind="chat")

        # 승인 게이트는 전원 동의(D52). 모두 동의하면 다음 단계, 한 명이라도 거절하면 고칠 점을 다시 모은다.
        vote_reject = chat_flow.intent(user_text, "reject")
        if session["state"] == "AWAIT_APPROVAL" and (vote_reject or chat_flow.intent(user_text, "approve")):
            vote = "reject" if vote_reject else "approve"
            room["votes"][member_id] = vote
            total = len(room["members"])
            approve_n, reject_n = tally(room["votes"])
            _append(
                room, "system", "시스템",
                f"{nickname}님이 {'동의' if vote == 'approve' else '거절'}했습니다 (동의 {approve_n}/{total})"
                + (" · 모두 동의하면 다음 단계로 넘어가요" if vote == "approve" and approve_n < total else ""),
                kind="vote",
            )
            decision = "거절" if reject_n else "승인" if approve_n == total else None
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
    idle, last_text, warned = _idle(safe_id, room)
    if _due_timers(session, idle, last_text, warned):
        # 타이머가 된 방만 잠그고, 잠근 뒤 다시 판정한다(그 사이 누가 입력했을 수 있음).
        with store.room_tx(safe_id) as (locked_room, locked_session):
            if locked_session is not None:
                idle2, last2, warned2 = _idle(safe_id, locked_room)
                _run_timers(locked_room, locked_session, _due_timers(locked_session, idle2, last2, warned2))
        room = store.read_room(safe_id)
        session = store.read_session(room["session_id"]) or {}
        idle, last_text, warned = _idle(safe_id, room)
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
             "is_owner": i == 0, "joined_at": m["joined_at"], "last_seen": m["last_seen"]}
            for i, m in enumerate(room["members"])
        ],
        "me": {"member_handle": member_handle(safe_id, member_id), "is_owner": owner_id(room) == member_id},
        "invite_required": bool(room.get("invite_required")),
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
