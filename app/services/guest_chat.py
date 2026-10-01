"""손님 ↔ 사장님 채팅 저장·알림 (GUEST_CHAT_CONTRACT §1·§2).

손님은 예약 채팅 쿠키 토큰의 해시로만 찾는다(원문 저장 없음). 공개된 가게(shops 행)만 대화를 남긴다.
알림은 글 원문 없이 "새 채팅이 왔어요"만, 같은 대화는 10분에 한 번. 마지막 글 뒤 30일이 지나면 지운다.
"""
import datetime
import logging
from typing import Optional

from sqlalchemy import delete, func, select

from app.config import settings
from app.db.models import GuestChatMessageRow, GuestChatThreadRow, ShopRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

KEEP_DAYS = 30
NOTIFY_EVERY = datetime.timedelta(minutes=10)
MAX_LEN = 500
OPEN, TO_OWNER = "ai", "owner"
CLOSED_STATES = ("closed", "blocked")


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def enabled(site_key: str) -> bool:
    """공개된 가게이고 '손님 채팅 받기'가 켜져 있으면 True."""
    from app.services import shop_settings
    with get_sessionmaker()() as db:
        if db.get(ShopRow, site_key) is None:
            return False
    try:
        return bool(shop_settings.get(site_key).get("guest_chat_on", True))
    except Exception:
        log.exception("손님 채팅 설정 읽기 실패")
        return False


def _thread(db, shop_id: str, th: str, create: bool) -> Optional[GuestChatThreadRow]:
    row = db.scalar(select(GuestChatThreadRow).where(GuestChatThreadRow.shop_id == shop_id,
                                                     GuestChatThreadRow.token_hash == th))
    if row is None and create:
        row = GuestChatThreadRow(shop_id=shop_id, token_hash=th, status=OPEN, owner_unread=0)
        db.add(row)
        db.flush()
    return row


def status(shop_id: str, th: Optional[str]) -> str:
    """이 손님 대화 상태. 대화가 없으면 'ai'."""
    if not th:
        return OPEN
    with get_sessionmaker()() as db:
        row = _thread(db, shop_id, th, create=False)
        return row.status if row is not None else OPEN


def log_turn(shop_id: str, th: Optional[str], guest_text: str, reply_text: str, *,
             to_owner: bool = False) -> Optional[int]:
    """손님 글과 AI 답을 남긴다. to_owner면 대화를 사장님 대기로 바꾸고 알린다. 대화 id를 돌려준다."""
    if not th:
        return None
    guest_text = (guest_text or "").strip()[:MAX_LEN]
    reply_text = (reply_text or "").strip()[:MAX_LEN]
    now = _now()
    with get_sessionmaker()() as db, db.begin():
        row = _thread(db, shop_id, th, create=True)
        if row.status in CLOSED_STATES:
            return row.id
        if guest_text:
            db.add(GuestChatMessageRow(thread_id=row.id, sender="guest", text=guest_text, created_at=now))
            if row.status == TO_OWNER or to_owner:
                row.owner_unread = (row.owner_unread or 0) + 1
        if reply_text:
            db.add(GuestChatMessageRow(thread_id=row.id, sender="ai", text=reply_text, created_at=now))
        if to_owner:
            row.status = TO_OWNER
        row.last_at = now
        thread_id = row.id
        need_notify = bool(row.status == TO_OWNER and guest_text and (
            row.notified_at is None or now - row.notified_at >= NOTIFY_EVERY))
        if need_notify:
            row.notified_at = now
    if need_notify:
        _notify(shop_id, guest_text)
    return thread_id


def last_sender(shop_id: str, th: Optional[str]) -> str:
    """마지막 글 쓴 쪽(없으면 빈 글). 사장님 대기 중 연달아 보낼 때 답을 한 번만 하려고 본다."""
    if not th:
        return ""
    with get_sessionmaker()() as db:
        row = _thread(db, shop_id, th, create=False)
        if row is None:
            return ""
        return db.scalar(select(GuestChatMessageRow.sender).where(GuestChatMessageRow.thread_id == row.id)
                         .order_by(GuestChatMessageRow.id.desc()).limit(1)) or ""


def to_owner(shop_id: str, th: Optional[str]) -> None:
    """'사장님께 직접 물어보기': 대화를 사장님 대기로(글이 오면 그때 알린다)."""
    if not th:
        return
    with get_sessionmaker()() as db, db.begin():
        row = _thread(db, shop_id, th, create=True)
        if row.status not in CLOSED_STATES:
            row.status = TO_OWNER
            row.last_at = _now()


def _notify(shop_id: str, text: str) -> None:
    """채팅방 한 줄(사장님 방이라 원문 포함, 예전 문의 알림과 같게) + 카톡(동의한 사장님만, 원문 없이)."""
    from app import store
    from app.services import booking_engine, notify, rooms
    room_id = booking_engine._room_for(shop_id)
    if not room_id:
        return
    base = (settings.public_base_url or "").rstrip("/")
    link = f"{base}/owner" if base else "/owner"
    try:
        with store.room_tx(room_id) as (room, _session):
            if room is not None:
                rooms._append(room, "system", "손님 문의(채팅)",
                              f"{text[:300]}\n(사장님 화면 > 채팅에서 답할 수 있어요)", kind="inquiry")
    except Exception:
        log.exception("손님 채팅 채팅방 알림 실패")
    try:
        notify.owner_kakao(room_id, f"새 채팅이 왔어요. 사장님 화면 > 채팅에서 답해 주세요.\n{link}")
    except Exception:
        log.exception("손님 채팅 카톡 알림 실패")


