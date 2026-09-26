"""세션·방 저장소 (PostgreSQL, STAGE0_DESIGN.md §6.3~6.4).

상태머신(chat_flow)은 계속 dict를 받아 고친다. 이 모듈은 트랜잭션 시작 시 행을 dict로 읽고,
블록이 정상 종료되면 dict를 행에 다시 쓴다. 예외로 끝나면 아무것도 저장하지 않는다.

동시성 규칙
- 같은 방·세션에 쓰는 요청은 트랜잭션 범위 advisory lock으로 직렬화한다. 다른 방은 병렬이다.
  행 잠금(FOR UPDATE)을 쓰지 않는 이유: 긴 NIM 호출 전에 ai_status를 별도 트랜잭션으로 바로
  커밋해 폴링하는 참여자에게 보여줘야 하는데, 행 잠금이면 그 UPDATE가 자기 잠금에 막힌다.
- 잠금 순서는 항상 방 → 세션이다.
- 백그라운드 코드생성 결과 기록도 세션 잠금을 잡는다. 요청 트랜잭션이 읽어 둔 codegen=None으로
  막 기록된 결과를 덮어쓰지 않게 하려는 것이다.
- 커밋 뒤에 해야 하는 일(코드생성 스레드 시작 등)은 after_commit으로 등록한다. 커밋 전에
  스레드가 시작되면 아직 보이지 않는 세션을 읽게 된다.
"""
import datetime
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, Optional

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm.attributes import flag_modified

from app.db.models import ChatTurnRow, RoomInviteRow, RoomMemberRow, RoomMessageRow, RoomRow, RoomVoteRow, SessionRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

_LOCK_NS_ROOM = 1
_LOCK_NS_SESSION = 2

# JSONB 열. 읽은 dict를 제자리에서 고치면 ORM이 변경을 모르므로 저장할 때 항상 변경으로 표시한다.
_JSON_FIELDS = ("quote", "codegen", "prd")

# dict 키 ↔ sessions 열. 이 밖의 키가 dict에 생기면 조용히 버리지 않고 에러를 낸다.
_SESSION_FIELDS = (
    "state", "requirement_id", "last_request", "quote", "codegen", "prd",
    "design_url", "design_preview_url", "design_url_unsent", "deploy_url",
)


class _Tx:
    def __init__(self, db: DbSession):
        self.db = db
        self.after_commit: list[Callable[[], None]] = []


_current: ContextVar[Optional[_Tx]] = ContextVar("store_tx", default=None)


@contextmanager
def _transaction() -> Iterator[_Tx]:
    """요청 하나 = 트랜잭션 하나. 이미 열려 있으면 그 트랜잭션에 합류한다."""
    existing = _current.get()
    if existing is not None:
        yield existing
        return
    db = get_sessionmaker()()
    tx = _Tx(db)
    token = _current.set(tx)
    try:
        with db.begin():
            yield tx
    finally:
        _current.reset(token)
        db.close()
    for fn in tx.after_commit:
        try:
            fn()
        except Exception:
            log.exception("커밋 후 작업 실패")


def after_commit(fn: Callable[[], None]) -> None:
    """현재 트랜잭션이 커밋된 뒤 실행한다. 트랜잭션 밖이면 바로 실행한다."""
    tx = _current.get()
    if tx is None:
        fn()
    else:
        tx.after_commit.append(fn)


def _lock(db: DbSession, namespace: int, key: str) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:ns, hashtext(:key))"), {"ns": namespace, "key": key})


