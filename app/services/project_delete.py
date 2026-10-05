"""프로젝트 삭제 (대표 2026-10-05, 유예 30일로 확정 10/6).

방장이 "지우기"를 누르면 **바로 공개 사이트가 내려가고**(주문·결제·예약·채팅까지 함께 닫힌다)
목록에서는 비활성으로 남는다. 30일 안에는 "되살리기"로 돌아온다. 30일이 지나면 하루 한 번 도는
청소(purge_deleted)가 방·세션·가게와 딸린 기록을 **모두** 지운다(카스케이드).

왜 바로 지우지 않나: 잘못 누르면 되돌릴 수 없다. 공개된 개인정보처리방침 3항이 "방장이 삭제한 방 →
즉시 숨김 → 30일 뒤 영구 삭제(30일 안 복구 가능)"이므로 기간을 거기에 맞춘다.

구독(우리에게 내는 요금)은 지울 때 함께 해지한다. 포트원이 우리 cron 없이 스스로 결제하므로
예약 결제를 취소하지 않으면 지운 뒤에도 카드가 계속 긁힌다.
"""
import datetime
import logging
import shutil

from sqlalchemy import delete, select

from app.config import settings
from app.db.models import (
    AttachmentRow,
    BookingEventRow,
    BookingRow,
    ChatTurnRow,
    CouponRow,
    CustomerRow,
    GuestbookRow,
    InquiryRow,
    OrderItemRow,
    OrderRow,
    PaymentRow,
    PhoneVerificationRow,
    RefundRow,
    RoomRow,
    SessionRow,
    SettlementRow,
    ShopRow,
    ShopSettingsRow,
    StampEventRow,
    StampRuleRow,
    SubscriptionRow,
    UsageLedgerRow,
)
from app.db.session import get_sessionmaker
from app.security import sanitize_token
from app.services import payments, takedown

log = logging.getLogger(__name__)

GRACE_DAYS = 30  # 지운 뒤 되살릴 수 있는 기간(방침 3항과 같아야 한다). 지나면 영구 삭제.


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _room_row(db, room_id: str):
    return db.get(RoomRow, sanitize_token(room_id or ""))


def deleted_at(room_id: str):
    """지운 시각. 안 지웠으면 None."""
    with get_sessionmaker()() as db:
        row = _room_row(db, room_id)
        return row.deleted_at if row else None


def purge_at(when: datetime.datetime) -> datetime.datetime:
    """이 시각에 지운 방이 영구 삭제되는 때."""
    return when + datetime.timedelta(days=GRACE_DAYS)


def cancel_subscription(site_key) -> bool:
    """우리에게 내는 요금(구독)을 끊는다. 끊을 것이 없거나 다 끊으면 True.

    포트원 예약 결제는 **우리 cron 없이 포트원이 때가 되면 스스로 결제한다**(PAYMENT_PLAN §4).
    그래서 ① 포트원에 걸린 예약을 취소하고 ② 우리가 가진 빌링키를 지운다. 둘 중 하나라도
    빠지면 지운 프로젝트에서 다음 달 요금이 계속 빠져나간다.

    포트원 취소가 실패해도 우리 쪽은 해지로 두고 운영에 알린다(사람이 포트원 콘솔에서 지워야 한다).
    """
    key = sanitize_token(site_key or "")
    if not key:
        return True
    with get_sessionmaker()() as db:
        row = db.get(SubscriptionRow, key)
        schedule_id = row.next_schedule_id if row else None
        had_key = bool(row and row.billing_key_enc)
    if row is None:
        return True
    ok = payments.cancel_schedules([schedule_id] if schedule_id else [])
    with get_sessionmaker()() as db, db.begin():
        row = db.get(SubscriptionRow, key)
        if row is not None:
            row.status = "canceled"
            row.cancel_at_period_end = True
            row.billing_key_enc = None  # 카드 정보를 더 들고 있지 않는다(되살려도 다시 신청해야 한다)
            row.next_schedule_id = None
    if not ok:
        try:
            from app.services import ops_alert
            ops_alert.send("subscription_cancel_failed",
                           f"구독 해지 중 포트원 예약 결제 취소가 실패했어요. 포트원 콘솔에서 지워 주세요. "
                           f"가게 {key} 예약 {schedule_id}")
        except Exception:
            log.exception("구독 해지 실패 알림을 보내지 못함 site=%s", key)
    elif schedule_id or had_key:
        log.info("프로젝트 삭제로 구독을 해지했어요 site=%s", key)
    return ok


def soft_delete(room_id: str) -> datetime.datetime:
    """지운 것으로 표시한다. 공개 사이트는 바로 닫힌다(takedown.is_down이 함께 본다).

    이미 지운 방이면 처음 지운 시각을 그대로 둔다(누를 때마다 기간이 늘어나지 않게).
    구독은 같은 자리에서 해지한다 — 영구 삭제(30일 뒤)를 기다리면 그동안 요금이 또 빠진다.
    """
    safe = sanitize_token(room_id or "")
    with get_sessionmaker()() as db, db.begin():
        row = _room_row(db, safe)
        if row is None:
            raise LookupError(room_id)
        if row.deleted_at is None:
            row.deleted_at = _now()
        when = row.deleted_at
    site_key = site_key_of(room_id)
    takedown.mark_deleted(site_key, True)  # 공개 사이트를 바로 닫는다(주문·결제·예약·채팅 함께)
    cancel_subscription(site_key)
    return when


