"""생성 사이트의 "예약 신청" (플랫폼 공용 ② 예약·신청 받기, DECISIONS D31·D32, docs/product/BOOKING_PLAN.md).

손님이 폼을 보내면 공용 DB(bookings)에 저장하고, 그 사이트를 만든 채팅방과 사장님 카톡에 알린다.
사장님은 채팅방에서 확정·거절한다(방장만). 손님에게는 우리가 보내지 않고 사장님이 연락한다(1단계).
- 스팸: 숨김 칸(website)이 채워졌으면 저장하지 않고 성공처럼 보인다(문의와 같다).
- 보관: 방문일 + RETENTION_DAYS 뒤 지운다(폼 안내문과 같은 값).
"""
import datetime
import logging
import re
from typing import Optional

from sqlalchemy import delete, func, select

from app import store
from app.db.models import BookingRow, RoomRow, SessionRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token
from app.services import availability, customers, rooms
from app.services.inquiries import _PHONE, _clean, site_exists

log = logging.getLogger(__name__)

RETENTION_DAYS = 30
MAX_AHEAD_DAYS = 60
MAX_PARTY = 20
MAX_NAME, MAX_PHONE, MAX_SERVICE, MAX_MEMO = 40, 20, 60, 300
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
STATUSES = ("requested", "confirmed", "declined")


class BookingError(Exception):
    """손님에게 보여 줄 한 줄 사유."""


class NotFound(Exception):
    pass


class AlreadyDecided(Exception):
    pass


class SlotFull(Exception):
    """확정하려는 시간이 이미 마감됨. 상태는 requested 그대로 둔다."""


def _today() -> datetime.date:
    # 가게·손님이 한국이라 한국 날짜로 판단한다(서버 시간대와 무관하게).
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=9)).date()


def submit(site_key: str, date: Optional[str], time: Optional[str], service: Optional[str], party: Optional[str],
           name: Optional[str], phone: Optional[str], memo: Optional[str], agree: Optional[str],
           website: Optional[str]) -> bool:
    """저장했으면 True, 스팸으로 조용히 버렸으면 False. 입력이 틀리면 BookingError."""
    key = sanitize_token(site_key or "")
    if not key or not site_exists(key):
        raise BookingError("사이트를 찾을 수 없어요.")
    if website:
        return False
    try:
        visit = datetime.date.fromisoformat((date or "").strip())
    except ValueError:
        raise BookingError("방문 날짜를 골라 주세요.")
    today = _today()
    if not today <= visit <= today + datetime.timedelta(days=MAX_AHEAD_DAYS):
        raise BookingError(f"방문 날짜는 오늘부터 {MAX_AHEAD_DAYS}일 안에서 골라 주세요.")
    time_c = (time or "").strip()
    if time_c and not _TIME.match(time_c):
        raise BookingError("방문 시간을 다시 골라 주세요.")
    try:
        party_n = int((party or "1").strip())
    except ValueError:
        raise BookingError("인원은 숫자로 적어 주세요.")
    if not 1 <= party_n <= MAX_PARTY:
        raise BookingError(f"인원은 1명부터 {MAX_PARTY}명까지 신청할 수 있어요.")
    phone_c = _clean(phone, MAX_PHONE)
    if not phone_c or not _PHONE.match(phone_c):
        raise BookingError("연락받을 전화번호를 적어 주세요.")
    if agree != "yes":
        raise BookingError("개인정보 수집·이용에 동의해 주세요.")
    name_c, service_c, memo_c = _clean(name, MAX_NAME), _clean(service, MAX_SERVICE), _clean(memo, MAX_MEMO)
    with get_sessionmaker()() as db, db.begin():
        if availability.slot_taken(db, key, visit, time_c, service_c):
            raise BookingError("이미 마감된 시간이에요. 다른 시간을 골라 주세요.")
        cid = customers.touch(db, key, phone_c, name_c)
        hist = customers.history(db, cid) if cid else None
        row = BookingRow(site_key=key, visit_date=visit, visit_time=time_c, service=service_c or None, party=party_n,
                         name=name_c or None, phone=phone_c, memo=memo_c or None, customer_id=cid)
        db.add(row)
        db.flush()
        booking_id = row.id
        room_id = db.scalar(select(RoomRow.id).join(SessionRow, RoomRow.session_id == SessionRow.id)
                            .where(SessionRow.requirement_id == key))
    line = customers.visit_line(hist) if hist is not None else None
    from app.services import design_log
    design_log.inquiry(key)  # D45: 공개 뒤 받은 문의·예약 수(내용·연락처는 남기지 않음)
    if room_id:
        text = _summary(visit, time_c, service_c, party_n, name_c, phone_c, memo_c)
        if line:
            text = text + "\n" + line
        _notify_room(room_id, booking_id, "사이트로 새 예약 신청이 왔어요.\n" + text
                     + f"\n확정·거절을 눌러 주시고 손님께 연락해 주세요. (방문일 {RETENTION_DAYS}일 뒤 자동으로 지워져요)")
        from app.services import notify
        notify.owner_kakao(room_id, "사이트로 새 예약 신청이 왔어요.\n" + text + "\n채팅방에서 확정·거절해 주세요.")
    return True


