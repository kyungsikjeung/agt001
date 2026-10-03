"""손님 회원 화면 (FEATURE_PLATFORM_PLAN §7.1): 전화번호 인증으로 가입·로그인 → 내 정보(내역 보기).

공개 사이트와 같은 주소(미리보기 주소)에서 열리는 서버 HTML. 스크립트 없음, 글자 16px·버튼 44px.
- GET  /api/members/{키}                  가입·로그인 폼 또는 내 정보
- POST /api/members/{키}                  번호 + 동의 → 인증번호 문자
- GET·POST /api/members/{키}/verify/{토큰} (+ /resend)
- POST /api/members/{키}/logout · /leave  이 기기에서 나가기 · 회원 탈퇴
이 기기 기억은 서명 쿠키 mb_{키}(90일, 이 경로에만).
"""
import html
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.api.inquiries import _allow
from app.security import sanitize_token
from app.services import availability, customers, members, phone_verify, sms

router = APIRouter()

_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'self'",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex",
}
_COOKIE_DAYS = 90
_STYLE = ("body{font-family:system-ui,-apple-system,sans-serif;max-width:32rem;margin:8vh auto;padding:0 16px;"
          "font-size:16px;line-height:1.6;color:#1f2328;background:#fbfaf7}"
          "h1{font-size:1.4rem;margin:0 0 4px}h2{font-size:1.05rem;margin:24px 0 8px}"
          "input,button{font:inherit;min-height:44px}input[type=tel],input[inputmode]{width:100%;box-sizing:border-box;"
          "padding:8px 12px;border:1px solid #c9c6bd;border-radius:10px}"
          "button{padding:0 16px;border-radius:10px;border:1px solid #c9c6bd;background:#fff;cursor:pointer}"
          "button.p{background:#1f2328;color:#fff;border-color:#1f2328;width:100%;margin-top:12px}"
          "a{color:#0b5fff}.m{color:#5b5f57;font-size:.9rem}.err{color:#b42318;font-weight:600}"
          "ul{list-style:none;margin:0;padding:0}li{padding:10px 0;border-top:1px solid #e7e4dc}"
          "li b{display:block}.tag{display:inline-block;font-size:.8rem;padding:0 8px;border-radius:999px;"
          "background:#efece4;margin-left:6px}details{margin-top:8px}.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:24px}"
          "label.c{display:flex;gap:8px;align-items:flex-start;margin-top:12px}label.c input{min-height:auto;width:20px;height:20px;margin-top:3px}")


def _doc(title: str, inner: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f'<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>'
        f'<style>{_STYLE}</style></head><body>{inner}</body></html>',
        status_code=status, headers=_HEADERS)


def _ctx(site_key: str):
    """(정리한 키, 가게 이름, 가게 전화, 켜졌나)."""
    key = sanitize_token(site_key or "") or ""
    card = availability._card_for_site(key) if key else None
    slots = (card or {}).get("slots") or {}
    name = (slots.get("shop_name") or {}).get("value")
    phone = (slots.get("phone") or {}).get("value")
    return key, name if isinstance(name, str) else "", phone if isinstance(phone, str) else "", members.enabled(card)


def _back(key: str) -> str:
    return f'<p class="m"><a href="/site/{html.escape(key)}/">사이트로 돌아가기</a></p>'


def _off(key: str) -> HTMLResponse:
    return _doc("회원", f"<h1>회원 기능을 쓰지 않는 가게예요</h1>{_back(key)}", 404)


def _cookie_phone(request: Request, key: str) -> Optional[str]:
    return phone_verify.device_phone(request.cookies.get(f"mb_{key}"), key)


def _consent(shop: str) -> str:
    who = html.escape(shop or "이 가게")
    return (f'<details><summary>무엇을 모으고 어떻게 쓰나요</summary><p class="m">'
            f"모으는 것: 전화번호(예약·주문 때 적은 이름이 있으면 함께)<br>"
            f"쓰는 곳: 회원 확인, 이 가게에서의 내 예약·주문·스탬프 보여 드리기<br>"
            f"보관: 탈퇴할 때까지(예약·주문 기록은 가게 보관 기간이 지나면 지워져요)<br>"
            f"처리: {who}(처리자) · 한마디(사이트 운영을 맡은 수탁자). 동의하지 않으면 가입할 수 없지만 "
            f'예약·문의는 그대로 할 수 있어요. <a href="/privacy.html">개인정보처리방침</a></p></details>')


def _join_form(key: str, shop: str, error: str = "") -> str:
    k = html.escape(key)
    err = f'<p class="err" role="alert">{html.escape(error)}</p>' if error else ""
    return (f"<h1>{html.escape(shop or '가게')} 회원</h1>"
            f'<p class="m">전화번호로 가입·로그인해요. 이 가게에서의 내 예약·주문·스탬프를 볼 수 있어요.</p>{err}'
            f'<form method="post" action="/api/members/{k}">'
            f'<label for="phone">전화번호</label>'
            f'<input id="phone" name="phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="010-1234-5678" required>'
            f'<label class="c"><input type="checkbox" name="agree" value="1" required>'
            f"<span>개인정보 수집·이용에 동의해요 (필수)</span></label>{_consent(shop)}"
            f'<button class="p" type="submit">인증번호 받기</button></form>'
            f'<p class="m">이미 회원이면 같은 번호로 인증하면 들어가져요. 이 기기는 90일 동안 기억해요.</p>{_back(key)}')


