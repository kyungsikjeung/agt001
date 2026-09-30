"""사장님 가게 설정 API (OWNER_SETTINGS_PLAN §1.5).

로그인 필수(아니면 401). 바꾸는 요청은 기존 _check_origin으로 막는다.
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import _check_origin
from app.services import auth, shop_settings
from app.services import sms as sms_svc
from app.services.shop_settings import SettingsError

log = logging.getLogger(__name__)

router = APIRouter()


def _me(request: Request) -> dict:
    user = auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise HTTPException(status_code=401)
    return user


class SettingsIn(BaseModel):
    phone_verify: Optional[bool] = None
    solapi_key: Optional[str] = None
    solapi_secret: Optional[str] = None
    sms_sender: Optional[str] = None
    clear_key: bool = False
    order_on: Optional[bool] = None


class SmsTestIn(BaseModel):
    solapi_key: str = ""
    solapi_secret: str = ""


@router.get("/api/me/shops")
def list_shops(request: Request):
    user = _me(request)
    sites = shop_settings.owned_sites(user["id"])
    return {"shops": [{**s, "settings": shop_settings.get(s["site_key"])} for s in sites]}


@router.put("/api/me/shops/{site_key}/settings")
def update_settings(site_key: str, body: SettingsIn, request: Request):
    _check_origin(request)
    user = _me(request)
    old_on = shop_settings.get(site_key).get("order_on", False)
    try:
        out = shop_settings.update(user["id"], site_key, phone_verify=body.phone_verify,
                                   solapi_key=body.solapi_key, solapi_secret=body.solapi_secret,
                                   sms_sender=body.sms_sender, clear_key=body.clear_key,
                                   order_on=body.order_on)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except (SettingsError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    if body.order_on is not None and out.get("order_on") != old_on:
        _republish_if_published(site_key)
    return {"settings": out}


def _republish_if_published(site_key: str) -> None:
    """주문 스위치가 바뀌면 공개본이 있으면 다시 공개한다. 실패해도 설정은 그대로 두고 로그만."""
    try:
        from sqlalchemy import select

        from app.db.models import SessionRow
        from app.db.session import get_sessionmaker
        from app.services import design
        with get_sessionmaker()() as db:
            row = db.scalar(select(SessionRow).where(SessionRow.requirement_id == site_key))
            card = row.prd if row is not None and isinstance(row.prd, dict) else None
        if isinstance(card, dict) and card.get("published"):
            design.publish_choice(site_key, card, card["published"])
    except Exception:
        log.exception("주문 설정 뒤 공개본 다시 그리기 실패 site=%s", site_key)


@router.post("/api/me/shops/{site_key}/sms-test")
def sms_test(site_key: str, body: SmsTestIn, request: Request):
    _check_origin(request)
    user = _me(request)
    if not shop_settings.can_edit(user["id"], site_key):
        raise HTTPException(status_code=403, detail="이 가게 설정을 바꿀 수 없어요.")
    return {"ok": sms_svc.check_key(body.solapi_key, body.solapi_secret)}
