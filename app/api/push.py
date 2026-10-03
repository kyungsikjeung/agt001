"""휴대폰 알림(웹 푸시) API (OWNER_NOTIFY_PLAN N5).

로그인한 사람이 자기 기기를 켜고 끈다. 바꾸는 요청은 _check_origin으로 막는다(쿠키 인증).
"""
import threading
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import _check_origin
from app.services import auth, push

router = APIRouter()

TEST_GAP_SEC = 20.0  # 시험 알림은 한 사람이 이 간격에 한 번
_last_test: dict[str, float] = {}
_lock = threading.Lock()


def _me(request: Request) -> Optional[dict]:
    return auth.user_for_session(request.cookies.get(auth.SESSION_COOKIE))


def _need_me(request: Request) -> dict:
    user = _me(request)
    if user is None:
        raise HTTPException(status_code=401)
    return user


class KeysIn(BaseModel):
    p256dh: str = Field("", max_length=200)
    auth: str = Field("", max_length=100)


class SubscribeIn(BaseModel):
    endpoint: str = Field("", max_length=1024)
    keys: KeysIn = KeysIn()
    label: Optional[str] = Field(None, max_length=200)


class UnsubscribeIn(BaseModel):
    endpoint: Optional[str] = Field(None, max_length=1024)
    id: Optional[int] = None


class StateIn(BaseModel):
    endpoint: Optional[str] = Field(None, max_length=1024)


def _state(request: Request, endpoint: Optional[str] = None) -> dict:
    user = _me(request)
    return {"configured": push.configured(), "key": push.application_server_key(),
            "logged_in": user is not None,
            "devices": push.devices(user["id"], endpoint) if user else []}


@router.get("/api/push")
def state(request: Request):
    """켤 수 있는지(서버 키), 공개 키, 로그인 여부, 내 기기 목록."""
    return _state(request)


@router.post("/api/push/state")
def state_for_device(body: StateIn, request: Request):
    """GET과 같되 지금 기기의 구독 주소를 받아 '이 기기' 표시를 한다(주소를 쿼리에 싣지 않으려고 POST)."""
    _check_origin(request)
    return _state(request, body.endpoint)


@router.post("/api/push/subscribe")
def subscribe(body: SubscribeIn, request: Request):
    _check_origin(request)
    user = _need_me(request)
    if not push.configured():
        raise HTTPException(status_code=503, detail="휴대폰 알림이 아직 준비되지 않았어요(서버 키 없음).")
    try:
        count = push.subscribe(user["id"], body.endpoint, body.keys.p256dh, body.keys.auth, body.label)
    except push.PushError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "count": count}


@router.post("/api/push/unsubscribe")
def unsubscribe(body: UnsubscribeIn, request: Request):
    _check_origin(request)
    user = _need_me(request)
    return {"ok": push.unsubscribe(user["id"], endpoint=body.endpoint, device_id=body.id)}


@router.post("/api/push/test")
def test(request: Request):
    """내 켜진 기기 모두에 시험 알림 1건. 바로 보내고 받은 기기 수를 알려 준다."""
    _check_origin(request)
    user = _need_me(request)
    if not push.configured():
        raise HTTPException(status_code=503, detail="휴대폰 알림이 아직 준비되지 않았어요(서버 키 없음).")
    now = time.monotonic()
    with _lock:
        if now - _last_test.get(user["id"], -TEST_GAP_SEC) < TEST_GAP_SEC:
            raise HTTPException(status_code=429, detail="잠시 뒤에 다시 눌러 주세요.")
        _last_test[user["id"]] = now
    sent = push.send_to_user(user["id"], {"title": "한마디", "body": "휴대폰 알림이 잘 켜졌어요.",
                                          "url": "/owner", "tag": "agt-test"})
    return {"ok": sent > 0, "sent": sent}
