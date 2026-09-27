"""예약 신청 (플랫폼 공용 ②, docs/product/BOOKING_PLAN.md §2).

- POST /api/bookings/{site_key}: 생성 사이트의 일반 HTML 폼 전송. 사이트가 CSP sandbox라 스크립트가 없으므로
  응답은 JSON이 아니라 페이지·리다이렉트다(문의 app/api/inquiries.py와 같다).
- GET/POST /room/{room_id}/bookings…: 채팅방의 방장이 상태를 보고 확정·거절한다.
"""
from typing import Optional

from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.api.inquiries import _allow, _page
from app.security import sanitize_token
from app.services import bookings, rooms

router = APIRouter()


@router.post("/api/bookings/{site_key}", include_in_schema=False)
def submit_booking(site_key: str, request: Request, date: Optional[str] = Form(default=None),
                   time: Optional[str] = Form(default=None), service: Optional[str] = Form(default=None),
                   party: Optional[str] = Form(default=None), name: Optional[str] = Form(default=None),
                   phone: Optional[str] = Form(default=None), memo: Optional[str] = Form(default=None),
                   agree: Optional[str] = Form(default=None), website: Optional[str] = Form(default=None),
                   slot: Optional[str] = Form(default=None), staff: Optional[str] = Form(default=None),
                   nights: Optional[str] = Form(default=None)):
    # 문의와 같은 IP 제한 창을 함께 쓴다(한 사람이 문의·예약을 번갈아 쏟아내지 못하게).
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 신청이 많이 들어왔어요.", site_key, 429)
    # 예약 현황 부품(booking--slots)은 날짜·시간을 "YYYY-MM-DD HH:MM" 한 값(slot)으로, 담당자를 staff로 보낸다.
    if slot and not date:
        date, _, time = slot.strip().partition(" ")
    if staff and staff.strip():
        # ponytail: 담당자 칸 없이 시술 칸에 붙인다. 담당자별 집계가 필요해지면 bookings에 열 추가.
        service = " · ".join(v.strip() for v in (service or "", staff) if v and v.strip())
    if nights and nights.strip():
        # 펜션 박 수: 1~14 정수일 때만 시술 칸 뒤에 붙인다 (틀린 값은 버림).
        try:
            count = int(nights.strip())
        except ValueError:
            count = 0
        if 1 <= count <= 14:
            suffix = f"{count}박"
            service = f"{service} · {suffix}" if service and service.strip() else suffix
    try:
        bookings.submit(site_key, date, time, service, party, name, phone, memo, agree, website)
    except bookings.BookingError as e:
        return _page("예약 신청을 보내지 못했어요", str(e), site_key, 400)
    return RedirectResponse(f"/api/bookings/{sanitize_token(site_key)}/done", status_code=303)


@router.get("/api/bookings/{site_key}/done", include_in_schema=False)
def booking_done(site_key: str):
    return _page("예약 신청이 전달됐어요", "가게에서 확인한 뒤 적어 주신 전화번호로 연락드릴 거예요. 아직 확정된 예약은 아니에요.",
                 site_key, 200)


class DecisionBody(BaseModel):
    decision: str


def _guard(fn):
    try:
        return fn()
    except (rooms.RoomNotFound, bookings.NotFound):
        raise HTTPException(status_code=404, detail="not found")
    except rooms.NotOwner:
        raise HTTPException(status_code=403, detail="owner only")
    except bookings.AlreadyDecided:
        raise HTTPException(status_code=409, detail="already decided")
    except rooms.InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/room/{room_id}/bookings")
def room_bookings(room_id: str, x_member_id: Optional[str] = Header(default=None)):
    return {"bookings": _guard(lambda: bookings.list_for_room(room_id, x_member_id))}


@router.post("/room/{room_id}/bookings/{booking_id}/decision")
def decide_booking(room_id: str, booking_id: int, body: DecisionBody, x_member_id: Optional[str] = Header(default=None)):
    return _guard(lambda: bookings.decide(room_id, x_member_id, booking_id, body.decision))