def _iso(value: Optional[datetime.datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _parse_ts(value) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        return value
    return datetime.datetime.fromisoformat(value)


# ── 세션 ──────────────────────────────────────────────────────────────

def _session_to_dict(row: SessionRow) -> dict:
    # 값이 없는 키는 dict에 넣지 않는다. 상태머신이 session.get(key, 기본값) 형태로
    # "키 없음"과 "값 있음"을 구분하는 곳이 있기 때문이다 (JSON 저장소 시절 동작과 동일).
    data = {}
    for field in _SESSION_FIELDS:
        value = getattr(row, field)
        if value is None or (field == "design_url_unsent" and not value):
            continue
        data[field] = value
    return data


def _apply_session(row: SessionRow, data: dict) -> None:
    unknown = set(data) - set(_SESSION_FIELDS)
    if unknown:
        raise ValueError(f"sessions에 없는 필드: {sorted(unknown)}")
    if data.get("requirement_id") != row.requirement_id:
        raise ValueError("requirement_id는 바꿀 수 없습니다")
    for field in _SESSION_FIELDS:
        if field == "requirement_id":
            continue
        value = data.get(field)
        setattr(row, field, bool(value) if field == "design_url_unsent" else value)
        if field in _JSON_FIELDS:
            flag_modified(row, field)
    row.updated_at = func.now()


def _new_session_row(session_id: str, data: dict) -> SessionRow:
    row = SessionRow(id=session_id, requirement_id=data["requirement_id"], state=data["state"])
    _apply_session(row, data)
    return row


@contextmanager
def session_tx(session_id: str, default: Optional[Callable[[], dict]] = None) -> Iterator[Optional[dict]]:
    """세션을 잠그고 dict로 준다. 없으면 default()로 만들고, default가 없으면 None을 준다."""
    with _transaction() as tx:
        _lock(tx.db, _LOCK_NS_SESSION, session_id)
        row = tx.db.get(SessionRow, session_id)
        if row is None:
            if default is None:
                yield None
                return
            data = default()
            row = _new_session_row(session_id, data)
            tx.db.add(row)
        else:
            data = _session_to_dict(row)
        yield data
        _apply_session(row, data)


def read_session(session_id: str) -> Optional[dict]:
    """잠금 없는 조회 (폴링용)."""
    with get_sessionmaker()() as db:
        row = db.get(SessionRow, session_id)
        return _session_to_dict(row) if row else None


def set_codegen(session_id: str, result: dict) -> None:
    """백그라운드 코드생성 결과 기록. 그 사이 사용자가 다른 상태로 옮겼으면 버린다."""
    with _transaction() as tx:
        _lock(tx.db, _LOCK_NS_SESSION, session_id)
        tx.db.execute(
            update(SessionRow)
            .where(SessionRow.id == session_id, SessionRow.state == "GENERATING")
            .values(codegen=result, updated_at=func.now())
        )


# ── 방 ────────────────────────────────────────────────────────────────

def _load_room(db: DbSession, row: RoomRow) -> dict:
    members = db.scalars(
        select(RoomMemberRow).where(RoomMemberRow.room_id == row.id).order_by(RoomMemberRow.position)
    ).all()
    votes = db.scalars(select(RoomVoteRow).where(RoomVoteRow.room_id == row.id)).all()
    return {
        "room_id": row.id,
        "session_id": row.session_id,
        "created_at": _iso(row.created_at),
        "ai_status": row.ai_status,
        "invite_required": row.invite_required,
        "members": [
            {"member_id": m.member_id, "nickname": m.nickname,
             "joined_at": _iso(m.joined_at), "last_seen": _iso(m.last_seen)}
            for m in members
        ],
        "votes": {v.member_id: v.vote for v in votes},
    }


def _save_room(db: DbSession, row: RoomRow, room: dict) -> None:
    # ORM 속성 대입은 "읽은 값과 같으면" UPDATE를 생략한다. 그 사이 set_room_ai_status가
    # 다른 값을 커밋했을 수 있으므로 최종 상태는 항상 명시적으로 쓴다.
    db.execute(update(RoomRow).where(RoomRow.id == row.id).values(ai_status=room["ai_status"]))
    for position, m in enumerate(room["members"]):
        stmt = pg_insert(RoomMemberRow).values(
            room_id=row.id, member_id=m["member_id"], nickname=m["nickname"],
            joined_at=_parse_ts(m["joined_at"]), last_seen=_parse_ts(m["last_seen"]), position=position,
        )
        db.execute(stmt.on_conflict_do_update(
            index_elements=["room_id", "member_id"],
            # 순서(position)도 쓴다: 맨 앞이 방장이라 방장 넘기기는 순서 바꾸기다.
            set_={"nickname": stmt.excluded.nickname, "last_seen": stmt.excluded.last_seen,
                  "position": stmt.excluded.position},
        ))
    # 나간 참여자는 지운다(그가 쓴 메시지는 남는다).
    keep = [m["member_id"] for m in room["members"]]
    db.execute(delete(RoomMemberRow).where(RoomMemberRow.room_id == row.id, RoomMemberRow.member_id.not_in(keep)))
    db.execute(delete(RoomVoteRow).where(RoomVoteRow.room_id == row.id))
    for member_id, vote in room["votes"].items():
        db.add(RoomVoteRow(room_id=row.id, member_id=member_id, vote=vote))
    for msg in room["new_messages"]:
        db.add(RoomMessageRow(
            room_id=row.id, seq=msg["seq"], member_id=msg["member_id"], nickname=msg["nickname"],
            text=msg["text"], kind=msg["kind"], ts=_parse_ts(msg["ts"]), meta=msg.get("meta"),
        ))


def create_room(room_id: str, session_id: str, session: dict, invite_required: bool = False) -> None:
    with _transaction() as tx:
        tx.db.add(_new_session_row(session_id, session))
        tx.db.flush()
        tx.db.add(RoomRow(id=room_id, session_id=session_id, ai_status="IDLE", invite_required=invite_required))


# ── 초대 링크 (ROOM_POLICY §3) ────────────────────────────────────────

def _token_hash(token: str) -> str:
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


def create_invite(room_id: str, created_by: str, days: int) -> tuple[str, str, Optional[str]]:
    """(초대 ID, 토큰 원문, 만료 시각). 토큰 원문은 여기서만 나오고 저장하지 않는다."""
    import secrets
    token = secrets.token_urlsafe(18)
    invite_id = secrets.token_hex(4)
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)) if days else None
    with _transaction() as tx:
        tx.db.add(RoomInviteRow(id=invite_id, room_id=room_id, token_hash=_token_hash(token),
                                created_by=created_by, expires_at=expires))
    return invite_id, token, _iso(expires)