def messages_after(shop_id: str, th: Optional[str], after: int = 0) -> dict:
    """손님 화면용: after 뒤의 글과 상태. 대화가 없으면 빈 목록."""
    if not th:
        return {"messages": [], "status": OPEN}
    with get_sessionmaker()() as db:
        row = _thread(db, shop_id, th, create=False)
        if row is None:
            return {"messages": [], "status": OPEN}
        rows = db.scalars(select(GuestChatMessageRow).where(GuestChatMessageRow.thread_id == row.id,
                                                            GuestChatMessageRow.id > int(after or 0))
                          .order_by(GuestChatMessageRow.id).limit(200)).all()
        return {"messages": [_msg(m) for m in rows], "status": row.status}


def _msg(m: GuestChatMessageRow) -> dict:
    return {"id": m.id, "sender": m.sender, "text": m.text, "at": m.created_at.isoformat()}


# ── 사장님 화면 ──

def shop_signature(shop_id: str) -> str:
    """사장님 채팅 탭 즉시 반영용 (§7): 대화 수·안 읽음·마지막 글 시각·기다림·닫힘 수가 바뀌면 달라지는 한 줄."""
    t = GuestChatThreadRow
    with get_sessionmaker()() as db:
        n, unread, last, waiting, ended = db.execute(
            select(func.count(), func.coalesce(func.sum(t.owner_unread), 0), func.max(t.last_at),
                   func.count().filter(t.status == TO_OWNER), func.count().filter(t.status.in_(CLOSED_STATES)))
            .where(t.shop_id == shop_id)).one()
    return f"{n}:{unread}:{last.isoformat() if last else ''}:{waiting}:{ended}"


def owner_list(shop_id: str) -> list:
    """최근 대화 50개: {id, status, owner_unread, last_at, last_text(40자)}."""
    with get_sessionmaker()() as db:
        threads = db.scalars(select(GuestChatThreadRow).where(GuestChatThreadRow.shop_id == shop_id)
                             .order_by(GuestChatThreadRow.last_at.desc()).limit(50)).all()
        out = []
        for t in threads:
            last = db.scalar(select(GuestChatMessageRow.text).where(GuestChatMessageRow.thread_id == t.id)
                             .order_by(GuestChatMessageRow.id.desc()).limit(1))
            out.append({"id": t.id, "status": t.status, "owner_unread": t.owner_unread or 0,
                        "last_at": t.last_at.isoformat(), "last_text": (last or "")[:40]})
        return out


def _owned_thread(db, shop_id: str, thread_id: int) -> GuestChatThreadRow:
    row = db.get(GuestChatThreadRow, int(thread_id))
    if row is None or row.shop_id != shop_id:
        raise LookupError("thread")
    return row


def owner_view(shop_id: str, thread_id: int) -> dict:
    """대화 전부 + 안 읽음 0으로."""
    with get_sessionmaker()() as db, db.begin():
        row = _owned_thread(db, shop_id, thread_id)
        row.owner_unread = 0
        msgs = db.scalars(select(GuestChatMessageRow).where(GuestChatMessageRow.thread_id == row.id)
                          .order_by(GuestChatMessageRow.id)).all()
        return {"id": row.id, "status": row.status, "messages": [_msg(m) for m in msgs]}


def owner_reply(shop_id: str, thread_id: int, text: str) -> dict:
    """사장님 답 (1~500자). 닫힘·차단 대화에는 못 쓴다."""
    text = (text or "").strip()
    if not text or len(text) > MAX_LEN:
        raise ValueError("답은 1~500자로 적어 주세요.")
    with get_sessionmaker()() as db, db.begin():
        row = _owned_thread(db, shop_id, thread_id)
        if row.status in CLOSED_STATES:
            raise ValueError("닫았거나 차단한 대화예요.")
        msg = GuestChatMessageRow(thread_id=row.id, sender="owner", text=text, created_at=_now())
        db.add(msg)
        row.status = TO_OWNER
        row.owner_unread = 0
        row.last_at = msg.created_at
        db.flush()
        return _msg(msg)


def owner_set_status(shop_id: str, thread_id: int, new_status: str) -> dict:
    if new_status not in CLOSED_STATES:
        raise ValueError("status")
    with get_sessionmaker()() as db, db.begin():
        row = _owned_thread(db, shop_id, thread_id)
        row.status = new_status
        row.owner_unread = 0
        return {"id": row.id, "status": row.status}


def purge(now: Optional[datetime.datetime] = None) -> int:
    """마지막 글 뒤 30일 지난 대화 삭제(글은 cascade)."""
    cutoff = (now or _now()) - datetime.timedelta(days=KEEP_DAYS)
    with get_sessionmaker()() as db, db.begin():
        return db.execute(delete(GuestChatThreadRow).where(GuestChatThreadRow.last_at < cutoff)).rowcount
