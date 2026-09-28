"""사장님 가게 설정 API (OWNER_SETTINGS_PLAN §1.5).

로그인 필수(아니면 401). 바꾸는 요청은 기존 _check_origin으로 막는다.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import _check_origin
from app.services import auth, shop_settings
from app.services import sms as sms_svc
from app.services.shop_settings import SettingsError

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
    try:
        out = shop_settings.update(user["id"], site_key, phone_verify=body.phone_verify,
                                   solapi_key=body.solapi_key, solapi_secret=body.solapi_secret,
                                   sms_sender=body.sms_sender, clear_key=body.clear_key)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except SettingsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"settings": out}


@router.post("/api/me/shops/{site_key}/sms-test")
def sms_test(site_key: str, body: SmsTestIn, request: Request):
    _check_origin(request)
    user = _me(request)
    if not shop_settings.can_edit(user["id"], site_key):
        raise HTTPException(status_code=403, detail="이 가게 설정을 바꿀 수 없어요.")
    return {"ok": sms_svc.check_key(body.solapi_key, body.solapi_secret)}
