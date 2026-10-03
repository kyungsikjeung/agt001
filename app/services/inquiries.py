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
from app.services import customers, rooms

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
    from app.services import takedown
    if takedown.is_down(key):  # 관리자가 내린 사이트는 문의·예약을 받지 않는다 (P2-4)
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
        cid, hist = None, None
        if customers.normalize_phone(contact_c) is not None:
            cid = customers.touch(db, key, contact_c, name_c)
            hist = customers.history(db, cid) if cid else None
        db.add(InquiryRow(site_key=key, name=name_c or None, contact=contact_c, message=message_c,
                          customer_id=cid))
        room_id = db.scalar(select(RoomRow.id).join(SessionRow, RoomRow.session_id == SessionRow.id)
                            .where(SessionRow.requirement_id == key))
    line = customers.visit_line(hist) if hist is not None else None
    from app.services import design_log
    design_log.inquiry(key)  # D45: 공개 뒤 문의 수(내용·연락처는 남기지 않음)
    if room_id:
        _notify_room(room_id, name_c, contact_c, message_c, line)
        # 사장님 카톡 알림(켜져 있으면). 연락처는 카톡에도 보인다(사장님 본인에게만 가는 메모).
        from app.services import notify
        notify.owner_kakao(room_id, f"사이트로 새 문의가 왔어요.\n이름: {name_c or '(적지 않음)'}\n연락처: {contact_c}\n내용: {message_c[:120]}"
                           + (f"\n{line}" if line else ""))
    return True


def submit_rsvp(site_key: str, name: Optional[str], side: Optional[str], attend: Optional[str],
                count: Optional[str], meal: Optional[str], contact: Optional[str], message: Optional[str],
                agree: Optional[str], website: Optional[str]) -> bool:
    """청첩장 참석 여부 (EVENT_INVITE_PLAN). 문의 저장소에 '[참석 여부] …' 한 줄로 넣어
    사장님 알림·목록·보관 기간을 그대로 쓴다. 연락처는 선택. 저장했으면 True, 스팸이면 False."""
    key = sanitize_token(site_key or "")
    if not key or not site_exists(key):
        raise InquiryError("사이트를 찾을 수 없어요.")
    if website:
        return False
    name_c = _clean(name, MAX_NAME)
    contact_c = _clean(contact, MAX_CONTACT)
    note = _clean(message, 300)
    if not name_c:
        raise InquiryError("이름을 적어 주세요.")
    if attend not in ("yes", "no"):
        raise InquiryError("참석·불참을 골라 주세요.")
    if contact_c and not (_PHONE.match(contact_c) or _EMAIL.match(contact_c)):
        raise InquiryError("연락처는 전화번호나 이메일로 적어 주세요.")
    if agree != "yes":
        raise InquiryError("개인정보 수집·이용에 동의해 주세요.")
    try:
        people = max(1, min(int(count or 1), 20))
    except ValueError:
        people = 1
    parts = [_clean(side, 10)] if _clean(side, 10) in ("신랑측", "신부측") else []
    parts.append(f"참석 · {people}명" if attend == "yes" else "불참")
    if attend == "yes" and meal in ("yes", "no"):
        parts.append("식사함" if meal == "yes" else "식사 안 함")
    text = RSVP_PREFIX + " · ".join(parts) + (f"\n{note}" if note else "")
    with get_sessionmaker()() as db, db.begin():
        db.add(InquiryRow(site_key=key, name=name_c, contact=contact_c, message=text))
        room_id = db.scalar(select(RoomRow.id).join(SessionRow, RoomRow.session_id == SessionRow.id)
                            .where(SessionRow.requirement_id == key))
    if room_id:
        _notify_room(room_id, name_c, contact_c or "(적지 않음)", text)
        from app.services import notify
        notify.owner_kakao(room_id, f"청첩장에 참석 여부가 왔어요.\n{name_c}: {text[8:120]}")
    return True


RSVP_PREFIX = "[참석 여부] "
_RSVP_COUNT = re.compile(r"참석 · (\d+)명")


def rsvp_summary(site_key: str) -> dict:
    """참석 여부 집계 (빌더 '참석 여부' 칸). submit_rsvp가 쓴 한 줄 형식을 읽는다(최신순).
    {entries: [{id, name, side, attend, count, meal, note, contact, ts}], total: {...}, sides: {측: 참석 인원}}"""
    key = sanitize_token(site_key or "")
    entries = []
    if key:
        with get_sessionmaker()() as db:
            rows = db.scalars(select(InquiryRow).where(InquiryRow.site_key == key,
                                                       InquiryRow.message.startswith(RSVP_PREFIX))
                              .order_by(InquiryRow.id.desc()).limit(500)).all()
            for r in rows:
                head, _, note = r.message[len(RSVP_PREFIX):].partition("\n")
                parts = head.split(" · ")
                side = parts[0] if parts and parts[0] in ("신랑측", "신부측") else ""
                attend = "불참" not in parts
                found = _RSVP_COUNT.search(head)
                entries.append({"id": r.id, "name": r.name or "", "side": side, "attend": attend,
                                "count": int(found.group(1)) if attend and found else 0,
                                "meal": "식사함" in parts, "note": note.strip(), "contact": r.contact or "",
                                "ts": r.ts.isoformat() if r.ts else ""})
    coming = [e for e in entries if e["attend"]]
    sides: dict = {}
    for e in coming:
        if e["side"]:
            sides[e["side"]] = sides.get(e["side"], 0) + e["count"]
    total = {"replies": len(entries), "people": sum(e["count"] for e in coming),
             "declined": len(entries) - len(coming), "meal": sum(e["count"] for e in coming if e["meal"])}
    return {"entries": entries, "total": total, "sides": sides}


def _notify_room(room_id: str, name: str, contact: str, message: str, line: Optional[str] = None) -> None:
    text = (f"사이트로 새 문의가 왔어요.\n이름: {name or '(적지 않음)'}\n연락처: {contact}\n내용: {message}\n"
            + (f"{line}\n" if line else "")
            + f"({RETENTION_DAYS}일 뒤 자동으로 지워져요)")
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
