"""예약 엔진 (BOOKING_BOT_IMPL_PLAN BOOK-1~BOOK-8, SPEC-3).

명세를 켠 가게만 이 엔진을 쓴다. 명세가 없는 가게는 bookings.submit·availability 옛 경로 그대로(BOOK-7).
- 가능 시각은 slots.find만 정한다. 저장 직전에 같은 트랜잭션 안에서 다시 계산한다.
- 가게·날짜 advisory 잠금으로 줄을 세우고, 담당자 겹침은 배제 제약이 한 번 더 막는다.
- 상태: held(10분) → requested/confirmed → cancelled·declined·no_show·expired.
"""
import datetime
import logging
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError

from app.db.models import BookingClosureRow, BookingEventRow, BookingRow, BotSpecRow, RoomRow, SessionRow, ShopRow
from app.db.session import get_sessionmaker
from app.services import booking_spec as S
from app.services import customers, shops, slots
from app.services.slots import KST

log = logging.getLogger(__name__)

HOLD_MIN = 10
BLOCKING = ("held", "requested", "confirmed")


class EngineError(Exception):
    """손님·사장님에게 보여 줄 한 줄 사유."""


class SlotTaken(EngineError):
    pass


class HoldExpired(EngineError):
    pass


class NotFound(EngineError):
    pass


class DeadlinePassed(EngineError):
    pass


class NotAllowed(EngineError):
    pass


def _now() -> datetime.datetime:
    return datetime.datetime.now(KST)


def _event(db, row: BookingRow, actor: str, action: str, detail: Optional[dict] = None) -> None:
    db.add(BookingEventRow(booking_id=row.id, shop_id=row.shop_id or 0, actor=actor, action=action, detail=detail))


# ── 명세 판 (SPEC-3) ──

def _spec_row(db, shop_id: int, status: str) -> Optional[BotSpecRow]:
    return db.scalar(select(BotSpecRow).where(BotSpecRow.shop_id == shop_id, BotSpecRow.status == status))


def get_spec(shop_id: int, status: str = "active") -> Optional[dict]:
    with get_sessionmaker()() as db:
        row = _spec_row(db, shop_id, status)
        return {"id": row.id, "version": row.version, "spec": row.spec} if row else None


def active_spec(site_key: str) -> Optional[tuple[int, dict]]:
    """(shop_id, 명세) — 명세를 켠 가게만."""
    shop_id = shops.shop_id_for(site_key)
    if shop_id is None:
        return None
    got = get_spec(shop_id)
    return (shop_id, got["spec"]) if got else None


def save_draft(shop_id: int, spec: dict, user_id: Optional[str]) -> int:
    """draft 판을 저장(없으면 새 판 번호로 만든다). 판 ID."""
    with get_sessionmaker()() as db, db.begin():
        row = _spec_row(db, shop_id, "draft")
        if row is None:
            version = (db.scalar(select(func.max(BotSpecRow.version)).where(BotSpecRow.shop_id == shop_id)) or 0) + 1
            row = BotSpecRow(shop_id=shop_id, version=version, spec=spec, status="draft", created_by=user_id)
            db.add(row)
        else:
            row.spec = spec
        db.flush()
        return row.id


def activate(shop_id: int, user_id: Optional[str], spec_id: Optional[int] = None) -> dict:
    """draft(또는 지정한 옛 판)를 켠다. 검증 문제가 있으면 EngineError. 되돌리기 = 옛 판 ID로 부르기."""
    with get_sessionmaker()() as db, db.begin():
        row = db.get(BotSpecRow, spec_id) if spec_id else _spec_row(db, shop_id, "draft")
        if row is None or row.shop_id != shop_id:
            raise NotFound("켤 설정이 없어요.")
        problems = S.validate(row.spec)
        if problems:
            raise EngineError(problems[0]["msg"])
        current = _spec_row(db, shop_id, "active")
        if current is not None and current.id != row.id:
            current.status = "archived"
            db.flush()
        row.status = "active"
        return {"id": row.id, "version": row.version}


