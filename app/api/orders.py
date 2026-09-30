"""포장 주문·테스트 결제 손님 경로 (PAY_WAVE3_CONTRACT §3.3).

- POST /api/orders/{site_key}: 메뉴 폼 → 기기 기억이면 바로 주문, 아니면 문자 인증.
  주문은 가게 설정과 상관없이 항상 인증한다 (기기 기억 쿠키가 맞을 때만 건너뜀).
- GET·POST /api/orders/{site_key}/verify/{token} (+ /resend): 예약 인증과 같은 화면·동작.
- GET /pay/{pay_id}: 테스트 결제 페이지 (앱 주소 전용, 서버 문자열 HTML).
- GET /pay/{pay_id}/done: 포트원 조회로 확정한 결과 화면.
- POST /api/payments/webhook: 포트원 웹훅 (서명 확인 → 같은 확정 함수).
"""
import datetime
import html
import json
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.auth import _check_origin
from app.api.inquiries import _allow, _page
from app.config import settings
from app.db.models import CouponRow, CustomerRow, OrderRow, PaymentRow, StampEventRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token
from app.services import availability, orders, payments, phone_verify
from app.services import stamps
from app.services.barcode import code128c_svg

router = APIRouter()

# 기기 기억 쿠키 보관 (예약과 같은 90일, 경로는 /api/orders/{site_key}).
_DEVICE_MAX_AGE = 90 * 24 * 3600

# /pay 응답 헤더 (PAY_WAVE3_CONTRACT §3.3 그대로).
_PAY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.portone.io; "
                               "connect-src https://*.portone.io; "
                               "frame-src https://*.portone.io https://*.tosspayments.com https://*.kcp.co.kr; "
                               "img-src 'self' data: https:; style-src 'self' 'unsafe-inline'",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

_PAY_STYLE = ("body{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;"
              "font-size:16px;line-height:1.6;color:#1f2328}"
              "input,button{font-size:16px;min-height:44px}a{color:#0b5fff}"
              ".s-paybtn{display:flex;width:100%;min-height:48px;align-items:center;justify-content:center;"
              "font-weight:700;color:#fff;background:#0b5fff;border:0;border-radius:10px;cursor:pointer}"
              ".s-test{background:#fff8e1;border:1px solid #f0d060;border-radius:10px;padding:10px 12px}")


def _js(value) -> str:
    """인라인 스크립트에 넣을 JSON 값. json.dumps는 </script>를 막지 않아 '<'·'>'·'&'도 \\u로 바꾼다
    (가게 이름은 사장님이 정하는 값이라, 그대로 두면 앱 주소 결제 페이지에서 스크립트를 끼워 넣을 수 있다)."""
    return json.dumps(value).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _pay_url(pay_id: str) -> str:
    """303·주문 뒤 이동 주소. 공개 기본 주소가 있으면 절대 주소, 없으면 상대 주소."""
    base = (settings.public_base_url or "").strip().rstrip("/")
    pid = sanitize_token(pay_id or "")
    return f"{base}/pay/{pid}" if base else f"/pay/{pid}"


def _done_url(request: Request, pay_id: str) -> str:
    """결제창이 돌아올 절대 주소 (휴대폰 결제창은 redirectUrl로 돌아온다)."""
    base = (settings.public_base_url or "").strip().rstrip("/") or str(request.base_url).rstrip("/")
    return f"{base}/pay/{sanitize_token(pay_id or '')}/done"


def _pay_doc(title: str, inner: str, status: int = 200) -> HTMLResponse:
    """결제 페이지 틀. 예약 인증 화면과 같은 모양, 글자 16px·버튼 48px."""
    doc = (f"<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
           f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
           f"<title>{html.escape(title)}</title><style>{_PAY_STYLE}</style></head>"
           f"<body>{inner}</body></html>")
    return HTMLResponse(doc, status_code=status, headers=_PAY_HEADERS)


def _pay_msg(title: str, body: str, back_href: str, status: int = 200) -> HTMLResponse:
    """짧은 안내 화면 (만료·준비 중·결과·못 찾음). 전화번호는 넣지 않는다."""
    inner = (f"<h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>"
             f"<p><a href=\"{html.escape(back_href, quote=True)}\">가게로 돌아가기</a></p>")
    return _pay_doc(title, inner, status)


