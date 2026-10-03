import logging
from typing import Optional

from fastapi import APIRouter, Cookie, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.services import auth

log = logging.getLogger(__name__)
router = APIRouter()


def _origin(request: Request) -> str:
    return (settings.public_base_url or str(request.base_url)).rstrip("/")


def _redirect_uri(request: Request, provider: str) -> str:
    return f"{_origin(request)}/auth/{provider}/callback"


def _check_origin(request: Request) -> None:
    """쿠키로 인증하는 상태 변경 요청은 우리 출처에서 온 것만 받는다(CSRF, 보안 S-3)."""
    if request.headers.get("origin", "").rstrip("/") != _origin(request):
        raise HTTPException(status_code=403, detail="bad origin")


def _set_cookie(resp: Response, name: str, value: str, max_age: int) -> None:
    resp.set_cookie(name, value, max_age=max_age, path="/", secure=True, httponly=True, samesite="lax")


@router.get("/auth/{provider}/start", include_in_schema=False)
def auth_start(provider: str, request: Request, next: Optional[str] = None, talk: Optional[int] = None):
    if provider not in auth.PROVIDERS:
        raise HTTPException(status_code=404)
    if not auth.configured(provider):
        # 키를 넣기 전(콘솔 설정 전)에는 안내로 돌려보낸다.
        return RedirectResponse(f"/?login_error={provider}_not_ready", status_code=303)
    state, url = auth.begin(provider, next or "/", _redirect_uri(request, provider), talk=bool(talk) and provider == "kakao")
    resp = RedirectResponse(url, status_code=303)
    _set_cookie(resp, auth.STATE_COOKIE, state, int(auth.STATE_TTL.total_seconds()))
    return resp


@router.get("/auth/{provider}/callback", include_in_schema=False)
def auth_callback(provider: str, request: Request, code: Optional[str] = None, state: Optional[str] = None,
                  error: Optional[str] = None):
    if provider not in auth.PROVIDERS:
        raise HTTPException(status_code=404)
    if error or not code:
        # 사용자가 취소했거나(카카오), 테스트 사용자가 아니라 막힌 경우(구글, D9)
        return RedirectResponse(f"/?login_error={provider}_denied", status_code=303)
    try:
        user_id, next_path = auth.finish(provider, state or "", request.cookies.get(auth.STATE_COOKIE), code,
                                         _redirect_uri(request, provider))
    except auth.AuthError as e:
        log.warning("로그인 실패 provider=%s code=%s", provider, e.code)
        return RedirectResponse(f"/?login_error={provider}_{e.code}", status_code=303)
    except Exception:
        log.exception("로그인 처리 오류 provider=%s", provider)
        return RedirectResponse(f"/?login_error={provider}_error", status_code=303)
    resp = RedirectResponse(next_path, status_code=303)
    resp.delete_cookie(auth.STATE_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    _set_cookie(resp, auth.SESSION_COOKIE, auth.create_session(user_id), settings.login_session_days * 86400)
    return resp


@router.get("/api/me")
def me(request: Request):
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401)
    return {"user": user}


@router.post("/api/logout", status_code=204)
def logout(request: Request):
    _check_origin(request)
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    resp = Response(status_code=204)
    resp.delete_cookie(auth.SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return resp


class WithdrawIn(BaseModel):
    confirm: str = ""


@router.post("/api/me/withdraw")
def withdraw(body: WithdrawIn, request: Request):
    """회원 탈퇴 (P2-6, L-5). 실수로 누르지 않게 "탈퇴"를 직접 적어야 한다."""
    from app.services import accounts
    _check_origin(request)
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401)
    if body.confirm.strip() != "탈퇴":
        raise HTTPException(status_code=400, detail="확인을 위해 '탈퇴'라고 적어 주세요.")
    try:
        result = accounts.withdraw(user["id"])
    except LookupError:
        raise HTTPException(status_code=401)
    resp = JSONResponse(result)
    resp.delete_cookie(auth.SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="lax")
    return resp


class ClaimIn(BaseModel):
    room_ids: list[str] = []


@router.post("/api/me/claim")
def claim(body: ClaimIn, request: Request, x_member_id: Optional[str] = Header(default=None)):
    _check_origin(request)
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401)
    return {"claimed": auth.claim_rooms(user["id"], x_member_id or "", body.room_ids)}