_WEEKDAYS = "월화수목금토일"


def _summary(visit, time_c, service_c, party_n, name_c, phone_c, memo_c) -> str:
    when = f"{visit.month}월 {visit.day}일({_WEEKDAYS[visit.weekday()]})" + (f" {time_c}" if time_c else "")
    lines = [f"날짜: {when}", f"인원: {party_n}명"]
    if service_c:
        lines.append(f"메뉴: {service_c}")
    lines += [f"이름: {name_c or '(적지 않음)'}", f"연락처: {phone_c}"]
    if memo_c:
        lines.append(f"메모: {memo_c}")
    return "\n".join(lines)


def _notify_room(room_id: str, booking_id: int, text: str) -> None:
    try:
        with store.room_tx(room_id) as (room, _session):
            if room is not None:
                rooms._append(room, "system", "예약 알림", text, kind="booking",
                              meta={"booking_id": booking_id, "status": "requested"})
    except Exception:
        # 알림이 실패해도 예약 저장은 이미 끝났다. 손님에게는 성공으로 보인다.
        log.exception("예약 알림 실패 room=%s", room_id)


def _owner_site_key(room_id: str, member_id_raw) -> str:
    """방장이면 그 방이 만든 사이트 키. 방이 없으면 NotFound, 방장이 아니면 rooms.NotOwner."""
    room = store.read_room(rooms._room_id(room_id))
    if room is None:
        raise NotFound()
    if rooms.owner_id(room) != sanitize_token(member_id_raw or ""):
        raise rooms.NotOwner()
    with get_sessionmaker()() as db:
        key = db.scalar(select(SessionRow.requirement_id).where(SessionRow.id == room["session_id"]))
    if not key:
        raise NotFound()
    return key


def list_for_room(room_id: str, member_id_raw) -> list[dict]:
    """방장이 보는 예약 상태 목록(새로고침 뒤 버튼 복원용). 최근 200건."""
    key = _owner_site_key(room_id, member_id_raw)
    with get_sessionmaker()() as db:
        rows = db.execute(select(BookingRow.id, BookingRow.status).where(BookingRow.site_key == key)
                          .order_by(BookingRow.id.desc()).limit(200)).all()
    return [{"id": r.id, "status": r.status} for r in rows]


def decide(room_id: str, member_id_raw, booking_id: int, decision: str) -> dict:
    """방장이 확정·거절. 이미 결정된 것은 AlreadyDecided."""
    status = {"confirm": "confirmed", "decline": "declined"}.get(decision)
    if status is None:
        raise rooms.InvalidRequest("decision은 confirm 또는 decline이에요.")
    key = _owner_site_key(room_id, member_id_raw)
    with get_sessionmaker()() as db, db.begin():
        row = db.scalar(select(BookingRow).where(BookingRow.id == booking_id, BookingRow.site_key == key)
                        .with_for_update())
        if row is None:
            raise NotFound()
        if row.status != "requested":
            raise AlreadyDecided()
        if status == "confirmed":
            db.execute(select(func.pg_advisory_xact_lock(func.hashtext(row.site_key + ":" + row.visit_date.isoformat()))))
            if availability.slot_taken(db, row.site_key, row.visit_date, row.visit_time, row.service):
                raise SlotFull()
        row.status = status
        row.decided_at = datetime.datetime.now(datetime.timezone.utc)
        when = f"{row.visit_date.month}월 {row.visit_date.day}일" + (f" {row.visit_time}" if row.visit_time else "")
        who = row.name or row.phone
    word = "확정했어요" if status == "confirmed" else "거절했어요"
    try:
        with store.room_tx(rooms._room_id(room_id)) as (room, _session):
            if room is not None:
                rooms._append(room, "system", "예약 알림", f"{when} {who}님 예약을 {word}. 손님께 연락해 주세요.",
                              kind="booking_result", meta={"booking_id": booking_id, "status": status})
    except Exception:
        log.exception("예약 결과 알림 실패 room=%s", room_id)
    try:
        # J7: 상태를 바꾼 뒤 공개돼 있으면 공개본을 다시 그린다 (실패해도 decide 결과는 그대로)
        room = store.read_room(rooms._room_id(room_id))
        card = None
        if room is not None:
            session = store.read_session(room["session_id"])
            card = (session or {}).get("prd")
        if isinstance(card, dict) and card.get("published"):
            from app.services import design as design_module
            design_module.publish_choice(key, card, card["published"])
    except Exception:
        log.exception("예약 확정·거절 뒤 공개본 다시 그리기 실패 room=%s", room_id)
    return {"id": booking_id, "status": status}


def purge_expired(today: Optional[datetime.date] = None) -> int:
    cutoff = (today or _today()) - datetime.timedelta(days=RETENTION_DAYS)
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(BookingRow).where(BookingRow.visit_date < cutoff)).rowcount
    if n:
        log.info("예약 %d건 삭제 (방문일 %d일 경과)", n, RETENTION_DAYS)
    return n
