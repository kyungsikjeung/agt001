"""사장님 예약 관리 API (BOOKING_BOT_IMPL_PLAN OWN-3·OWN-4·OWN-6, UI-3).

로그인 필수(401). 남의 가게는 404. 바꾸는 요청은 _check_origin.
"""
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.api.auth import _check_origin
from app.config import settings
from app.services import auth, booking_engine, botmaker, orders, payments, shops
from app.services.slots import KST

router = APIRouter()
log = logging.getLogger(__name__)


def _me(request: Request) -> dict:
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401)
    return user


def _shop(request: Request, site_key: str, roles=shops.ROLES) -> tuple[dict, int]:
    user = _me(request)
    try:
        return user, shops.require_member(user["id"], site_key, roles)
    except shops.NotMember:
        raise HTTPException(status_code=404)


def _engine_call(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except booking_engine.SlotTaken as e:
        raise HTTPException(status_code=409, detail=str(e))
    except booking_engine.NotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except booking_engine.EngineError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _date(raw: Optional[str], default: datetime.date) -> datetime.date:
    if not raw:
        return default
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="날짜 형식은 YYYY-MM-DD")


@router.get("/owner", include_in_schema=False)
def owner_page():
    return FileResponse(settings.static_dir / "owner.html")


@router.get("/api/owner/shops")
def list_shops(request: Request):
    user = _me(request)
    out = []
    for s in shops.member_sites(user["id"]):
        active = booking_engine.get_spec(s["shop_id"])
        draft = booking_engine.get_spec(s["shop_id"], "draft")
        out.append({**s, "bot_active": bool(active), "bot_version": active["version"] if active else None,
                    "bot_draft": bool(draft)})
    return {"shops": out, "support_phone": settings.support_phone}


# ── 예약 ──

class BookingIn(BaseModel):
    date: str
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    service: Optional[str] = None
    staff: Optional[str] = None
    party: int = Field(default=1, ge=1, le=50)
    name: Optional[str] = Field(default=None, max_length=40)
    phone: str = Field(default="", max_length=20)
    memo: Optional[str] = Field(default=None, max_length=300)


@router.get("/api/owner/shops/{site_key}/bookings")
def list_bookings(site_key: str, request: Request, frm: Optional[str] = None, to: Optional[str] = None):
    _, shop_id = _shop(request, site_key)
    today = datetime.datetime.now(KST).date()
    a = _date(frm, today)
    b = _date(to, a + datetime.timedelta(days=14))
    if (b - a).days > 62:
        raise HTTPException(status_code=400, detail="한 번에 62일까지 볼 수 있어요.")
    return {"bookings": booking_engine.list_for_owner(shop_id, a, b)}


@router.post("/api/owner/shops/{site_key}/bookings")
def add_booking(site_key: str, body: BookingIn, request: Request):
    """전화·방문 예약을 사장님이 직접 넣는다(바로 확정)."""
    _check_origin(request)
    _shop(request, site_key)
    day = _date(body.date, datetime.datetime.now(KST).date())
    out = _engine_call(booking_engine.book_now, site_key, day, body.time, service=body.service, staff=body.staff,
                       party=body.party, name=body.name, phone=body.phone, memo=body.memo, source="phone",
                       actor="owner")
    return {"booking": out}


@router.post("/api/owner/shops/{site_key}/bookings/{booking_id}/{action}")
def booking_action(site_key: str, booking_id: int, action: str, request: Request):
    _check_origin(request)
    user, shop_id = _shop(request, site_key)
    return {"booking": _engine_call(booking_engine.owner_action, shop_id, booking_id, action, user["id"])}


# ── 주문 (PAY_WAVE3_CONTRACT §3.5) ──

class RefundIn(BaseModel):
    amount: Optional[int] = None
    reason: str = ""


@router.get("/api/owner/shops/{site_key}/orders")
def list_orders(site_key: str, request: Request, date: Optional[str] = None):
    """그날 주문 목록. 기본 오늘(KST)."""
    _shop(request, site_key)
    day = _date(date, datetime.datetime.now(KST).date())
    return {"orders": orders.owner_list(site_key, day)}


@router.post("/api/owner/shops/{site_key}/orders/{order_id}/refund")
def refund_order(site_key: str, order_id: int, body: RefundIn, request: Request):
    """환불. amount가 비면 남은 전액."""
    _check_origin(request)
    user, _ = _shop(request, site_key)
    try:
        return payments.refund(site_key, order_id, body.amount, body.reason or "", user["id"])
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/owner/shops/{site_key}/orders/{order_id}/complete")
def complete_order(site_key: str, order_id: int, request: Request):
    """가져감 처리. 결제된 주문만."""
    _check_origin(request)
    user, _ = _shop(request, site_key)
    try:
        return orders.mark_completed(site_key, order_id, user["id"])
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/api/owner/shops/{site_key}/orders/{order_id}/recheck")
def recheck_order(site_key: str, order_id: int, request: Request):
    """포트원에 결제 상태를 다시 묻는다(웹훅을 못 받았을 때)."""
    _check_origin(request)
    _shop(request, site_key)
    from sqlalchemy import select

    from app.db.models import PaymentRow
    from app.db.session import get_sessionmaker

    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.order_id == order_id))
        if pay is None or pay.site_key != site_key:
            raise HTTPException(status_code=404, detail="주문을 찾을 수 없어요.")
        pid = pay.provider_payment_id
    return {"result": payments.complete(pid)}


