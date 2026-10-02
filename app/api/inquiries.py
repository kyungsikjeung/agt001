"""POST /api/inquiries/{site_key}: 생성 사이트의 일반 HTML 폼 전송 (templates/README.md §5).

생성 사이트는 CSP sandbox로 열려 스크립트 없이 동작해야 하므로, 응답은 JSON이 아니라 페이지·리다이렉트다.
"""
import html
import threading
import time
from collections import deque
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.security import sanitize_token
from app.services import inquiries

router = APIRouter()

# IP당 10분에 5건. IP는 메모리에서만 쓴다.
RATE_LIMIT, RATE_WINDOW = 5, 600
_hits: dict[str, deque] = {}
_lock = threading.Lock()

_PAGE_HEADERS = {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'", "X-Content-Type-Options": "nosniff"}


def _allow(key: str) -> bool:
    now = time.monotonic()
    with _lock:
        q = _hits.setdefault(key, deque())
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        return True


def _page(title: str, body: str, site_key: str, status: int) -> HTMLResponse:
    back = f"/site/{html.escape(sanitize_token(site_key) or '')}/" if sanitize_token(site_key) else "/"
    doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>body{{font-family:system-ui,sans-serif;max-width:32rem;margin:15vh auto;padding:0 16px;line-height:1.6;color:#1f2328}}
a{{color:#0b5fff}}</style></head><body><h1>{html.escape(title)}</h1><p>{html.escape(body)}</p>
<p><a href="{back}">사이트로 돌아가기</a></p></body></html>"""
    return HTMLResponse(doc, status_code=status, headers=_PAGE_HEADERS)


@router.post("/api/inquiries/{site_key}", include_in_schema=False)
def submit_inquiry(site_key: str, request: Request, name: Optional[str] = Form(default=None),
                   contact: Optional[str] = Form(default=None), message: Optional[str] = Form(default=None),
                   agree: Optional[str] = Form(default=None), website: Optional[str] = Form(default=None)):
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 문의가 많이 들어왔어요.", site_key, 429)
    try:
        inquiries.submit(site_key, name, contact, message, agree, website)
    except inquiries.InquiryError as e:
        return _page("문의를 보내지 못했어요", str(e), site_key, 400)
    return RedirectResponse(f"/api/inquiries/{sanitize_token(site_key)}/done", status_code=303)


@router.post("/api/rsvp/{site_key}", include_in_schema=False)
def submit_rsvp(site_key: str, request: Request, name: Optional[str] = Form(default=None),
                side: Optional[str] = Form(default=None), attend: Optional[str] = Form(default=None),
                count: Optional[str] = Form(default=None), meal: Optional[str] = Form(default=None),
                contact: Optional[str] = Form(default=None), message: Optional[str] = Form(default=None),
                agree: Optional[str] = Form(default=None), website: Optional[str] = Form(default=None)):
    """청첩장 참석 여부 (rsvp--form). 문의와 같은 IP 제한·저장소를 쓴다."""
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 보내 주세요", "짧은 시간에 많이 들어왔어요.", site_key, 429)
    try:
        inquiries.submit_rsvp(site_key, name, side, attend, count, meal, contact, message, agree, website)
    except inquiries.InquiryError as e:
        return _page("보내지 못했어요", str(e), site_key, 400)
    return _page("참석 여부를 전했어요", "알려 주셔서 고마워요. 그날 뵐게요.", site_key, 200)


@router.post("/api/guestbook/{site_key}", include_in_schema=False)
def submit_guestbook(site_key: str, request: Request, name: Optional[str] = Form(default=None),
                     message: Optional[str] = Form(default=None), website: Optional[str] = Form(default=None)):
    """청첩장 방명록 (guestbook--list). 남기면 사이트의 방명록 자리로 돌아간다."""
    from app.services import guestbook
    if not _allow(request.client.host if request.client else "unknown"):
        return _page("잠시 후 다시 남겨 주세요", "짧은 시간에 많이 들어왔어요.", site_key, 429)
    try:
        guestbook.add(site_key, name, message, website)
    except guestbook.GuestbookError as e:
        return _page("남기지 못했어요", str(e), site_key, 400)
    return RedirectResponse(f"/site/{sanitize_token(site_key)}/#guestbook-title-guestbook", status_code=303)


@router.get("/api/inquiries/{site_key}/done", include_in_schema=False)
def inquiry_done(site_key: str):
    return _page("문의가 전달됐어요", "가게에서 확인한 뒤 적어 주신 연락처로 답변드릴 거예요.", site_key, 200)
