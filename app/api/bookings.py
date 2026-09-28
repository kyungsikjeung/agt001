"""예약 신청 (플랫폼 공용 ②, docs/product/BOOKING_PLAN.md §2).

- POST /api/bookings/{site_key}: 생성 사이트의 일반 HTML 폼 전송. 사이트가 CSP sandbox라 스크립트가 없으므로
  응답은 JSON이 아니라 페이지·리다이렉트다(문의 app/api/inquiries.py와 같다).
- 문자 인증이 켜져 있으면(CUSTOMER_PLAN §4.1) 폼을 바로 저장하지 않고 인증번호 페이지로 보낸다.
- GET/POST /room/{room_id}/bookings…: 채팅방의 방장이 상태를 보고 확정·거절한다.
"""
import html
from typing import Optional

from fastapi import APIRouter, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from app.api.inquiries import _PAGE_HEADERS, _allow, _page
from app.db.session import get_sessionmaker
from app.security import sanitize_token
from app.services import availability, bookings, customers, phone_verify, rooms, shop_settings

router = APIRouter()

# 이 기기 기억 쿠키 보관 (CUSTOMER_PLAN §4.1 10). phone_verify.DEVICE_DAYS와 같은 값.
_DEVICE_MAX_AGE = 90 * 24 * 3600


def _merge_form(date: Optional[str], time: Optional[str], service: Optional[str], party: Optional[str],
                name: Optional[str], phone: Optional[str], memo: Optional[str], agree: Optional[str],
                website: Optional[str], slot: Optional[str], staff: Optional[str],
                nights: Optional[str]) -> dict:
    """폼 전송값을 bookings.submit 인자로 합친다. 인증 앞에서는 이 값을 payload에 넣어 둔다."""
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
    return {"date": date, "time": time, "service": service, "party": party, "name": name,
            "phone": phone, "memo": memo, "agree": agree, "website": website}


def _shop_name(key: str) -> str:
    """문자 앞머리에 넣을 가게 이름. 카드에 없으면 빈 값(그러면 '예약'으로 보낸다)."""
    try:
        card = availability._card_for_site(key)
        value = ((card or {}).get("slots") or {}).get("shop_name", {}).get("value")
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def _verify_page(site_key: str, token: str, error: Optional[str] = None, status: int = 200) -> HTMLResponse:
    """인증번호 입력 페이지. 문의 _page와 같은 모양·같은 헤더, 스크립트 없음. 틀린 사유는 서버에서 넣어 그린다."""
    key = html.escape(sanitize_token(site_key or "") or "")
    tok = html.escape(sanitize_token(token or "") or "")
    err = f"<p>{html.escape(error)}</p>" if error else ""
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>인증번호를 입력해 주세요</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;line-height:1.6;color:#1f2328}}
input,button{{font-size:1rem;min-height:44px}}a{{color:#0b5fff}}</style></head><body>
<h1>인증번호를 입력해 주세요</h1><p>적어 주신 번호로 6자리 인증번호를 보냈어요. 3분 안에 입력해 주세요.</p>
{err}<form method="post" action="/api/bookings/{key}/verify/{tok}">
<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6" required>
<button type="submit">확인</button></form>
<form method="post" action="/api/bookings/{key}/verify/{tok}/resend"><button type="submit">인증번호 다시 받기</button></form>
<p><a href="/site/{key}/">사이트로 돌아가기</a></p></body></html>"""
    return HTMLResponse(doc, status_code=status, headers=_PAGE_HEADERS)


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
    form = _merge_form(date, time, service, party, name, phone, memo, agree, website, slot, staff, nights)
    key = sanitize_token(site_key or "")
    # 인증 꺼짐·스팸 숨김 칸·이 기기 기억 쿠키가 맞으면 지금처럼 바로 저장한다.
    if (not shop_settings.phone_verify_on(key) or form.get("website")
            or phone_verify.device_ok(request.cookies.get(f"pv_{key}"), key, form.get("phone"))):
        try:
            bookings.submit(site_key, **form)
        except bookings.BookingError as e:
            return _page("예약 신청을 보내지 못했어요", str(e), site_key, 400)
        return RedirectResponse(f"/api/bookings/{sanitize_token(site_key)}/done", status_code=303)
    try:
        bookings.submit(site_key, **form, check_only=True)  # 틀린 폼·마감이면 문자 보내기 전에 알린다
    except bookings.BookingError as e:
        return _page("예약 신청을 보내지 못했어요", str(e), site_key, 400)
    try:
        token = phone_verify.start(key, form.get("phone"), form, _shop_name(key))
    except phone_verify.VerifyError as e:
        return _page("인증번호를 보내지 못했어요", str(e), site_key, 400)
    return RedirectResponse(f"/api/bookings/{sanitize_token(site_key)}/verify/{sanitize_token(token)}",
                            status_code=303)


@router.get("/api/bookings/{site_key}/verify/{token}", include_in_schema=False)
def verify_page(site_key: str, token: str):
    return _verify_page(site_key, token)


@router.post("/api/bookings/{site_key}/verify/{token}", include_in_schema=False)
def verify_submit(site_key: str, token: str, code: Optional[str] = Form(default=None)):
    try:
        form = phone_verify.check(token, code)
    except phone_verify.VerifyError as e:
        return _verify_page(site_key, token, str(e), 400)
    try:
        bookings.submit(site_key, **form)
    except bookings.BookingError as e:
        return _page("예약 신청을 보내지 못했어요", str(e), site_key, 400)
    key = sanitize_token(site_key or "")
    with get_sessionmaker()() as db, db.begin():
        customers.mark_verified(db, key, form.get("phone"))
    resp = RedirectResponse(f"/api/bookings/{sanitize_token(site_key)}/done", status_code=303)
    cookie = phone_verify.device_cookie(key, form.get("phone") or "")
    if cookie is not None:
        resp.set_cookie(f"pv_{key}", cookie, max_age=_DEVICE_MAX_AGE, httponly=True, secure=True,
                        samesite="lax", path=f"/api/bookings/{key}")
    return resp


@router.post("/api/bookings/{site_key}/verify/{token}/resend", include_in_schema=False)
def verify_resend(site_key: str, token: str, request: Request):
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 신청이 많이 들어왔어요.", site_key, 429)
    try:
        new_token = phone_verify.resend(token)
    except phone_verify.VerifyError as e:
        return _verify_page(site_key, token, str(e), 400)
    return RedirectResponse(f"/api/bookings/{sanitize_token(site_key)}/verify/{sanitize_token(new_token)}",
                            status_code=303)


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
    except bookings.SlotFull:
        raise HTTPException(status_code=409, detail="slot full")
    except rooms.InvalidRequest as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/room/{room_id}/bookings")
def room_bookings(room_id: str, x_member_id: Optional[str] = Header(default=None)):
    return {"bookings": _guard(lambda: bookings.list_for_room(room_id, x_member_id))}


@router.post("/room/{room_id}/bookings/{booking_id}/decision")
def decide_booking(room_id: str, booking_id: int, body: DecisionBody, x_member_id: Optional[str] = Header(default=None)):
    return _guard(lambda: bookings.decide(room_id, x_member_id, booking_id, body.decision))