# ── 휴무·막기 ──

class ClosureIn(BaseModel):
    start_at: datetime.datetime
    end_at: datetime.datetime
    resource_key: Optional[str] = Field(default=None, max_length=20)
    reason: Optional[str] = Field(default=None, max_length=100)


@router.get("/api/owner/shops/{site_key}/closures")
def list_closures(site_key: str, request: Request):
    _, shop_id = _shop(request, site_key)
    return {"closures": booking_engine.list_closures(shop_id, datetime.datetime.now(KST))}


@router.post("/api/owner/shops/{site_key}/closures")
def add_closure(site_key: str, body: ClosureIn, request: Request):
    _check_origin(request)
    user, shop_id = _shop(request, site_key)

    def kst(dt):
        return dt if dt.tzinfo else dt.replace(tzinfo=KST)
    return _engine_call(booking_engine.add_closure, shop_id, kst(body.start_at), kst(body.end_at),
                        resource_key=body.resource_key, reason=body.reason, user_id=user["id"])


@router.delete("/api/owner/shops/{site_key}/closures/{closure_id}")
def delete_closure(site_key: str, closure_id: int, request: Request):
    _check_origin(request)
    _, shop_id = _shop(request, site_key)
    if not booking_engine.delete_closure(shop_id, closure_id):
        raise HTTPException(status_code=404)
    return {"ok": True}


# ── 봇메이커 ──

class BotTurnIn(BaseModel):
    text: Optional[str] = Field(default=None, max_length=500)
    action: Optional[str] = Field(default=None, max_length=60)
    mode: Optional[str] = Field(default=None, pattern=r"^(slot|table)$")


@router.get("/api/owner/shops/{site_key}/bot")
def bot_state(site_key: str, request: Request):
    _, shop_id = _shop(request, site_key, ("owner",))
    active = booking_engine.get_spec(shop_id)
    draft = booking_engine.get_spec(shop_id, "draft")
    return {"active": active, "draft": draft,
            "problems": booking_spec_problems(draft["spec"]) if draft else []}


def booking_spec_problems(spec: dict) -> list:
    from app.services import booking_spec
    return booking_spec.validate(botmaker._clean(spec))


@router.post("/api/owner/shops/{site_key}/bot")
def bot_turn(site_key: str, body: BotTurnIn, request: Request):
    """봇메이커 한 턴. draft가 없으면 카드에서 씨앗을 만들고 첫 질문을 한다. action=activate면 켠다."""
    _check_origin(request)
    user, shop_id = _shop(request, site_key, ("owner",))
    if body.action == "activate":
        got = _engine_call(botmaker.activate, shop_id, user["id"])
        _republish(site_key)
        return {"reply": f"예약 봇을 켰어요(설정 {got['version']}판). 손님은 사이트의 '채팅으로 예약'으로 들어와요.",
                "buttons": [], "activated": got}
    draft = booking_engine.get_spec(shop_id, "draft")
    if draft is None or body.mode:
        from app.services import availability
        spec = botmaker.seed(availability._card_for_site(site_key) or {}, mode=body.mode)
        spec, out = botmaker.turn(spec)
    else:
        spec, out = botmaker.turn(draft["spec"], text=body.text, action=body.action)
    booking_engine.save_draft(shop_id, spec, user["id"])
    return out


def _republish(site_key: str) -> None:
    """봇을 켜면 공개 사이트를 바로 다시 그려 '채팅으로 예약' 링크를 넣는다 (D55 B3).
    전엔 다음 날 날짜가 넘어가 다시 그릴 때까지 링크가 없었다. 실패해도 켜기는 유지한다."""
    from app.services import availability, design
    try:
        card = availability._card_for_site(site_key)
        if card and card.get("published"):
            design.publish_choice(site_key, card, card["published"])
    except Exception:
        log.exception("봇 켜기 뒤 공개본 다시 그리기 실패 site=%s", site_key)


class RevertIn(BaseModel):
    spec_id: int


@router.post("/api/owner/shops/{site_key}/bot/revert")
def bot_revert(site_key: str, body: RevertIn, request: Request):
    """옛 판으로 되돌리기 (SPEC-3)."""
    _check_origin(request)
    user, shop_id = _shop(request, site_key, ("owner",))
    return {"activated": _engine_call(booking_engine.activate, shop_id, user["id"], body.spec_id)}