def list_invites(room_id: str) -> list[dict]:
    with get_sessionmaker()() as db:
        rows = db.scalars(select(RoomInviteRow).where(RoomInviteRow.room_id == room_id)
                          .order_by(RoomInviteRow.created_at.desc())).all()
        return [{"invite_id": r.id, "created_at": _iso(r.created_at), "expires_at": _iso(r.expires_at),
                 "revoked": r.revoked, "uses": r.uses} for r in rows]


def revoke_invite(room_id: str, invite_id: str) -> bool:
    with _transaction() as tx:
        n = tx.db.execute(update(RoomInviteRow).where(RoomInviteRow.room_id == room_id, RoomInviteRow.id == invite_id)
                          .values(revoked=True)).rowcount
    return bool(n)


def use_invite(room_id: str, token: str) -> bool:
    """유효한 초대면 사용 횟수를 올리고 True. 틀림·폐기·만료면 False."""
    now = datetime.datetime.now(datetime.timezone.utc)
    with _transaction() as tx:
        n = tx.db.execute(
            update(RoomInviteRow)
            .where(RoomInviteRow.room_id == room_id, RoomInviteRow.token_hash == _token_hash(token or ""),
                   RoomInviteRow.revoked.is_(False),
                   (RoomInviteRow.expires_at.is_(None)) | (RoomInviteRow.expires_at > now))
            .values(uses=RoomInviteRow.uses + 1)).rowcount
    return bool(n)


@contextmanager
def room_tx(room_id: str) -> Iterator[tuple[Optional[dict], Optional[dict]]]:
    """방과 그 세션을 잠그고 (room, session) dict를 준다.

    room["new_messages"]에 넣은 메시지만 추가 저장된다. seq는 room["next_seq"]부터 이어서 붙인다.
    """
    with _transaction() as tx:
        _lock(tx.db, _LOCK_NS_ROOM, room_id)
        row = tx.db.get(RoomRow, room_id)
        if row is None:
            yield None, None
            return
        room = _load_room(tx.db, row)
        last_seq = tx.db.scalar(select(func.max(RoomMessageRow.seq)).where(RoomMessageRow.room_id == room_id))
        room["next_seq"] = 0 if last_seq is None else last_seq + 1
        room["new_messages"] = []
        room["activity"] = _activity(tx.db, room_id)
        with session_tx(row.session_id) as session:
            yield room, session
        _save_room(tx.db, row, room)


def read_room(room_id: str) -> Optional[dict]:
    """잠금 없는 조회 (폴링용)."""
    with get_sessionmaker()() as db:
        row = db.get(RoomRow, room_id)
        return _load_room(db, row) if row else None


def read_messages(room_id: str, since: int) -> list[dict]:
    with get_sessionmaker()() as db:
        rows = db.scalars(
            select(RoomMessageRow)
            .where(RoomMessageRow.room_id == room_id, RoomMessageRow.seq >= since)
            .order_by(RoomMessageRow.seq)
        ).all()
        return [
            {"seq": r.seq, "member_id": r.member_id, "nickname": r.nickname,
             "text": r.text, "ts": _iso(r.ts), "kind": r.kind, **(r.meta or {})}
            for r in rows
        ]