def deactivate(shop_id: int) -> None:
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(BotSpecRow).where(BotSpecRow.shop_id == shop_id, BotSpecRow.status == "active")
                   .values(status="archived"))


# ── 읽기 ──

def _expire(db, shop_id: int, spec: dict, now: datetime.datetime) -> None:
    """지난 hold → expired. 사장님이 hold_hours 동안 결정하지 않은 신청도 자리를 푼다(B3)."""
    db.execute(update(BookingRow).where(BookingRow.shop_id == shop_id, BookingRow.status == "held",
                                        BookingRow.hold_expires_at < now).values(status="expired"))
    hours = int(S.policy(spec)["hold_hours"])
    stale = db.scalars(select(BookingRow).where(
        BookingRow.shop_id == shop_id, BookingRow.status == "requested",
        BookingRow.ts < now - datetime.timedelta(hours=hours))).all()
    for row in stale:
        row.status = "expired"
        _event(db, row, "system", "expired", {"after_hours": hours})


def _day_range(day: datetime.date):
    start = datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=KST)
    return start, start + datetime.timedelta(days=1)


def _busy(db, shop_id: int, day: datetime.date, exclude_id: Optional[int] = None) -> list[dict]:
    a, b = _day_range(day)
    q = select(BookingRow.id, BookingRow.resource_key, BookingRow.start_at, BookingRow.end_at, BookingRow.party).where(
        BookingRow.shop_id == shop_id, BookingRow.status.in_(BLOCKING),
        BookingRow.start_at < b, BookingRow.end_at > a)
    return [{"resource_key": r.resource_key, "start": r.start_at, "end": r.end_at, "party": r.party}
            for r in db.execute(q).all() if r.id != exclude_id]


def _closures(db, shop_id: int, day: datetime.date) -> list[dict]:
    a, b = _day_range(day)
    rows = db.execute(select(BookingClosureRow.resource_key, BookingClosureRow.start_at, BookingClosureRow.end_at)
                      .where(BookingClosureRow.shop_id == shop_id, BookingClosureRow.start_at < b,
                             BookingClosureRow.end_at > a)).all()
    return [{"resource_key": r.resource_key, "start": r.start_at, "end": r.end_at} for r in rows]


def _require_spec(site_key: str) -> tuple[int, dict]:
    got = active_spec(site_key)
    if got is None:
        raise NotFound("이 가게는 아직 채팅 예약을 받지 않아요.")
    return got


def available(site_key: str, day: datetime.date, *, service: Optional[str] = None, staff: Optional[str] = None,
              party: int = 1, now: Optional[datetime.datetime] = None) -> list[dict]:
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    with get_sessionmaker()() as db, db.begin():
        _expire(db, shop_id, spec, now)
        return slots.find(spec, day, service=service, staff=staff, party=party,
                          busy=_busy(db, shop_id, day), closures=_closures(db, shop_id, day), now=now)


def next_days(site_key: str, day: datetime.date, *, count: int = 3, now: Optional[datetime.datetime] = None,
              **kw) -> list[dict]:
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    out, d = [], day
    with get_sessionmaker()() as db:
        for _ in range(int(S.policy(spec)["max_days"]) + 1):
            found = slots.find(spec, d, busy=_busy(db, shop_id, d), closures=_closures(db, shop_id, d), now=now, **kw)
            if found:
                out.append({"date": d, "first": found[0]["time"]})
                if len(out) >= count:
                    break
            d += datetime.timedelta(days=1)
    return out


# ── 쓰기 ──