def restore(room_id: str) -> None:
    """되살리기. 30일이 지나 영구 삭제된 뒤에는 방이 없으므로 LookupError.

    구독은 되살리지 않는다 — 카드 정보(빌링키)를 지울 때 함께 지웠으므로 사장님이 다시 신청해야 한다.
    """
    safe = sanitize_token(room_id or "")
    with get_sessionmaker()() as db, db.begin():
        row = _room_row(db, safe)
        if row is None:
            raise LookupError(room_id)
        row.deleted_at = None
    takedown.mark_deleted(site_key_of(room_id), False)


def site_key_of(room_id: str):
    """이 방이 만든 사이트 키(= requirement_id). 없으면 None."""
    safe = sanitize_token(room_id or "")
    with get_sessionmaker()() as db:
        return db.scalar(select(SessionRow.requirement_id).join(RoomRow, RoomRow.session_id == SessionRow.id)
                         .where(RoomRow.id == safe))


# 가게(site_key)에 딸린 표. 먼저 지워야 shops 행을 지울 수 있다(외래키가 CASCADE가 아닌 것들).
# shops를 지우면 알아서 따라 지워지는 것(shop_members·shop_payout·bot_specs·booking_closures·
# agent_threads·guest_chat_threads)은 여기 없다.
# 순서가 중요하다: 가리키는 쪽(자식)을 먼저 지운다. refunds·settlements → payments → orders,
# stamp_events·coupons → orders·customers. 거꾸로 지우면 외래키 위반으로 영구 삭제가 통째로 실패한다.
_BY_SITE_KEY = (
    RefundRow, SettlementRow, OrderItemRow, PaymentRow,
    StampEventRow, CouponRow, StampRuleRow, OrderRow,
    BookingRow, InquiryRow, GuestbookRow, PhoneVerificationRow, CustomerRow,
    ShopSettingsRow, UsageLedgerRow, SubscriptionRow,
)


def _purge_one(db, room_id: str, session_id: str, site_key) -> None:
    """한 방을 통째로 지운다. 호출하는 쪽이 트랜잭션을 연다."""
    if site_key:
        db.execute(delete(BookingEventRow).where(BookingEventRow.shop_id == site_key))
        for model in _BY_SITE_KEY:
            db.execute(delete(model).where(model.site_key == site_key))
        db.execute(delete(ShopRow).where(ShopRow.site_key == site_key))
    # 대화 기록은 방·세션 둘 다로 걸린다(1:1 대화에는 방이 없다).
    db.execute(delete(ChatTurnRow).where(ChatTurnRow.room_id == room_id))
    db.execute(delete(ChatTurnRow).where(ChatTurnRow.session_id == session_id))
    db.execute(delete(AttachmentRow).where(AttachmentRow.room_id == room_id))
    # room_members·room_messages·room_votes·user_rooms·room_invites는 방을 지우면 따라 지워진다.
    db.execute(delete(RoomRow).where(RoomRow.id == room_id))
    db.execute(delete(SessionRow).where(SessionRow.id == session_id))


def _purge_files(site_key) -> None:
    """만든 사이트 파일(공개본·시안·올린 사진). 지우지 못해도 DB 삭제는 되돌리지 않는다."""
    key = sanitize_token(site_key or "")
    if not key:
        return
    path = settings.generated_dir / key
    try:
        if path.is_dir():
            shutil.rmtree(path)
    except Exception:
        log.exception("지운 프로젝트 파일을 지우지 못함 site=%s", key)


def purge_deleted(now=None) -> int:
    """지운 지 30일이 지난 방을 영구 삭제한다. 지운 방 수를 돌려준다. 하루 한 번(main._purge_all)."""
    cutoff = (now or _now()) - datetime.timedelta(days=GRACE_DAYS)
    with get_sessionmaker()() as db:
        rows = db.execute(
            select(RoomRow.id, RoomRow.session_id, SessionRow.requirement_id)
            .join(SessionRow, SessionRow.id == RoomRow.session_id)
            .where(RoomRow.deleted_at.isnot(None), RoomRow.deleted_at < cutoff)
        ).all()
    done = 0
    for room_id, session_id, site_key in rows:
        try:
            with get_sessionmaker()() as db, db.begin():
                _purge_one(db, room_id, session_id, site_key)
        except Exception:
            log.exception("지운 프로젝트를 영구 삭제하지 못함 room=%s", room_id)
            continue
        _purge_files(site_key)
        done += 1
    if done:
        log.info("지운 프로젝트 %d개를 영구 삭제했어요(유예 %d일)", done, GRACE_DAYS)
    return done