_kst = members.kst_date


def _mine(key: str, shop: str, shop_phone: str, phone: str, data: dict) -> str:
    e = html.escape
    k = e(key)
    parts = [f"<h1>내 정보</h1><p class=\"m\">{e(shop or '가게')} · {e(members.mask(phone))} · {_kst(data['since'])} 가입</p>"]
    parts.append("<h2>예약</h2>")
    if data["bookings"]:
        parts.append("<ul>" + "".join(
            f"<li><b>{e(b['date'])} {e(b['time'])}<span class=\"tag\">{e(b['status'])}</span></b>"
            f"<span class=\"m\">{e(b['service'])}{' · ' if b['service'] else ''}{b['party']}명</span></li>"
            for b in data["bookings"]) + "</ul>")
    else:
        parts.append('<p class="m">아직 예약이 없어요.</p>')
    parts.append("<h2>주문</h2>")
    if data["orders"]:
        parts.append("<ul>" + "".join(
            f"<li><b>{_kst(o['at'])} · {o['total']:,}원<span class=\"tag\">{e(o['status'])}</span></b>"
            f"<span class=\"m\">{e(o['items'])}</span></li>" for o in data["orders"]) + "</ul>")
    else:
        parts.append('<p class="m">아직 주문이 없어요.</p>')
    if data["stamps"] is not None:
        st = data["stamps"]
        parts.append(f"<h2>스탬프</h2><p><b>{st['balance']} / {st['goal']}</b></p>")
        if st["coupons"]:
            parts.append('<p class="m">쓸 수 있는 쿠폰: ' + ", ".join(e(c) for c in st["coupons"]) +
                         f' · <a href="/api/orders/{k}/my">쿠폰 보여 주기</a></p>')
    call = f' (<a href="tel:{e(customers.normalize_phone(shop_phone) or "")}">{e(shop_phone)}</a>)' if shop_phone else ""
    parts.append(f'<p class="m">예약 바꾸기·취소는 가게에 연락해 주세요{call}.</p>')
    parts.append(f'<div class="row"><form method="post" action="/api/members/{k}/logout">'
                 f'<button type="submit">이 기기에서 나가기</button></form>'
                 f'<form method="post" action="/api/members/{k}/leave">'
                 f'<button type="submit">회원 탈퇴</button></form></div>'
                 f'<p class="m">탈퇴하면 회원 표시와 이름을 지워요. 예약·주문 기록은 가게 보관 기간이 지나면 지워져요.</p>')
    parts.append(_back(key))
    return "".join(parts)


def _no_sms(key: str, shop: str) -> HTMLResponse:
    """문자 키가 하나도 없으면 인증번호가 실제로 가지 않는다(개발 모드는 기록만) → 가입을 열지 않는다."""
    return _doc(f"{shop or '가게'} 회원", f"<h1>지금은 회원 가입을 받을 수 없어요</h1>"
                f'<p class="m">문자 인증 준비가 아직 안 됐어요. 예약·문의는 그대로 할 수 있어요.</p>{_back(key)}', 503)


@router.get("/api/members/{site_key}", include_in_schema=False)
def member_home(site_key: str, request: Request):
    key, shop, shop_phone, on = _ctx(site_key)
    if not on:
        return _off(key)
    phone = _cookie_phone(request, key)
    data = members.history(key, phone) if phone else None
    if data is None:
        if not sms.available(key):
            return _no_sms(key, shop)
        return _doc(f"{shop or '가게'} 회원", _join_form(key, shop))
    return _doc("내 정보", _mine(key, shop, shop_phone, phone, data))


@router.post("/api/members/{site_key}", include_in_schema=False)
def member_start(site_key: str, request: Request, phone: str = Form(default=""), agree: str = Form(default="")):
    key, shop, _p, on = _ctx(site_key)
    if not on:
        return _off(key)
    if not _allow(request.client.host if request.client else "unknown"):
        return _doc("잠시 뒤에", _join_form(key, shop, "짧은 시간에 요청이 많았어요. 잠시 뒤 다시 해 주세요."), 429)
    if not sms.available(key):
        return _no_sms(key, shop)
    if agree != "1":
        return _doc("동의가 필요해요", _join_form(key, shop, "개인정보 수집·이용에 동의해야 가입할 수 있어요."), 400)
    if customers.normalize_phone(phone) is None:
        return _doc("번호를 확인해 주세요", _join_form(key, shop, "전화번호를 다시 확인해 주세요."), 400)
    if not members.sms_quota_ok(key):
        return _doc("오늘은 어려워요", _join_form(key, shop, "오늘은 회원 확인 문자를 더 보낼 수 없어요. 내일 다시 해 주세요."), 429)
    try:
        token = phone_verify.start(key, phone, {"kind": "member", "phone": phone}, shop or "회원 확인")
    except phone_verify.VerifyError as exc:
        return _doc("인증번호를 보내지 못했어요", _join_form(key, shop, str(exc)), 400)
    return RedirectResponse(f"/api/members/{key}/verify/{sanitize_token(token)}", status_code=303)


