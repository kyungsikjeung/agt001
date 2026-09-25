"""생성 사이트의 "문의하기" (플랫폼 공용 ①, DECISIONS.md D31·D32, templates/README.md §5).

사이트 방문자가 폼을 보내면 저장하고, 그 사이트를 만든 채팅방에 알린다. 가게(방 참여자)가 받는 사람이다.
- 스팸: 숨김 칸(website)이 채워졌으면 저장하지 않고 성공처럼 보인다.
- 보관: RETENTION_DAYS 뒤 지운다(폼 안내문과 같은 값).
"""
import datetime
import logging
import re
from typing import Optional

from sqlalchemy import delete, select

from app import store
from app.db.models import InquiryRow, RoomRow, SessionRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token
from app.services import rooms

log = logging.getLogger(__name__)

RETENTION_DAYS = 30
MAX_NAME, MAX_CONTACT, MAX_MESSAGE = 40, 100, 1000
_PHONE = re.compile(r"^[0-9+\-\s()]{8,20}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class InquiryError(Exception):
    """방문자에게 보여 줄 한 줄 사유."""


def _clean(value: Optional[str], limit: int) -> str:
    # 제어 문자를 지우고 공백을 정리한다. 채팅방에 그대로 보이므로 줄바꿈만 남긴다.
    text = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", value or "")
    return text.strip()[:limit]


def site_exists(site_key: str) -> bool:
    key = sanitize_token(site_key or "")
    if not key:
        return False
    with get_sessionmaker()() as db:
        return db.scalar(select(SessionRow.id).where(SessionRow.requirement_id == key)) is not None


def submit(site_key: str, name: Optional[str], contact: Optional[str], message: Optional[str],
           agree: Optional[str], website: Optional[str]) -> bool:
    """저장했으면 True, 스팸으로 조용히 버렸으면 False. 입력이 틀리면 InquiryError."""
    key = sanitize_token(site_key or "")
    if not key or not site_exists(key):
        raise InquiryError("사이트를 찾을 수 없어요.")
    if website:
        return False
    name_c = _clean(name, MAX_NAME)
    contact_c = _clean(contact, MAX_CONTACT)
    message_c = _clean(message, MAX_MESSAGE)
    if not contact_c or not (_PHONE.match(contact_c) or _EMAIL.match(contact_c)):
        raise InquiryError("연락처는 전화번호나 이메일로 적어 주세요.")
    if not message_c:
        raise InquiryError("문의 내용을 적어 주세요.")
    if agree != "yes":
        raise InquiryError("개인정보 수집·이용에 동의해 주세요.")
    with get_sessionmaker()() as db, db.begin():
        db.add(InquiryRow(site_key=key, name=name_c or None, contact=contact_c, message=message_c))
        room_id = db.scalar(select(RoomRow.id).join(SessionRow, RoomRow.session_id == SessionRow.id)
                            .where(SessionRow.requirement_id == key))
    if room_id:
        _notify_room(room_id, name_c, contact_c, message_c)
    return True


def _notify_room(room_id: str, name: str, contact: str, message: str) -> None:
    text = (f"사이트로 새 문의가 왔어요.\n이름: {name or '(적지 않음)'}\n연락처: {contact}\n내용: {message}\n"
            f"({RETENTION_DAYS}일 뒤 자동으로 지워져요)")
    try:
        with store.room_tx(room_id) as (room, _session):
            if room is not None:
                rooms._append(room, "system", "문의 알림", text, kind="inquiry")
    except Exception:
        # 알림이 실패해도 문의 저장은 이미 끝났다. 방문자에게는 성공으로 보인다.
        log.exception("문의 알림 실패 room=%s", room_id)


def purge_expired(now: Optional[datetime.datetime] = None) -> int:
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=RETENTION_DAYS)
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(InquiryRow).where(InquiryRow.ts < cutoff)).rowcount
    if n:
        log.info("문의 %d건 삭제 (%d일 경과)", n, RETENTION_DAYS)
    return n