def _place(db, shop_id: int, site_key: str, spec: dict, day: datetime.date, time: str, *, service, staff, party,
           now, status, source, token_hash=None, exclude_id=None, **fields) -> BookingRow:
    """잠금 안에서 다시 계산해 그 시각이 되면 저장. 안 되면 SlotTaken."""
    db.execute(select(func.pg_advisory_xact_lock(func.hashtext(f"bk:{shop_id}:{day.isoformat()}"))))
    _expire(db, shop_id, spec, now)
    found = slots.find(spec, day, service=service, staff=staff, party=party,
                       busy=_busy(db, shop_id, day, exclude_id), closures=_closures(db, shop_id, day), now=now)
    pick = next((f for f in found if f["time"] == time), None)
    if pick is None:
        raise SlotTaken("그 시간은 이미 찼거나 받을 수 없어요. 다른 시간을 골라 주세요.")
    staff_name = next((r.get("name") for r in S.staff(spec) if r.get("key") == pick["resource_key"]), None)
    label = " · ".join(v for v in (service, staff_name) if v)
    row = BookingRow(site_key=site_key, shop_id=shop_id, visit_date=day, visit_time=time, service=label or None,
                     party=party, status=status, source=source, start_at=pick["start"], end_at=pick["end"],
                     resource_key=pick["resource_key"], chat_token_hash=token_hash,
                     phone=fields.pop("phone", "") or "", **fields)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        raise SlotTaken("방금 다른 분이 그 시간을 예약했어요. 다른 시간을 골라 주세요.")
    return row


def hold(site_key: str, day: datetime.date, time: str, *, service: Optional[str] = None,
         staff: Optional[str] = None, party: int = 1, token_hash: Optional[str] = None,
         now: Optional[datetime.datetime] = None) -> int:
    """10분 동안 자리를 잡는다(BOOK-4). 예약 ID."""
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    with get_sessionmaker()() as db, db.begin():
        row = _place(db, shop_id, site_key, spec, day, time, service=service, staff=staff, party=party, now=now,
                     status="held", source="chat", token_hash=token_hash,
                     hold_expires_at=now + datetime.timedelta(minutes=HOLD_MIN))
        _event(db, row, "customer", "held")
        return row.id


def _status_after(spec: dict) -> str:
    return "confirmed" if S.policy(spec).get("auto_confirm") else "requested"


def confirm_hold(site_key: str, booking_id: int, token_hash: Optional[str], *, name: Optional[str],
                 phone: str, memo: Optional[str] = None, now: Optional[datetime.datetime] = None) -> dict:
    """잡아 둔 자리에 이름·번호를 붙여 신청(또는 자동 확정)."""
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    if not customers.normalize_phone(phone):
        raise EngineError("연락받을 전화번호를 다시 적어 주세요.")
    with get_sessionmaker()() as db, db.begin():
        row = db.scalar(select(BookingRow).where(BookingRow.id == booking_id, BookingRow.shop_id == shop_id)
                        .with_for_update())
        if row is None or row.chat_token_hash != token_hash:
            raise NotFound("예약을 찾을 수 없어요.")
        if row.status != "held" or (row.hold_expires_at and row.hold_expires_at < now):
            raise HoldExpired("자리를 잡아 둔 시간(10분)이 지났어요. 시간을 다시 골라 주세요.")
        row.name, row.phone, row.memo = (name or None), phone.strip(), (memo or None)
        row.customer_id = customers.touch(db, site_key, phone, name)
        row.status = _status_after(spec)
        row.hold_expires_at = None
        if row.status == "confirmed":
            row.decided_at = datetime.datetime.now(datetime.timezone.utc)
        _event(db, row, "customer", row.status)
        out = _public(row)
    _notify_new(site_key, out)
    return out


