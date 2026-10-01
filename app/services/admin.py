"""관리자 접근 통제 (DECISIONS D49·D50, ADMIN_CONTRACT §1).

관리자 명단은 서버 .env의 ADMIN_USER_IDS(우리 users.id를 쉼표로)에만 있다. 화면에서 못 바꾼다.
로그인은 기존 카카오·구글 세션을 쓴다. 관리자가 아니면 관리자 기능이 있다는 것 자체를 숨긴다(404).
키 교체처럼 민감한 일은 최근에 로그인한 세션만 할 수 있다.
"""
import datetime
from typing import Optional

from fastapi import HTTPException, Request

from app.config import settings
from app.db.models import LoginSessionRow
from app.db.session import get_sessionmaker
from app.services import auth, keystore


def admin_ids() -> set:
    return {v.strip() for v in (settings.admin_user_ids or "").split(",") if v.strip()}


def require_admin(request: Request) -> dict:
    """관리자면 사용자 dict. 로그인 안 했으면 401, 관리자가 아니면 404."""
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401)
    if user["id"] not in admin_ids():
        raise HTTPException(status_code=404)
    return user


def require_recent_login(request: Request) -> None:
    """이 로그인 세션이 admin_reauth_minutes 안에 만들어졌어야 한다. 아니면 403 reauth."""
    token = request.cookies.get(auth.SESSION_COOKIE)
    created = None
    if token:
        with get_sessionmaker()() as db:
            row = db.get(LoginSessionRow, auth._hash(token))
            created = row.created_at if row else None
    limit = datetime.timedelta(minutes=settings.admin_reauth_minutes)
    if created is None or datetime.datetime.now(datetime.timezone.utc) - created > limit:
        raise HTTPException(status_code=403, detail="reauth")


def viewed(user: dict, what: str, target: Optional[str] = None) -> None:
    """관리자가 무엇을 봤는지 남긴다(D49). 기록이 실패해도 화면은 막지 않는다."""
    try:
        keystore.audit(user["id"], "view:" + what, target)
    except Exception:
        pass