def _verify(key: str, token: str, error: str = "", status: int = 200) -> HTMLResponse:
    k, t = html.escape(key), html.escape(sanitize_token(token or "") or "")
    err = f'<p class="err" role="alert">{html.escape(error)}</p>' if error else ""
    return _doc("인증번호를 입력해 주세요", (
        f"<h1>인증번호를 입력해 주세요</h1><p class=\"m\">적어 주신 번호로 6자리 인증번호를 보냈어요. 3분 안에 입력해 주세요.</p>{err}"
        f'<form method="post" action="/api/members/{k}/verify/{t}">'
        f'<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6" '
        f'aria-label="인증번호 6자리" required><button class="p" type="submit">확인</button></form>'
        f'<form method="post" action="/api/members/{k}/verify/{t}/resend"><button type="submit">인증번호 다시 받기</button></form>'
        f"{_back(key)}"), status)


@router.get("/api/members/{site_key}/verify/{token}", include_in_schema=False)
def member_verify_page(site_key: str, token: str):
    key, _s, _p, on = _ctx(site_key)
    return _verify(key, token) if on else _off(key)


@router.post("/api/members/{site_key}/verify/{token}", include_in_schema=False)
def member_verify(site_key: str, token: str, code: Optional[str] = Form(default=None)):
    key, _s, _p, on = _ctx(site_key)
    if not on:
        return _off(key)
    try:
        payload = phone_verify.check(token, code)
    except phone_verify.VerifyError as exc:
        return _verify(key, token, str(exc), 400)
    if not isinstance(payload, dict) or payload.get("kind") != "member":
        return _verify(key, token, "인증 요청을 찾을 수 없어요.", 400)
    phone = str(payload.get("phone") or "")
    members.join(key, phone)
    cookie = phone_verify.device_cookie(key, phone)
    if cookie is None:
        # 서명 키가 없어 이 기기를 기억할 수 없으면(서버 설정) 돌려보내지 말고 이번만 바로 보여 준다
        norm = customers.normalize_phone(phone) or ""
        key_, shop, shop_phone, _on = _ctx(key)
        data = members.history(key_, norm)
        if data is not None:
            note = '<p class="m">이 기기는 기억하지 못해요. 다음에 볼 때 다시 인증해 주세요.</p>'
            return _doc("내 정보", _mine(key_, shop, shop_phone, norm, data) + note)
    resp = RedirectResponse(f"/api/members/{key}", status_code=303)
    if cookie is not None:
        resp.set_cookie(f"mb_{key}", cookie, max_age=_COOKIE_DAYS * 86400, httponly=True, secure=True,
                        samesite="lax", path=f"/api/members/{key}")
    return resp


@router.post("/api/members/{site_key}/verify/{token}/resend", include_in_schema=False)
def member_resend(site_key: str, token: str, request: Request):
    key, _s, _p, on = _ctx(site_key)
    if not on:
        return _off(key)
    if not _allow(request.client.host if request.client else "unknown"):
        return _verify(key, token, "짧은 시간에 요청이 많았어요. 잠시 뒤 다시 해 주세요.", 429)
    if not members.sms_quota_ok(key):
        return _verify(key, token, "오늘은 회원 확인 문자를 더 보낼 수 없어요.", 429)
    try:
        new_token = phone_verify.resend(token)
    except phone_verify.VerifyError as exc:
        return _verify(key, token, str(exc), 400)
    return RedirectResponse(f"/api/members/{key}/verify/{sanitize_token(new_token)}", status_code=303)


def _out(key: str, message: str) -> HTMLResponse:
    resp = _doc("내 정보", f"<h1>{html.escape(message)}</h1>{_back(key)}")
    resp.delete_cookie(f"mb_{key}", path=f"/api/members/{key}")
    return resp


@router.post("/api/members/{site_key}/logout", include_in_schema=False)
def member_logout(site_key: str):
    key, _s, _p, _on = _ctx(site_key)
    return _out(key, "이 기기에서 나갔어요")


@router.post("/api/members/{site_key}/leave", include_in_schema=False)
def member_leave(site_key: str, request: Request):
    key, _s, _p, _on = _ctx(site_key)
    phone = _cookie_phone(request, key)
    if not phone:
        return _doc("내 정보", f"<h1>먼저 번호로 들어와 주세요</h1>{_back(key)}", 400)
    members.leave(key, phone)
    return _out(key, "회원 탈퇴했어요")