def book_now(site_key: str, day: datetime.date, time: str, *, service: Optional[str] = None,
             staff: Optional[str] = None, party: int = 1, name: Optional[str] = None, phone: str = "",
             memo: Optional[str] = None, source: str = "web", actor: str = "customer",
             token_hash: Optional[str] = None, now: Optional[datetime.datetime] = None, notify: bool = True) -> dict:
    """한 번에 신청(사이트 폼)·사장님 직접 입력(전화 예약, 바로 확정)."""
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    status = "confirmed" if actor == "owner" else _status_after(spec)
    with get_sessionmaker()() as db, db.begin():
        cid = customers.touch(db, site_key, phone, name) if phone else None
        row = _place(db, shop_id, site_key, spec, day, time, service=service, staff=staff, party=party, now=now,
                     status=status, source=source, token_hash=token_hash, name=name or None, phone=phone,
                     memo=memo or None, customer_id=cid)
        if status == "confirmed":
            row.decided_at = datetime.datetime.now(datetime.timezone.utc)
        _event(db, row, actor, status, {"source": source})
        out = _public(row)
    if notify and actor != "owner":
        _notify_new(site_key, out)
    return out


def _deadline_ok(row: BookingRow, hours: int, now: datetime.datetime) -> bool:
    return row.start_at is None or now <= row.start_at - datetime.timedelta(hours=hours)


def change(site_key: str, booking_id: int, token_hash: Optional[str], day: datetime.date, time: str, *,
           staff: Optional[str] = None, now: Optional[datetime.datetime] = None) -> dict:
    """손님 변경(BOOK-5). 새 자리를 못 잡으면 옛 예약은 그대로."""
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    pol = S.policy(spec)
    with get_sessionmaker()() as db, db.begin():
        old = db.scalar(select(BookingRow).where(BookingRow.id == booking_id, BookingRow.shop_id == shop_id)
                        .with_for_update())
        if old is None or token_hash is None or old.chat_token_hash != token_hash:
            raise NotFound("예약을 찾을 수 없어요.")
        if old.status not in ("requested", "confirmed"):
            raise NotAllowed("바꿀 수 있는 예약이 아니에요.")
        if not _deadline_ok(old, int(pol["change_deadline_hours"]), now):
            raise DeadlinePassed(f"방문 {pol['change_deadline_hours']}시간 전부터는 채팅으로 바꿀 수 없어요. 가게로 전화 주세요.")
        service = (old.service or "").split(" · ")[0] or None
        old.status = "cancelled"
        db.flush()  # 옛 자리를 먼저 풀어야 같은 담당자의 가까운 시각으로 옮길 수 있다
        new = _place(db, shop_id, site_key, spec, day, time, service=service, staff=staff, party=old.party,
                     now=now, status=_status_after(spec), source=old.source or "chat", token_hash=token_hash,
                     name=old.name, phone=old.phone, memo=old.memo, customer_id=old.customer_id)
        _event(db, old, "customer", "changed_from", {"to": new.id})
        _event(db, new, "customer", "changed_to", {"from": old.id})
        out = _public(new)
    _notify_room(site_key, f"예약을 바꾸셨어요: {_when(out)} {out['name'] or out['phone']}님 ({out['service'] or ''})",
                 out, kind="booking" if out["status"] == "requested" else "booking_result")
    return out


def cancel(site_key: str, booking_id: int, *, token_hash: Optional[str] = None, actor: str = "customer",
           now: Optional[datetime.datetime] = None) -> dict:
    """손님 취소(마감 전까지) (BOOK-6)."""
    shop_id, spec = _require_spec(site_key)
    now = now or _now()
    pol = S.policy(spec)
    with get_sessionmaker()() as db, db.begin():
        row = db.scalar(select(BookingRow).where(BookingRow.id == booking_id, BookingRow.shop_id == shop_id)
                        .with_for_update())
        if row is None or token_hash is None or row.chat_token_hash != token_hash:
            raise NotFound("예약을 찾을 수 없어요.")
        if row.status not in ("held", "requested", "confirmed"):
            raise NotAllowed("이미 취소됐거나 끝난 예약이에요.")
        if row.status != "held" and not _deadline_ok(row, int(pol["cancel_deadline_hours"]), now):
            raise DeadlinePassed(f"방문 {pol['cancel_deadline_hours']}시간 전부터는 채팅으로 취소할 수 없어요. 가게로 전화 주세요.")
        was_held = row.status == "held"
        row.status = "cancelled"
        _event(db, row, actor, "cancelled")
        out = _public(row)
    if not was_held:
        _notify_room(site_key, f"손님이 예약을 취소했어요: {_when(out)} {out['name'] or out['phone']}님", out,
                     kind="booking_result")
    return out