def _activity(db: DbSession, room_id: str) -> tuple[Optional[datetime.datetime], Optional[str], frozenset]:
    """(마지막 사람 활동 시각, 마지막 메시지 글, 그 뒤에 남긴 경고 글들). 경고는 활동 뒤 한 번만 남기려고 본다."""
    last_act = db.scalar(select(func.max(RoomMessageRow.ts))
                         .where(RoomMessageRow.room_id == room_id, RoomMessageRow.kind.in_(("chat", "vote"))))
    last_text = db.scalar(select(RoomMessageRow.text).where(RoomMessageRow.room_id == room_id)
                          .order_by(RoomMessageRow.seq.desc()).limit(1))
    q = select(RoomMessageRow.text).where(RoomMessageRow.room_id == room_id, RoomMessageRow.kind == "warning")
    if last_act is not None:
        q = q.where(RoomMessageRow.ts > last_act)
    return last_act, last_text, frozenset(db.scalars(q).all())


def activity_info(room_id: str) -> tuple[Optional[datetime.datetime], Optional[str], frozenset]:
    """(마지막 사람 활동 시각, 마지막 메시지 글). 활동은 사람이 보낸 메시지와 투표(ROOM_POLICY §4.2).
    room_tx 안에서는 room["activity"]를 쓴다(잠금 중에 연결을 하나 더 잡으면 동시 요청에서 풀이 바닥난다)."""
    with get_sessionmaker()() as db:
        return _activity(db, room_id)


def set_room_ai_status(room_id: str, status: str) -> None:
    """요청 트랜잭션과 별개로 바로 커밋한다. 긴 NIM 호출 중에도 다른 참여자가 진행 상태를 보게 한다."""
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(RoomRow).where(RoomRow.id == room_id).values(ai_status=status))


# ── 기동·테스트 ───────────────────────────────────────────────────────

def recover_on_startup() -> None:
    """코드생성 스레드는 재시작과 함께 사라지므로, 사용자가 '진행'으로 재시도할 수 있게 되돌린다.

    0-3에서 코드생성이 별도 워커(작업 큐)로 옮겨 가면 이 복구는 워커 기준으로 바뀐다.
    """
    with get_sessionmaker()() as db, db.begin():
        n_sessions = db.execute(
            update(SessionRow).where(SessionRow.state == "GENERATING").values(state="QUOTED", codegen=None)
        ).rowcount
        n_rooms = db.execute(update(RoomRow).where(RoomRow.ai_status != "IDLE").values(ai_status="IDLE")).rowcount
    log.info("기동 복구: 세션 %d개 GENERATING→QUOTED, 방 %d개 ai_status→IDLE", n_sessions, n_rooms)


# ── 대화 턴 기록 (AI 성능 평가) ────────────────────────────────────────

CHAT_TURN_RETENTION_DAYS = 90
MAX_TURN_TEXT = 4000


def record_turn(session_id: str, room_id: Optional[str], author: Optional[str], user_text: str, ai_text: str,
                state_before: str, state_after: str, meta: Optional[dict]) -> None:
    """요청 트랜잭션 안에서 함께 기록한다(대화 처리가 롤백되면 기록도 사라진다)."""
    with _transaction() as tx:
        tx.db.add(ChatTurnRow(
            session_id=session_id, room_id=room_id, author=author,
            user_text=(user_text or "")[:MAX_TURN_TEXT], ai_text=(ai_text or "")[:MAX_TURN_TEXT],
            state_before=state_before, state_after=state_after, meta=meta,
        ))


def purge_chat_turns(now: Optional[datetime.datetime] = None) -> int:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=CHAT_TURN_RETENTION_DAYS)
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(ChatTurnRow).where(ChatTurnRow.ts < cutoff)).rowcount
    if n:
        log.info("대화 턴 기록 %d건 삭제 (%d일 경과)", n, CHAT_TURN_RETENTION_DAYS)
    return n


def reset_all() -> None:
    """테스트 전용: 모든 행을 지운다."""
    with get_sessionmaker()() as db, db.begin():
        db.execute(text("TRUNCATE attachments, room_invites, inquiries, user_rooms, login_sessions, oauth_states, oauth_accounts, users, chat_turns, funnel_events, room_votes, room_messages, room_members, rooms, sessions RESTART IDENTITY CASCADE"))
