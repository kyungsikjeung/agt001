"""손님 회원 (FEATURE_PLATFORM_PLAN §7.1, 10/4 대표 결정: 전화번호 인증 · 내역 보기까지만).

- 가게가 켜면(card["members"]["signup"]) 공개 사이트 메뉴에 '내 정보'가 생긴다(/api/members/<키>).
- 가입 = 번호 인증 + 동의 → customers.member_since. 다시 들어올 때도 같은 번호 인증(이 기기 90일 기억).
- 내 정보 = 이 가게에서의 내 예약·주문·스탬프·쿠폰 보기만. 바꾸기·취소는 가게에 연락.
- 탈퇴 = 회원 표시와 명단 이름을 지운다. 예약·주문 기록은 가게 보관 기간이 지나면 지워진다.
- 개인정보: 가게가 처리자, 우리는 수탁자(static/privacy.html §손님 회원).
- 인증 문자: 가게 문자 키가 있으면 가게 비용. 없으면 우리 키로 보내되 가게당 하루 DAILY_SMS_MAX건까지
  (무료 요금제에 넣는 대신 비용 상한, 결정 ③).
"""
import datetime
from typing import Optional

from sqlalchemy import func, select, update

from app.db.models import BookingRow, CustomerRow, OrderItemRow, OrderRow, PhoneVerificationRow
from app.db.session import get_sessionmaker
from app.services import customers

DAILY_SMS_MAX = 30
BOOKING_STATUS = {"requested": "확인 중", "confirmed": "확정", "declined": "거절", "cancelled": "취소", "no_show": "노쇼"}
ORDER_STATUS = {"open": "결제 전", "paid": "결제 완료", "completed": "받아 감", "canceled": "취소", "no_show": "안 받아 감"}
LIST_MAX = 20


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def enabled(card: Optional[dict]) -> bool:
    m = (card or {}).get("members")
    return isinstance(m, dict) and m.get("signup") is True


def state(card: Optional[dict]) -> Optional[dict]:
    """빌더용: 아직 안 정했으면 None(첫 화면에서 묻는다), 정했으면 {signup, method}."""
    m = (card or {}).get("members")
    if not isinstance(m, dict):
        return None
    return {"signup": m.get("signup") is True, "method": "phone"}


def set_enabled(card: dict, on: bool) -> bool:
    """켜기·끄기(정했다는 표시도 남긴다). 바뀌면 True."""
    new = {"signup": bool(on), "method": "phone"}
    if card.get("members") == new:
        return False
    card["members"] = new
    return True


def sms_quota_ok(site_key: str) -> bool:
    """우리 문자 키로 보낼 때만 가게당 하루 상한을 본다(가게 키면 가게 비용이라 상한 없음).
    오늘 인증을 통과한 손님 수 + 아직 남은 인증 요청 수로 센다."""
    from app.services import shop_settings
    try:
        if shop_settings.sms_credentials(site_key):
            return True
    except Exception:
        pass
    since = _now() - datetime.timedelta(days=1)
    with get_sessionmaker()() as db:
        done = db.scalar(select(func.count()).select_from(CustomerRow).where(
            CustomerRow.site_key == site_key, CustomerRow.phone_verified_at > since)) or 0
        pending = db.scalar(select(func.count()).select_from(PhoneVerificationRow).where(
            PhoneVerificationRow.site_key == site_key, PhoneVerificationRow.created_at > since)) or 0
    return done + pending < DAILY_SMS_MAX


def join(site_key: str, phone_raw: str) -> bool:
    """번호 인증을 통과한 손님을 회원으로(이미 회원이면 그대로). 새로 가입했으면 True."""
    phone = customers.normalize_phone(phone_raw)
    if not phone:
        return False
    with get_sessionmaker()() as db, db.begin():
        customers.touch(db, site_key, phone, None)
        customers.mark_verified(db, site_key, phone)
        n = db.execute(update(CustomerRow).where(
            CustomerRow.site_key == site_key, CustomerRow.phone == phone, CustomerRow.member_since.is_(None))
            .values(member_since=func.now())).rowcount
    return n > 0


