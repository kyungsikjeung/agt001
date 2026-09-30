"""포장 주문·테스트 결제 손님 경로 (PAY_WAVE3_CONTRACT §3.3).

- POST /api/orders/{site_key}: 메뉴 폼 → 기기 기억이면 바로 주문, 아니면 문자 인증.
  주문은 가게 설정과 상관없이 항상 인증한다 (기기 기억 쿠키가 맞을 때만 건너뜀).
- GET·POST /api/orders/{site_key}/verify/{token} (+ /resend): 예약 인증과 같은 화면·동작.
- GET /pay/{pay_id}: 테스트 결제 페이지 (앱 주소 전용, 서버 문자열 HTML).
- GET /pay/{pay_id}/done: 포트원 조회로 확정한 결과 화면.
- POST /api/payments/webhook: 포트원 웹훅 (서명 확인 → 같은 확정 함수).
"""
import html
import json
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.api.inquiries import _allow, _page
from app.config import settings
from app.security import sanitize_token
from app.services import availability, orders, payments, phone_verify

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
    if not isinstance(payload, dict) or payload.get("kind") != "order":
        return _verify_page(site_key, token, "인증 요청을 찾을 수 없어요.", 400)
    key = sanitize_token(site_key or "")
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


@router.get("/pay/{pay_id}", include_in_schema=False)
def pay_page(pay_id: str, request: Request):
    pid = sanitize_token(pay_id or "")
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
    store_id = settings.portone_store_id or ""
    channel_key = settings.portone_channel_key or ""
    done = _done_url(request, pid)
    order_name = (got["shop_name"] or "우리 가게")[:40] + " 주문"
    # 손님 전화번호는 어떤 칸에도 넣지 않는다 (summary에 없음).
    inner = (f"<h1>주문 확인</h1>"
             f"<p class=\"s-test\">테스트 결제예요. 실제로 돈이 나가지 않아요</p>"
             f"<p><strong>{e(got['shop_name'] or '우리 가게')}</strong></p>"
             f"<ul>{rows}</ul><p>합계 {total:,}원</p>"
             f"<p id=\"pay-msg\" role=\"status\"></p>"
             f"<p><button class=\"s-paybtn\" id=\"pay-btn\" type=\"button\">{total:,}원 결제하기</button></p>"
             f"<p><a href=\"{e(got['site_url'], quote=True)}\">가게로 돌아가기</a></p>"
             f"<script src=\"https://cdn.portone.io/v2/browser-sdk.js\"></script>"
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
    return _pay_doc("주문 확인", inner)


@router.get("/pay/{pay_id}/done", include_in_schema=False)
def pay_done(pay_id: str):
    pid = sanitize_token(pay_id or "")
    got = orders.summary(pid)
    if got is None:
        return _pay_msg("페이지를 찾을 수 없어요", "주문 주소를 다시 확인해 주세요.", "/", 404)
    result = payments.complete(pid)
    if result in ("paid", "already"):
        return _pay_msg("주문이 들어갔어요", "주문이 가게에 전달됐어요. 준비되면 연락드릴게요.", got["site_url"])
    if result == "pending":
        return _pay_msg("결제를 확인하고 있어요", "결제를 확인하고 있어요. 잠시 뒤 새로고침해 주세요.",
                        got["site_url"])
    return _pay_msg("결제가 확인되지 않았어요", "결제가 확인되지 않았어요. 가게에 전화로 주문해 주세요.",
                    got["site_url"])


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
