"""카카오·구글 로그인 (1-1·1-2·1-3, DECISIONS.md D9·D10·UQ-1·UQ-2, 보안 S-3).

- 로그인 CSRF 방지: state를 DB(해시)와 짧은 쿠키 양쪽에 두고 콜백에서 둘 다 맞아야 통과. 한 번 쓰면 지운다.
- 구글은 PKCE(S256)도 쓴다. 카카오는 client_secret + state.
- 제공자 토큰은 사용자 정보를 한 번 읽는 데만 쓰고 저장하지 않는다(UQ-1).
- 세션: 쿠키에는 무작위 토큰, DB에는 해시만. 쿠키는 __Host- 접두사 + Secure + HttpOnly + SameSite=Lax.
"""
import base64
import datetime
import hashlib
import secrets
import uuid
from typing import Optional
from urllib.parse import urlencode

import httpx
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app import store
from app.config import settings
from app.db.models import LoginSessionRow, OAuthAccountRow, OAuthStateRow, UserRoomRow, UserRow
from app.db.session import get_sessionmaker
from app.security import sanitize_token

SESSION_COOKIE = "__Host-agt001_session"
STATE_COOKIE = "__Host-agt001_oauth"
STATE_TTL = datetime.timedelta(minutes=10)
PROVIDERS = ("kakao", "google")