def owner_action(shop_id: int, booking_id: int, action: str, user_id: str,
                 now: Optional[datetime.datetime] = None) -> dict:
    """사장님: confirm·decline·cancel·no_show (OWN-4). 명세 없는 옛 예약도 같은 가게면 된다."""
    now = now or _now()
    with get_sessionmaker()() as db, db.begin():
        site_key = db.scalar(select(ShopRow.site_key).where(ShopRow.id == shop_id))
        row = db.scalar(select(BookingRow).where(BookingRow.id == booking_id, BookingRow.site_key == site_key)
                        .with_for_update())
        if row is None:
            raise NotFound("예약을 찾을 수 없어요.")
        allowed = {"confirm": ("requested",), "decline": ("requested",), "cancel": ("requested", "confirmed"),
                   "no_show": ("confirmed",)}.get(action)
        if allowed is None:
            raise NotAllowed("알 수 없는 동작이에요.")
        if row.status not in allowed:
            raise NotAllowed("지금 상태에서는 할 수 없어요.")
        if action == "no_show" and row.start_at is not None and row.start_at > now:
            raise NotAllowed("방문 시간이 지난 뒤에 노쇼로 표시할 수 있어요.")
        if action == "confirm" and row.start_at is None:
            # 옛 예약: 날짜 잠금 안에서 확정 수를 센다 (bookings.decide와 같은 규칙)
            from app.services import availability
            db.execute(select(func.pg_advisory_xact_lock(func.hashtext(row.site_key + ":" + row.visit_date.isoformat()))))
            if availability.slot_taken(db, row.site_key, row.visit_date, row.visit_time, row.service):
                raise SlotTaken("이미 확정된 예약으로 찬 시간이에요.")
        row.status = {"confirm": "confirmed", "decline": "declined", "cancel": "cancelled",
                      "no_show": "no_show"}[action]
        row.decided_at = datetime.datetime.now(datetime.timezone.utc)
        if row.shop_id is None:
            row.shop_id = shop_id
        _event(db, row, "owner", row.status, {"user_id": user_id})
        return _public(row)


# ── 목록 ──

def _public(row: BookingRow) -> dict:
    return {"id": row.id, "status": row.status, "date": row.visit_date.isoformat(), "time": row.visit_time,
            "service": row.service, "party": row.party, "name": row.name, "phone": row.phone, "memo": row.memo,
            "source": row.source, "resource_key": row.resource_key,
            "start_at": row.start_at.isoformat() if row.start_at else None,
            "end_at": row.end_at.isoformat() if row.end_at else None}


def list_for_owner(shop_id: int, frm: datetime.date, to: datetime.date) -> list[dict]:
    with get_sessionmaker()() as db:
        site_key = db.scalar(select(ShopRow.site_key).where(ShopRow.id == shop_id))
        rows = db.scalars(select(BookingRow).where(
            BookingRow.site_key == site_key, BookingRow.visit_date >= frm, BookingRow.visit_date <= to,
            BookingRow.status.notin_(("held", "expired")))
            .order_by(BookingRow.visit_date, BookingRow.visit_time, BookingRow.id)).all()
        return [_public(r) for r in rows]


def my_bookings(site_key: str, token_hash: Optional[str], now: Optional[datetime.datetime] = None) -> list[dict]:
    """이 브라우저(채팅 토큰)로 만든 다가오는 예약 (CH-5)."""
    if not token_hash:
        return []
    now = now or _now()
    with get_sessionmaker()() as db:
        rows = db.scalars(select(BookingRow).where(
            BookingRow.site_key == site_key, BookingRow.chat_token_hash == token_hash,
            BookingRow.status.in_(("requested", "confirmed")), BookingRow.start_at > now)
            .order_by(BookingRow.start_at)).all()
        return [_public(r) for r in rows]


