"""문의·경고를 사장님 카카오톡으로 ("나에게 보내기", D32 ①, contracts/ROOM_FEATURES_API.md §6).

- 사장님이 "문의를 카톡으로 받기"로 추가 동의(talk_message)하면 카카오 리프레시 토큰만 암호화해 저장한다(UQ-1 예외).
- 보낼 때 리프레시 토큰으로 액세스 토큰을 새로 받고(저장 안 함), 카카오가 새 리프레시 토큰을 주면 바꿔 저장한다.
- 누구에게 보내나: 방장(참여자 목록 맨 앞)이 카카오로 로그인해 그 방을 계정에 옮겨 둔 경우 그 계정.
- 암호화 키: TOKEN_ENC_KEY(설정) 또는 없으면 카카오 Client Secret에서 만든 키. Client Secret을 바꾸면 알림을 다시 켜야 한다.
"""
import base64
import datetime
import hashlib
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import select, update

from app import store
from app.config import settings
from app.db.models import OAuthAccountRow, UserRoomRow
from app.db.session import get_sessionmaker
from app.services import keystore

log = logging.getLogger(__name__)
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _fernet():
    from cryptography.fernet import Fernet
    raw = settings.token_enc_key or ("agt001-talk:" + (settings.kakao_client_secret or ""))
    if not raw.strip(":") or raw == "agt001-talk:":
        raise RuntimeError("암호화 키 없음")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest()))


def save_refresh_token(provider_user_id: str, refresh_token: str, expires_in: Optional[int]) -> None:
    enc = _fernet().encrypt(refresh_token.encode()).decode()
    expires = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=int(expires_in))) if expires_in else None
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(OAuthAccountRow).where(OAuthAccountRow.provider == "kakao",
                                                 OAuthAccountRow.provider_user_id == provider_user_id)
                   .values(talk_refresh_enc=enc, talk_refresh_expires_at=expires))


def forget(user_id: str) -> None:
    with get_sessionmaker()() as db, db.begin():
        db.execute(update(OAuthAccountRow).where(OAuthAccountRow.user_id == user_id, OAuthAccountRow.provider == "kakao")
                   .values(talk_refresh_enc=None, talk_refresh_expires_at=None))


def _account_for_user(user_id: str) -> Optional[OAuthAccountRow]:
    with get_sessionmaker()() as db:
        return db.scalar(select(OAuthAccountRow).where(OAuthAccountRow.user_id == user_id,
                                                       OAuthAccountRow.provider == "kakao",
                                                       OAuthAccountRow.talk_refresh_enc.is_not(None)))


def is_linked(user_id: str) -> bool:
    return _account_for_user(user_id) is not None


def owner_user_id(room_id: str) -> Optional[str]:
    """방장이 계정에 옮겨 둔 방이면 그 계정 ID."""
    room = store.read_room(room_id)
    if not room or not room["members"]:
        return None
    owner = room["members"][0]["member_id"]
    with get_sessionmaker()() as db:
        return db.scalar(select(UserRoomRow.user_id).where(UserRoomRow.room_id == room_id,
                                                          UserRoomRow.member_id == owner))


def _access_token(acc: OAuthAccountRow) -> Optional[str]:
    f = _fernet()
    refresh = f.decrypt(acc.talk_refresh_enc.encode()).decode()
    resp = httpx.post(TOKEN_URL, data={"grant_type": "refresh_token", "client_id": keystore.get("kakao_rest_api_key"),
                                       "client_secret": keystore.get("kakao_client_secret"), "refresh_token": refresh},
                      timeout=10)
    if resp.status_code != 200:
        log.warning("카카오 토큰 갱신 실패 status=%s", resp.status_code)
        return None
    body = resp.json()
    if body.get("refresh_token"):
        save_refresh_token(acc.provider_user_id, body["refresh_token"], body.get("refresh_token_expires_in"))
    return body.get("access_token")


def send_to_room_owner(room_id: str, text: str) -> bool:
    user_id = owner_user_id(room_id)
    acc = _account_for_user(user_id) if user_id else None
    if acc is None:
        return False
    token = _access_token(acc)
    if not token:
        return False
    base = (settings.public_base_url or "https://144.24.91.250.sslip.io").rstrip("/")
    link = f"{base}/room.html?room={room_id}"
    template = {"object_type": "text", "text": ("[agt001] " + text)[:200],
                "link": {"web_url": link, "mobile_web_url": link}, "button_title": "채팅방 열기"}
    resp = httpx.post(MEMO_URL, headers={"Authorization": f"Bearer {token}"},
                      data={"template_object": json.dumps(template, ensure_ascii=False)}, timeout=10)
    if resp.status_code != 200:
        log.warning("카카오 나에게 보내기 실패 status=%s body=%s", resp.status_code, resp.text[:200])
        return False
    return True
