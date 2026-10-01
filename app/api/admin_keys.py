"""관리자 키 API (ADMIN_CONTRACT §3, D50).

모든 경로는 관리자만이다. 바꾸는 요청은 우리 출처(_check_origin)와 최근 로그인(require_recent_login)도 거친다.
키 값은 응답·기록에 넣지 않는다(상태의 뒤 4자리만 나간다).
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.auth import _check_origin
from app.services import admin, keystore

router = APIRouter()


class KeyIn(BaseModel):
    value: str = Field(default="", max_length=600)


def _admin(request: Request, response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return admin.require_admin(request)


def _change(request: Request, name: str) -> None:
    """바꾸는 요청 공통: 우리 출처, 최근 로그인, 화면에서 바꿀 수 있는 키."""
    _check_origin(request)
    admin.require_recent_login(request)
    if name not in keystore.EDITABLE:
        raise HTTPException(status_code=404)


def _overview() -> dict:
    return {"ready": keystore.ready(), "keys": keystore.status()}


@router.get("/api/admin/keys")
def list_keys(user: dict = Depends(_admin)):
    admin.viewed(user, "keys")
    return _overview()


@router.post("/api/admin/keys/{name}")
def replace_key(name: str, body: KeyIn, request: Request, user: dict = Depends(_admin)):
    """새 키: 형식 확인 → 연결 테스트 → 통과하면 저장(이전 키 7일 보관)."""
    _change(request, name)
    if not keystore.ready():
        raise HTTPException(status_code=409, detail="서버 .env에 TOKEN_ENC_KEY를 먼저 넣어 주세요.")
    try:
        value = keystore.check_format(name, body.value)
    except keystore.KeyError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        ok, msg = keystore.test(name, value)
    except Exception:
        ok, msg = False, "연결 테스트에 실패했어요. 키를 확인해 주세요."
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    try:
        keystore.replace(name, value, user["id"], tested=True)
    except keystore.KeyError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _overview()


@router.post("/api/admin/keys/{name}/rollback")
def rollback_key(name: str, request: Request, user: dict = Depends(_admin)):
    _change(request, name)
    try:
        keystore.rollback(name, user["id"])
    except keystore.KeyError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _overview()


@router.post("/api/admin/keys/{name}/clear")
def clear_key(name: str, request: Request, user: dict = Depends(_admin)):
    _change(request, name)
    try:
        keystore.clear(name, user["id"])
    except keystore.KeyError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _overview()