def _shop_name(key: str) -> str:
    """문자 앞머리에 넣을 가게 이름. 카드에 없으면 빈 값."""
    try:
        card = availability._card_for_site(key)
        value = ((card or {}).get("slots") or {}).get("shop_name", {}).get("value")
        return value if isinstance(value, str) else ""
    except Exception:
        return ""


def _verify_page(site_key: str, token: str, error: Optional[str] = None, status: int = 200) -> HTMLResponse:
    """인증번호 입력 페이지. 예약 화면과 같은 모양, 주소만 /api/orders/…."""
    key = html.escape(sanitize_token(site_key or "") or "")
    tok = html.escape(sanitize_token(token or "") or "")
    err = f"<p>{html.escape(error)}</p>" if error else ""
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>인증번호를 입력해 주세요</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;line-height:1.6;color:#1f2328}}
input,button{{font-size:1rem;min-height:44px}}a{{color:#0b5fff}}</style></head><body>
<h1>인증번호를 입력해 주세요</h1><p>적어 주신 번호로 6자리 인증번호를 보냈어요. 3분 안에 입력해 주세요.</p>
{err}<form method="post" action="/api/orders/{key}/verify/{tok}">
<input name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{{6}}" maxlength="6" required>
<button type="submit">확인</button></form>
<form method="post" action="/api/orders/{key}/verify/{tok}/resend"><button type="submit">인증번호 다시 받기</button></form>
<p><a href="/site/{key}/">사이트로 돌아가기</a></p></body></html>"""
    return HTMLResponse(doc, status_code=status, headers=_PAY_HEADERS)


def _verified_lines(payload: dict) -> list:
    """인증 통과 내용 → [(이름, 수량)]. 틀린 값은 버린다."""
    lines = []
    items = (payload or {}).get("items")
    if not isinstance(items, list):
        return []
    for pair in items:
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            continue
        name, qty = pair
        if not isinstance(name, str) or not name.strip():
            continue
        if not isinstance(qty, int) or isinstance(qty, bool):
            continue
        lines.append((name.strip()[:60], qty))
    return lines


@router.post("/api/orders/{site_key}", include_in_schema=False)
async def submit_order(site_key: str, request: Request):
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 신청이 많이 들어왔어요.", site_key, 429)
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    key = sanitize_token(site_key or "")
    if form.get("website"):
        return RedirectResponse(f"/site/{key}/", status_code=303)  # 스팸 숨김 칸: 조용히 가게로
    phone = str(form.get("phone") or "")
    name = str(form.get("name") or "")
    try:
        lines = orders.parse_form(form)
    except orders.OrderError as e:
        return _page("주문을 보내지 못했어요", str(e), site_key, 400)
    if phone_verify.device_ok(request.cookies.get(f"pv_{key}"), key, phone):
        try:
            pay_id = orders.create(key, lines, name, phone)
        except orders.OrderError as e:
            return _page("주문을 보내지 못했어요", str(e), site_key, 400)
        return RedirectResponse(_pay_url(pay_id), status_code=303)
    try:
        orders.check(key, lines, phone)  # 메뉴·금액·주문 받기 여부를 문자 보내기 전에
    except orders.OrderError as e:
        return _page("주문을 보내지 못했어요", str(e), site_key, 400)
    payload = {"kind": "order", "items": [[n, q] for n, q in lines], "name": name, "phone": phone}
    try:
        token = phone_verify.start(key, phone, payload, _shop_name(key))
    except phone_verify.VerifyError as e:
        return _page("인증번호를 보내지 못했어요", str(e), site_key, 400)
    return RedirectResponse(f"/api/orders/{key}/verify/{sanitize_token(token)}", status_code=303)


@router.get("/api/orders/{site_key}/verify/{token}", include_in_schema=False)
def verify_page(site_key: str, token: str):
    return _verify_page(site_key, token)


@router.post("/api/orders/{site_key}/verify/{token}", include_in_schema=False)
def verify_submit(site_key: str, token: str, code: Optional[str] = Form(default=None)):
    try:
        payload = phone_verify.check(token, code)
    except phone_verify.VerifyError as e:
        return _verify_page(site_key, token, str(e), 400)
    if not isinstance(payload, dict):
        return _verify_page(site_key, token, "인증 요청을 찾을 수 없어요.", 400)
    key = sanitize_token(site_key or "")
    if payload.get("kind") == "my":
        # 내 스탬프 보기용 인증. 주문을 만들지 않고 기기 기억만 둔다.
        resp = RedirectResponse(f"/api/orders/{key}/my", status_code=303)
        cookie = phone_verify.device_cookie(key, str(payload.get("phone") or ""))
        if cookie is not None:
            resp.set_cookie(f"pv_{key}", cookie, max_age=_DEVICE_MAX_AGE, httponly=True, secure=True,
                            samesite="lax", path=f"/api/orders/{key}")
        return resp
    if payload.get("kind") != "order":
        return _verify_page(site_key, token, "인증 요청을 찾을 수 없어요.", 400)
    lines = _verified_lines(payload)
    if not lines:
        return _verify_page(site_key, token, "주문할 메뉴를 골라 주세요.", 400)
    try:
        pay_id = orders.create(key, lines, str(payload.get("name") or ""),
                               str(payload.get("phone") or ""))
    except orders.OrderError as e:
        return _page("주문을 보내지 못했어요", str(e), site_key, 400)
    resp = RedirectResponse(_pay_url(pay_id), status_code=303)
    cookie = phone_verify.device_cookie(key, str(payload.get("phone") or ""))
    if cookie is not None:
        resp.set_cookie(f"pv_{key}", cookie, max_age=_DEVICE_MAX_AGE, httponly=True, secure=True,
                        samesite="lax", path=f"/api/orders/{key}")
    return resp


@router.post("/api/orders/{site_key}/verify/{token}/resend", include_in_schema=False)
def verify_resend(site_key: str, token: str, request: Request):
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 신청이 많이 들어왔어요.", site_key, 429)
    try:
        new_token = phone_verify.resend(token)
    except phone_verify.VerifyError as e:
        return _verify_page(site_key, token, str(e), 400)
    key = sanitize_token(site_key or "")
    return RedirectResponse(f"/api/orders/{key}/verify/{sanitize_token(new_token)}", status_code=303)


def _kst_date(dt) -> str:
    """UTC 시각 → KST 날짜 (YYYY-MM-DD)."""
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    return kst.date().isoformat()


def _pay_stamp_ctx(pid: str) -> Optional[dict]:
    """쿠폰 칸에 필요한 주문·손님·쓸 수 있는 쿠폰. 없으면 None."""
    with get_sessionmaker()() as db:
        pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pid))
        if pay is None:
            return None
        order = db.get(OrderRow, pay.order_id)
        if order is None:
            return None
        held = db.scalar(select(CouponRow.id).where(
            CouponRow.held_order_id == order.id, CouponRow.status == "held"))
        usable = []
        if order.customer_id is not None:
            usable = stamps.usable(db, order.site_key, order.customer_id)
        return {"order_id": order.id, "customer_id": order.customer_id,
                "held_id": held, "coupons": usable}


def _coupon_block(pid: str, ctx: dict, subtotal: int, total: int) -> str:
    """쿠폰 고르기 폼. 쓸 수 있는 쿠폰이 없으면 금액 줄만."""
    e = html.escape
    disc = max(subtotal - total, 0)
    parts = [f"<p>합계 {subtotal:,}원 · 쿠폰 할인 {disc:,}원 · 결제할 금액 {total:,}원</p>"]
    if ctx.get("customer_id") is not None and ctx.get("coupons"):
        labels = []
        for c in ctx["coupons"]:
            checked = " checked" if ctx.get("held_id") == c["id"] else ""
            labels.append(
                f"<label><input type=\"radio\" name=\"coupon_id\" value=\"{int(c['id'])}\"{checked}>"
                f" {e(c['title'])} · 기한 {_kst_date(c.get('expires_at'))}</label>")
        none_checked = " checked" if ctx.get("held_id") is None else ""
        labels.append(f"<label><input type=\"radio\" name=\"coupon_id\" value=\"\"{none_checked}> 쓰지 않기</label>")
        parts.append(
            f"<form method=\"post\" action=\"/pay/{e(pid, quote=True)}/coupon\">"
            + "<br>".join(labels) + "<br><button type=\"submit\">쿠폰 고르기</button></form>")
    return "".join(parts)


def _render_pay(pid: str, request: Request, error: Optional[str] = None) -> HTMLResponse:
    """결제 페이지 본문. 쿠폰 오류는 같은 화면에 문구로 보여준다."""
    got = orders.summary(pid)
    if got is None:
        return _pay_msg("페이지를 찾을 수 없어요", "주문 주소를 다시 확인해 주세요.", "/", 404)
    if got["status"] == "paid":
        return RedirectResponse(_done_url(request, pid), status_code=303)
    if got["expired"]:
        return _pay_msg("주문 시간이 지났어요", "주문 시간이 지났어요. 가게 사이트에서 다시 주문해 주세요.",
                        got["site_url"])
    if not payments.ready():
        return _pay_msg("결제 준비 중이에요", "결제 준비 중이에요. 전화로 주문해 주세요.", got["site_url"])
    e = html.escape
    rows = "".join(f"<li>{e(r['name'])} {int(r['qty'])}개 · {int(r['amount']):,}원</li>"
                   for r in got["items"])
    total = int(got["total"])
    subtotal = sum(int(r["amount"]) for r in got["items"])
    store_id = settings.portone_store_id or ""
    channel_key = settings.portone_channel_key or ""
    done = _done_url(request, pid)
    order_name = (got["shop_name"] or "우리 가게")[:40] + " 주문"
    err = f"<p>{e(error)}</p>" if error else ""
    ctx = _pay_stamp_ctx(pid) or {}
    coupon = _coupon_block(pid, ctx, subtotal, total)
    if total == 0:
        # 쿠폰으로 전액 할인되면 포트원 없이 바로 확정한다.
        pay_btn = (f"<form method=\"post\" action=\"/pay/{e(pid, quote=True)}/free\">"
                   f"<button class=\"s-paybtn\" type=\"submit\">쿠폰으로 주문하기</button></form>")
        scripts = ""
    else:
        pay_btn = (f"<p id=\"pay-msg\" role=\"status\"></p>"
                   f"<p><button class=\"s-paybtn\" id=\"pay-btn\" type=\"button\">{total:,}원 결제하기</button></p>")
        scripts = (f"<script src=\"https://cdn.portone.io/v2/browser-sdk.js\"></script>"
                   f"<script>(function(){{var btn=document.getElementById('pay-btn');"
                   f"btn.addEventListener('click',async function(){{"
                   f"var msg=document.getElementById('pay-msg');msg.textContent='결제창을 여는 중이에요.';"
                   f"try{{var res=await PortOne.requestPayment({{storeId:{_js(store_id)},"
                   f"channelKey:{_js(channel_key)},paymentId:{_js(pid)},"
                   f"orderName:{_js(order_name)},totalAmount:{total},"
                   f"currency:\"CURRENCY_KRW\",payMethod:\"CARD\",redirectUrl:{_js(done)}}});"
                   f"if(res&&res.code!=null){{msg.textContent='결제가 끝나지 않았어요. 다시 눌러 주세요.';return;}}"
                   f"location.href={_js(done)};}}"
                   f"catch(err){{msg.textContent='결제창을 열지 못했어요. 다시 눌러 주세요.';}}}});}})();</script>")
    # 손님 전화번호는 어떤 칸에도 넣지 않는다 (summary에 없음).
    inner = (f"<h1>주문 확인</h1>"
             f"<p class=\"s-test\">테스트 결제예요. 실제로 돈이 나가지 않아요</p>"
             f"<p><strong>{e(got['shop_name'] or '우리 가게')}</strong></p>"
             f"<ul>{rows}</ul>{coupon}{err}{pay_btn}"
             f"<p><a href=\"{e(got['site_url'], quote=True)}\">가게로 돌아가기</a></p>"
             f"{scripts}")
    return _pay_doc("주문 확인", inner)


@router.get("/pay/{pay_id}", include_in_schema=False)
def pay_page(pay_id: str, request: Request):
    return _render_pay(sanitize_token(pay_id or ""), request)


@router.post("/pay/{pay_id}/coupon", include_in_schema=False)
def pay_coupon(pay_id: str, request: Request, coupon_id: Optional[str] = Form(default=None)):
    _check_origin(request)
    pid = sanitize_token(pay_id or "")
    raw = (coupon_id or "").strip()
    cid: Optional[int] = None
    if raw:
        try:
            cid = int(raw)
        except ValueError:
            return _render_pay(pid, request, "쿠폰을 고를 수 없어요.")
        if cid <= 0:
            return _render_pay(pid, request, "쿠폰을 고를 수 없어요.")
    try:
        ctx = _pay_stamp_ctx(pid)
        if ctx is None:
            return _pay_msg("페이지를 찾을 수 없어요", "주문 주소를 다시 확인해 주세요.", "/", 404)
        with get_sessionmaker()() as db, db.begin():
            stamps.hold(db, ctx["order_id"], cid)
    except (ValueError, LookupError) as exc:
        return _render_pay(pid, request, str(exc))
    except IntegrityError:
        # 전액 할인(합계 0원)은 payments.amount > 0 검사를 넘지 못한다 (DEVIATIONS).
        # 500 대신 같은 화면에 문구로 보여준다.
        return _render_pay(pid, request, "쿠폰을 지금 쓸 수 없어요. 가게에 물어봐 주세요.")
    return RedirectResponse(f"/pay/{pid}", status_code=303)


@router.post("/pay/{pay_id}/free", include_in_schema=False)
def pay_free(pay_id: str, request: Request):
    _check_origin(request)
    pid = sanitize_token(pay_id or "")
    try:
        result = payments.complete_free(pid)
    except (ValueError, LookupError) as exc:
        return _render_pay(pid, request, str(exc))
    if result in ("paid", "already"):
        return RedirectResponse(_done_url(request, pid), status_code=303)
    return _render_pay(pid, request, "결제할 금액이 남아 있어요.")


def _done_stamp_line(pid: str) -> str:
    """done 화면에 붙는 도장 한 줄. 규칙 꺼짐·손님 없음이면 빈 값."""
    try:
        with get_sessionmaker()() as db:
            pay = db.scalar(select(PaymentRow).where(PaymentRow.provider_payment_id == pid))
            if pay is None:
                return ""
            order = db.get(OrderRow, pay.order_id)
            if order is None or order.customer_id is None:
                return ""
            rule = stamps.rule(order.site_key)
            if rule is None:
                return ""
            bal = stamps.balance(db, order.site_key, order.customer_id)
            shown = min(max(bal, 0), rule["goal"])
            line = f"도장 {shown}/{rule['goal']}"
            # 이 주문 뒤에 생긴 보상 기록이 이 주문 적립으로 받은 쿠폰이다.
            created = order.created_at
            if created is not None:
                if created.tzinfo is None:
                    created = created.replace(tzinfo=datetime.timezone.utc)
                n = db.scalar(select(func.count()).select_from(StampEventRow).where(
                    StampEventRow.site_key == order.site_key,
                    StampEventRow.customer_id == order.customer_id,
                    StampEventRow.reason == "reward",
                    StampEventRow.created_at >= created)) or 0
                if n:
                    line += f" · 쿠폰 {n}장 받았어요"
            return line
    except Exception:
        return ""


@router.get("/pay/{pay_id}/done", include_in_schema=False)
def pay_done(pay_id: str):
    pid = sanitize_token(pay_id or "")
    got = orders.summary(pid)
    if got is None:
        return _pay_msg("페이지를 찾을 수 없어요", "주문 주소를 다시 확인해 주세요.", "/", 404)
    result = payments.complete(pid)
    if result in ("paid", "already"):
        body = "주문이 가게에 전달됐어요. 준비되면 연락드릴게요."
        stamp_line = _done_stamp_line(pid)
        if stamp_line:
            body += f" {stamp_line}"
        return _pay_msg("주문이 들어갔어요", body, got["site_url"])
    if result == "pending":
        return _pay_msg("결제를 확인하고 있어요", "결제를 확인하고 있어요. 잠시 뒤 새로고침해 주세요.",
                        got["site_url"])
    return _pay_msg("결제가 확인되지 않았어요", "결제가 확인되지 않았어요. 가게에 전화로 주문해 주세요.",
                    got["site_url"])


# 내 스탬프 화면 (미리보기 주소, 스크립트 없음).
_MY_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def _my_doc(title: str, inner: str, status: int = 200) -> HTMLResponse:
    """내 스탬프 화면 틀. 글자 16px·버튼 44px, 스크립트 없음."""
    doc = (f"<!doctype html><html lang=\"ko\"><head><meta charset=\"utf-8\">"
           f"<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
           f"<title>{html.escape(title)}</title>"
           f"<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:10vh auto;"
           f"padding:0 16px;font-size:16px;line-height:1.6;color:#1f2328}}"
           f"input,button{{font-size:16px;min-height:44px}}a{{color:#0b5fff}}</style></head>"
           f"<body>{inner}</body></html>")
    return HTMLResponse(doc, status_code=status, headers=_MY_HEADERS)


def _stamp_board(balance: int, goal: int) -> str:
    """도장판 (목표 칸, 채운 만큼 파랑)."""
    filled = min(max(balance, 0), goal)
    dots = "".join(
        "<span style=\"display:inline-block;width:18px;height:18px;border-radius:50%;margin:2px;"
        + ("background:#0b5fff;" if i < filled else "border:2px solid #ccc;")
        + "\"></span>"
        for i in range(goal))
    return (f"<p>도장 {filled}/{goal}</p><p>{dots}</p>")


@router.get("/api/orders/{site_key}/my", include_in_schema=False)
def my_page(site_key: str, request: Request):
    key = sanitize_token(site_key or "")
    e = html.escape
    phone = phone_verify.device_phone(request.cookies.get(f"pv_{key}"), key)
    if not phone:
        inner = (f"<h1>내 스탬프</h1><p>전화번호를 적어 주세요.</p>"
                 f"<form method=\"post\" action=\"/api/orders/{e(key, quote=True)}/my\">"
                 f"<input name=\"phone\" inputmode=\"tel\" autocomplete=\"tel\" required>"
                 f"<button type=\"submit\">번호로 확인하기</button></form>")
        return _my_doc("내 스탬프", inner)
    with get_sessionmaker()() as db:
        cust = db.scalar(select(CustomerRow).where(
            CustomerRow.site_key == key, CustomerRow.phone == phone))
        rule = stamps.rule(key)
        if rule is None:
            return _my_doc("내 스탬프", "<h1>내 스탬프</h1><p>이 가게는 스탬프를 쓰지 않아요</p>")
        if cust is None:
            bal, usable = 0, []
            dimmed: list = []
        else:
            bal = stamps.balance(db, key, cust.id)
            usable = stamps.usable(db, key, cust.id)
            usable_ids = {c["id"] for c in usable}
            now = datetime.datetime.now(datetime.timezone.utc)
            rows = db.scalars(select(CouponRow).where(
                CouponRow.site_key == key, CouponRow.customer_id == cust.id)
                .order_by(CouponRow.id.desc()).limit(10)).all()
            dimmed = [r for r in rows
                      if r.id not in usable_ids and r.status in ("used", "expired")
                      or (r.id not in usable_ids and r.status == "issued"
                          and r.expires_at is not None
                          and (r.expires_at if r.expires_at.tzinfo else
                               r.expires_at.replace(tzinfo=datetime.timezone.utc)) <= now)]
            dimmed = dimmed[:5]
    parts = [f"<h1>내 스탬프</h1>", _stamp_board(bal, rule["goal"])]
    if usable:
        items = []
        for c in usable:
            code = str(c.get("code") or "")
            grouped = f"{code[0:4]} {code[4:8]} {code[8:12]}" if len(code) == 12 else e(code)
            items.append(
                f"<li><p><strong>{e(c.get('title') or '')}</strong> · 기한 {_kst_date(c.get('expires_at'))}</p>"
                f"{code128c_svg(code)}<p>{grouped}</p></li>")
        parts.append("<h2>쓸 수 있는 쿠폰</h2><ul>" + "".join(items) + "</ul>"
                     "<p>화면을 밝게 하고 보여 주세요</p>")
    if dimmed:
        items = []
        for r in dimmed:
            state = "쓴 쿠폰" if r.status == "used" else "기간 지남"
            items.append(f"<li style=\"opacity:.5\"><p><strong>{e(r.title)}</strong> · {state}</p></li>")
        parts.append("<h2>지난 쿠폰</h2><ul>" + "".join(items) + "</ul>")
    return _my_doc("내 스탬프", "".join(parts))


@router.post("/api/orders/{site_key}/my", include_in_schema=False)
async def my_start(site_key: str, request: Request):
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 신청이 많이 들어왔어요.", site_key, 429)
    form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
    key = sanitize_token(site_key or "")
    phone = str(form.get("phone") or "")
    try:
        token = phone_verify.start(key, phone, {"kind": "my", "phone": phone}, _shop_name(key))
    except phone_verify.VerifyError as exc:
        return _page("인증번호를 보내지 못했어요", str(exc), site_key, 400)
    return RedirectResponse(f"/api/orders/{key}/verify/{sanitize_token(token)}", status_code=303)


@router.post("/api/payments/webhook", include_in_schema=False)
async def payments_webhook(request: Request):
    raw = await request.body()
    try:
        data = payments.verify_webhook(dict(request.headers), raw)
    except ValueError:
        return JSONResponse({"ok": False}, status_code=400)
    pid = None
    if isinstance(data, dict):
        inner = data.get("data")
        if isinstance(inner, dict) and isinstance(inner.get("paymentId"), str):
            pid = inner["paymentId"]
    if pid:
        payments.complete(pid)  # 모르는 pay_id면 complete가 unknown으로 끝난다
    return JSONResponse({"ok": True})