def is_member(site_key: str, phone: Optional[str]) -> bool:
    if not phone:
        return False
    with get_sessionmaker()() as db:
        return db.scalar(select(CustomerRow.id).where(
            CustomerRow.site_key == site_key, CustomerRow.phone == phone,
            CustomerRow.member_since.isnot(None))) is not None


def leave(site_key: str, phone: Optional[str]) -> bool:
    """탈퇴: 회원 표시와 명단 이름을 지운다."""
    if not phone:
        return False
    with get_sessionmaker()() as db, db.begin():
        return db.execute(update(CustomerRow).where(
            CustomerRow.site_key == site_key, CustomerRow.phone == phone, CustomerRow.member_since.isnot(None))
            .values(member_since=None, name=None)).rowcount > 0


def history(site_key: str, phone: str) -> Optional[dict]:
    """내 정보: 이 가게에서의 내 예약·주문(최근 20개)·스탬프. 회원이 아니면 None."""
    from app.services import stamps
    with get_sessionmaker()() as db:
        cust = db.scalar(select(CustomerRow).where(
            CustomerRow.site_key == site_key, CustomerRow.phone == phone, CustomerRow.member_since.isnot(None)))
        if cust is None:
            return None
        bookings = db.scalars(select(BookingRow).where(
            BookingRow.site_key == site_key, BookingRow.customer_id == cust.id)
            .order_by(BookingRow.visit_date.desc(), BookingRow.visit_time.desc()).limit(LIST_MAX)).all()
        order_rows = db.scalars(select(OrderRow).where(
            OrderRow.site_key == site_key, OrderRow.customer_id == cust.id)
            .order_by(OrderRow.created_at.desc()).limit(LIST_MAX)).all()
        items: dict[int, list] = {}
        if order_rows:
            for it in db.scalars(select(OrderItemRow).where(OrderItemRow.order_id.in_([o.id for o in order_rows]))).all():
                items.setdefault(it.order_id, []).append(f"{it.name} {it.qty}개" if it.qty > 1 else it.name)
        rule = stamps.rule(site_key)
        stamp = None
        if rule is not None:
            stamp = {"balance": stamps.balance(db, site_key, cust.id), "goal": rule["goal"],
                     "coupons": [c.get("title") or "" for c in stamps.usable(db, site_key, cust.id)]}
        return {
            "since": cust.member_since,
            "bookings": [{"date": b.visit_date.isoformat(), "time": b.visit_time, "service": b.service or "",
                          "party": b.party, "status": BOOKING_STATUS.get(b.status, b.status)} for b in bookings],
            "orders": [{"at": o.created_at, "items": ", ".join(items.get(o.id, []))[:80], "total": o.total,
                        "status": ORDER_STATUS.get(o.status, o.status)} for o in order_rows],
            "stamps": stamp,
        }


def owner_list(site_key: str) -> list[dict]:
    """사장님 '손님' 탭: 회원 목록(번호 가운데 가림·가입일·마지막 방문·예약·주문 수)."""
    with get_sessionmaker()() as db:
        rows = db.scalars(select(CustomerRow).where(
            CustomerRow.site_key == site_key, CustomerRow.member_since.isnot(None))
            .order_by(CustomerRow.last_seen.desc()).limit(500)).all()
        out = []
        for c in rows:
            n_book = db.scalar(select(func.count()).select_from(BookingRow).where(BookingRow.customer_id == c.id)) or 0
            n_order = db.scalar(select(func.count()).select_from(OrderRow).where(OrderRow.customer_id == c.id)) or 0
            out.append({"name": c.name or "", "phone": mask(c.phone), "since": kst_date(c.member_since),
                        "last_seen": kst_date(c.last_seen), "bookings": n_book, "orders": n_order})
        return out


KST = datetime.timezone(datetime.timedelta(hours=9))


def kst_date(dt: Optional[datetime.datetime]) -> str:
    """한국 날짜 YYYY-MM-DD (손님 화면·사장님 화면이 같은 날짜를 보이게)."""
    return dt.astimezone(KST).strftime("%Y-%m-%d") if dt else ""


def mask(phone: str) -> str:
    """010-****-5678 (가운데 가림)."""
    d = phone or ""
    if len(d) < 8:
        return "****"
    return f"{d[:3]}-****-{d[-4:]}"
