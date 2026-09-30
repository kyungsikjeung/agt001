"""가게별 손님 명단 바탕 (CUSTOMER_PLAN §1.1·§1.2).

손님 회원가입 없이 전화번호로 손님을 잇는다. 번호는 숫자만 남겨 저장하고,
같은 가게·같은 번호는 한 손님으로 모아 마지막 이름과 방문 시각을 갱신한다.
"""
import datetime
import logging
import re
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import BookingRow, CouponRow, CustomerRow, InquiryRow, OrderRow, StampEventRow
from app.db.session import get_sessionmaker

log = logging.getLogger(__name__)

ORPHAN_DAYS = 30


def normalize_phone(raw: Optional[str]) -> Optional[str]:
    """숫자만 남긴다. 82로 시작하는 11~12자리면 앞 82를 0으로 바꾼다. 0으로 시작하는 9~11자리가 아니면 None."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("82") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    if re.fullmatch(r"0\d{8,10}", digits or ""):
        return digits
    return None


def touch(db, site_key: str, phone_raw: Optional[str], name: Optional[str]) -> Optional[int]:
    """번호가 되면 손님 한 줄을 만들고(있으면 갱신) id를 돌려준다. 안 되면 None. 부른 쪽 트랜잭션 안에서 돈다."""
    phone = normalize_phone(phone_raw)
    if not phone or not site_key:
        return None
    stmt_in = pg_insert(CustomerRow).values(site_key=site_key, phone=phone, name=name or None,
                                            first_seen=func.now(), last_seen=func.now())
    stmt = stmt_in.on_conflict_do_update(
        index_elements=["site_key", "phone"],
        set_={"last_seen": func.now(), "name": func.coalesce(stmt_in.excluded.name, CustomerRow.name)},
    ).returning(CustomerRow.id)
    return db.execute(stmt).scalar()


def history(db, customer_id: int) -> dict:
    """그 손님에 붙은 기존 예약·문의 수. 지금 넣는 행은 붙이기 전에 부르므로 빠진다."""
    n = db.scalar(select(func.count()).select_from(BookingRow)
                  .where(BookingRow.customer_id == customer_id)) or 0
    m = db.scalar(select(func.count()).select_from(InquiryRow)
                  .where(InquiryRow.customer_id == customer_id)) or 0
    return {"bookings": n, "inquiries": m}


def visit_line(hist: dict) -> str:
    """채팅방·카톡 알림 끝에 붙는 한 줄. 둘 다 0이면 첫 방문, 0인 쪽은 뺀다."""
    n = hist.get("bookings", 0) or 0
    m = hist.get("inquiries", 0) or 0
    if not n and not m:
        return "처음 오신 손님이에요."
    parts = []
    if n:
        parts.append(f"예약 {n}번")
    if m:
        parts.append(f"문의 {m}번")
    return "이 번호로 " + "·".join(parts) + " 있었어요."


def mark_verified(db, site_key: str, phone_raw: Optional[str]) -> None:
    """문자 인증을 통과한 손님에 통과 시각을 남긴다. 맞는 손님이 없으면 아무것도 안 한다."""
    phone = normalize_phone(phone_raw)
    if not phone or not site_key:
        return None
    db.execute(update(CustomerRow).where(CustomerRow.site_key == site_key, CustomerRow.phone == phone)
               .values(phone_verified_at=func.now()))
    return None


def purge_orphans(now: Optional[datetime.datetime] = None) -> int:
    """붙은 문의·예약·주문·도장·쿠폰이 하나도 없고 마지막 방문이 30일 지난 손님을 지운다.
    도장·쿠폰 표는 손님 삭제에 따라 지워지므로, 주문만 한 손님의 기록이 30일 뒤에 사라지지 않게 남긴다."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=ORPHAN_DAYS)
    with get_sessionmaker()() as db, db.begin():
        n = db.execute(delete(CustomerRow).where(
            CustomerRow.last_seen < cutoff,
            ~select(InquiryRow.id).where(InquiryRow.customer_id == CustomerRow.id).exists(),
            ~select(BookingRow.id).where(BookingRow.customer_id == CustomerRow.id).exists(),
            ~select(OrderRow.id).where(OrderRow.customer_id == CustomerRow.id).exists(),
            ~select(StampEventRow.id).where(StampEventRow.customer_id == CustomerRow.id).exists(),
            ~select(CouponRow.id).where(CouponRow.customer_id == CustomerRow.id).exists(),
        )).rowcount
    if n:
        log.info("손님 %d명 삭제 (빈 손님 %d일 경과)", n, ORPHAN_DAYS)
    return n