# ── 휴무·막기 (CAL-3) ──

def add_closure(shop_id: int, start: datetime.datetime, end: datetime.datetime, *, resource_key: Optional[str] = None,
                reason: Optional[str] = None, user_id: Optional[str] = None) -> dict:
    """막기를 넣고, 그 구간에 걸리는 예약 목록을 돌려준다(사장님에게 보여 줄 경고)."""
    if end <= start:
        raise EngineError("끝 시각이 시작보다 뒤여야 해요.")
    with get_sessionmaker()() as db, db.begin():
        row = BookingClosureRow(shop_id=shop_id, resource_key=resource_key, start_at=start, end_at=end,
                                reason=reason, created_by=user_id)
        db.add(row)
        db.flush()
        q = select(BookingRow).where(BookingRow.shop_id == shop_id, BookingRow.status.in_(("requested", "confirmed")),
                                     BookingRow.start_at < end, BookingRow.end_at > start)
        if resource_key:
            q = q.where(BookingRow.resource_key == resource_key)
        hits = [_public(r) for r in db.scalars(q).all()]
        return {"id": row.id, "conflicts": hits}


def list_closures(shop_id: int, frm: datetime.datetime) -> list[dict]:
    with get_sessionmaker()() as db:
        rows = db.scalars(select(BookingClosureRow).where(BookingClosureRow.shop_id == shop_id,
                                                          BookingClosureRow.end_at > frm)
                          .order_by(BookingClosureRow.start_at)).all()
        return [{"id": r.id, "resource_key": r.resource_key, "start_at": r.start_at.isoformat(),
                 "end_at": r.end_at.isoformat(), "reason": r.reason} for r in rows]


def delete_closure(shop_id: int, closure_id: int) -> bool:
    with get_sessionmaker()() as db, db.begin():
        row = db.get(BookingClosureRow, closure_id)
        if row is None or row.shop_id != shop_id:
            return False
        db.delete(row)
        return True


# ── 알림 ──

def _when(b: dict) -> str:
    d = datetime.date.fromisoformat(b["date"])
    return f"{d.month}월 {d.day}일({'월화수목금토일'[d.weekday()]}) {b['time']}"


def _room_for(site_key: str) -> Optional[str]:
    with get_sessionmaker()() as db:
        return db.scalar(select(RoomRow.id).join(SessionRow, RoomRow.session_id == SessionRow.id)
                         .where(SessionRow.requirement_id == site_key))


def _notify_room(site_key: str, text: str, b: dict, kind: str = "booking") -> None:
    room_id = _room_for(site_key)
    if not room_id:
        return
    from app import store
    from app.services import rooms
    try:
        with store.room_tx(room_id) as (room, _session):
            if room is not None:
                rooms._append(room, "system", "예약 알림", text, kind=kind,
                              meta={"booking_id": b["id"], "status": b["status"]})
    except Exception:
        log.exception("예약 알림 실패 room=%s", room_id)
    try:
        from app.services import notify
        notify.owner_kakao(room_id, text)
    except Exception:
        log.exception("사장님 카톡 알림 실패 room=%s", room_id)


def _notify_new(site_key: str, b: dict) -> None:
    head = "새 예약이 확정됐어요(자동 확정)." if b["status"] == "confirmed" else "새 예약 신청이 왔어요. 확정·거절해 주세요."
    lines = [head, f"날짜: {_when(b)}", f"인원: {b['party']}명"]
    if b["service"]:
        lines.append(f"예약: {b['service']}")
    lines += [f"이름: {b['name'] or '(적지 않음)'}", f"연락처: {b['phone']}"]
    if b["memo"]:
        lines.append(f"메모: {b['memo']}")
    _notify_room(site_key, "\n".join(lines), b, kind="booking" if b["status"] == "requested" else "booking_result")