class AuthError(Exception):
    """사용자에게는 코드만 보여준다(자세한 사유는 서버 로그)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def configured(provider: str) -> bool:
    if provider == "kakao":
        return bool(settings.kakao_rest_api_key and settings.kakao_client_secret)
    if provider == "google":
        return bool(settings.google_client_id and settings.google_client_secret)
    return False


def safe_next(path: Optional[str]) -> str:
    """로그인 뒤 돌아갈 곳은 우리 사이트 안의 경로만(열린 리다이렉트 방지)."""
    p = (path or "/").strip()
    if not p.startswith("/") or p.startswith("//") or "\\" in p or "://" in p or len(p) > 300:
        return "/"
    return p


def begin(provider: str, next_path: str, redirect_uri: str) -> tuple[str, str]:
    """(state 원문, 제공자 로그인 주소). state 원문은 쿠키로도 내려 보낸다."""
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    with get_sessionmaker()() as db, db.begin():
        db.execute(delete(OAuthStateRow).where(OAuthStateRow.expires_at < _now()))
        db.add(OAuthStateRow(state_hash=_hash(state), provider=provider, code_verifier=verifier,
                             next_path=safe_next(next_path), expires_at=_now() + STATE_TTL))
    if provider == "kakao":
        url = "https://kauth.kakao.com/oauth/authorize?" + urlencode({
            "response_type": "code", "client_id": settings.kakao_rest_api_key,
            "redirect_uri": redirect_uri, "state": state,
        })
    else:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
            "response_type": "code", "client_id": settings.google_client_id, "redirect_uri": redirect_uri,
            "scope": "openid email profile", "state": state, "code_challenge": challenge,
            "code_challenge_method": "S256", "prompt": "select_account",
        })
    return state, url


def exchange_code(provider: str, code: str, verifier: str, redirect_uri: str) -> str:
    """인가 코드 → 제공자 액세스 토큰(저장하지 않음)."""
    if provider == "kakao":
        url, data = "https://kauth.kakao.com/oauth/token", {
            "grant_type": "authorization_code", "client_id": settings.kakao_rest_api_key,
            "client_secret": settings.kakao_client_secret, "redirect_uri": redirect_uri, "code": code,
        }
    else:
        url, data = "https://oauth2.googleapis.com/token", {
            "grant_type": "authorization_code", "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "redirect_uri": redirect_uri,
            "code": code, "code_verifier": verifier,
        }
    resp = httpx.post(url, data=data, timeout=10)
    if resp.status_code != 200 or "access_token" not in resp.json():
        raise AuthError("token")
    return resp.json()["access_token"]


def fetch_profile(provider: str, access_token: str) -> tuple[str, str, Optional[str]]:
    """(제공자 회원 ID, 닉네임, 이메일)."""
    headers = {"Authorization": f"Bearer {access_token}"}
    if provider == "kakao":
        resp = httpx.get("https://kapi.kakao.com/v2/user/me", headers=headers, timeout=10)
        if resp.status_code != 200:
            raise AuthError("profile")
        body = resp.json()
        account = body.get("kakao_account") or {}
        nickname = (account.get("profile") or {}).get("nickname") or "카카오 사용자"
        return str(body["id"]), nickname, account.get("email")
    resp = httpx.get("https://openidconnect.googleapis.com/v1/userinfo", headers=headers, timeout=10)
    if resp.status_code != 200:
        raise AuthError("profile")
    body = resp.json()
    return str(body["sub"]), body.get("name") or "구글 사용자", body.get("email")


def finish(provider: str, state: str, state_cookie: Optional[str], code: str, redirect_uri: str) -> tuple[str, str]:
    """콜백 처리 → (user_id, 돌아갈 경로)."""
    if not state or not state_cookie or not secrets.compare_digest(state, state_cookie):
        raise AuthError("state")
    with get_sessionmaker()() as db, db.begin():
        row = db.get(OAuthStateRow, _hash(state))
        if row is None or row.provider != provider or row.expires_at < _now():
            raise AuthError("state")
        verifier, next_path = row.code_verifier, row.next_path
        db.delete(row)  # 한 번만 쓴다
    token = exchange_code(provider, code, verifier, redirect_uri)
    provider_user_id, nickname, email = fetch_profile(provider, token)
    with get_sessionmaker()() as db, db.begin():
        account = db.get(OAuthAccountRow, (provider, provider_user_id))
        if account is None:
            user = UserRow(id=str(uuid.uuid4()), nickname=nickname[:40], email=email)
            db.add(user)
            db.flush()
            db.add(OAuthAccountRow(provider=provider, provider_user_id=provider_user_id, user_id=user.id))
            user_id = user.id
        else:
            user_id = account.user_id
            user = db.get(UserRow, user_id)
            user.nickname = nickname[:40]
            user.last_login_at = _now()
    return user_id, next_path


def create_session(user_id: str) -> str:
    token = secrets.token_urlsafe(32)
    with get_sessionmaker()() as db, db.begin():
        db.add(LoginSessionRow(token_hash=_hash(token), user_id=user_id,
                               expires_at=_now() + datetime.timedelta(days=settings.login_session_days)))
    return token


def user_for_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    with get_sessionmaker()() as db:
        sess = db.get(LoginSessionRow, _hash(token))
        if sess is None or sess.expires_at < _now():
            return None
        user = db.get(UserRow, sess.user_id)
        if user is None or user.deleted_at is not None:
            return None
        provider = db.scalar(select(OAuthAccountRow.provider).where(OAuthAccountRow.user_id == user.id).limit(1))
        return {"id": user.id, "nickname": user.nickname, "provider": provider}


def end_session(token: Optional[str]) -> None:
    if token:
        with get_sessionmaker()() as db, db.begin():
            db.execute(delete(LoginSessionRow).where(LoginSessionRow.token_hash == _hash(token)))


def claim_rooms(user_id: str, member_id_raw: str, room_ids: list[str]) -> int:
    """이 기기에서 쓰던 방(참여자인 방만)을 계정으로 옮긴다. 이미 옮긴 방은 무시."""
    member_id = sanitize_token(member_id_raw or "")
    if not member_id:
        return 0
    claimed = 0
    for raw in room_ids[:50]:
        room_id = sanitize_token(raw)
        room = store.read_room(room_id) if room_id else None
        if room is None or not any(m["member_id"] == member_id for m in room["members"]):
            continue
        with get_sessionmaker()() as db, db.begin():
            result = db.execute(pg_insert(UserRoomRow).values(user_id=user_id, room_id=room_id, member_id=member_id)
                                .on_conflict_do_nothing().returning(UserRoomRow.room_id))
            claimed += 1 if result.first() else 0
    return claimed


def rooms_for_user(user_id: str) -> list[tuple[str, str]]:
    """계정에 옮긴 (방 ID, 그 방의 본인 확인 값)."""
    with get_sessionmaker()() as db:
        rows = db.execute(select(UserRoomRow.room_id, UserRoomRow.member_id).where(UserRoomRow.user_id == user_id)).all()
        return [(r.room_id, r.member_id) for r in rows]
