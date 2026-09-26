"""카카오/구글 로그인 전체 흐름 테스트 (작업 A1).

실제 카카오/구글/NIM 호출 금지: settings에는 가짜 키만 넣고
app.services.auth.exchange_code / fetch_profile 를 가짜 함수로 바꾼다.
Secure 쿠키가 오가도록 TestClient는 base_url="https://testserver" 로 만든다.
"""
import datetime
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.db.models import LoginSessionRow
from app.db.session import get_sessionmaker
from app.main import create_app
from app.services import auth as auth_service

ORIGIN = "https://testserver"
SESSION_COOKIE = auth_service.SESSION_COOKIE
STATE_COOKIE = auth_service.STATE_COOKIE


def _wipe_auth_tables():
    with get_sessionmaker()() as db, db.begin():
        db.execute(text(
            "TRUNCATE user_rooms, login_sessions, oauth_accounts, oauth_states, users CASCADE"
        ))


def _fake_keys(monkeypatch):
    monkeypatch.setattr(settings, "kakao_rest_api_key", "fake-kakao-key")
    monkeypatch.setattr(settings, "kakao_client_secret", "fake-kakao-secret")
    monkeypatch.setattr(settings, "google_client_id", "fake-google-id")
    monkeypatch.setattr(settings, "google_client_secret", "fake-google-secret")
    monkeypatch.setattr(settings, "public_base_url", None)


def _fake_provider(monkeypatch, provider_user_id="fake-user-1",
                   nickname="fake-nick-1", email="fake@example.com"):
    monkeypatch.setattr(
        auth_service, "exchange_code",
        lambda provider, code, verifier, redirect_uri: {"access_token": "fake-access-token"},
    )
    monkeypatch.setattr(
        auth_service, "fetch_profile",
        lambda provider, access_token: (provider_user_id, nickname, email),
    )


@pytest.fixture
def sclient(client, monkeypatch):
    """conftest의 격리(store 초기화, 가짜 LLM) 위에 https 클라이언트를 얹는다."""
    _fake_keys(monkeypatch)
    _fake_provider(monkeypatch)
    _wipe_auth_tables()
    with TestClient(create_app(), base_url="https://testserver") as c:
        yield c
    _wipe_auth_tables()


def _start(c, provider, next="/projects"):
    return c.get(f"/auth/{provider}/start", params={"next": next}, follow_redirects=False)


def _query_param(location, name):
    return parse_qs(urlparse(location).query)[name][0]


def _callback(c, provider, state, code="fake-code", error=None):
    params = {}
    if error is not None:
        params["error"] = error
    if code is not None:
        params["code"] = code
    if state is not None:
        params["state"] = state
    return c.get(f"/auth/{provider}/callback", params=params, follow_redirects=False)


def _login(c, provider="kakao", next="/projects"):
    r = _start(c, provider, next)
    assert r.status_code == 303, r.text
    state = _query_param(r.headers["location"], "state")
    r2 = _callback(c, provider, state)
    assert r2.status_code == 303, r2.headers.get("location")
    return r2


def _set_cookie_headers(resp):
    try:
        return resp.headers.get_list("set-cookie")
    except AttributeError:
        v = resp.headers.get("set-cookie", "")
        return [v] if v else []


def _make_room_with_member(c, member_id, nickname="tester"):
    r = c.post("/room")
    assert r.status_code == 200, r.text
    room_id = r.json()["room_id"]
    j = c.post(f"/room/{room_id}/chat",
               json={"member_id": member_id, "nickname": nickname, "message": ""})
    assert j.status_code == 200, j.text
    return room_id


# a. 키가 없으면 start에서 안내로 돌려보낸다.
def test_start_not_ready_without_keys(sclient, monkeypatch):
    monkeypatch.setattr(settings, "kakao_rest_api_key", None)
    monkeypatch.setattr(settings, "kakao_client_secret", None)
    r = sclient.get("/auth/kakao/start", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/?login_error=kakao_not_ready"

    monkeypatch.setattr(settings, "google_client_id", None)
    monkeypatch.setattr(settings, "google_client_secret", None)
    r = sclient.get("/auth/google/start", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/?login_error=google_not_ready"


# b. start 리다이렉트와 state 쿠키.
@pytest.mark.parametrize("provider", ["kakao", "google"])
def test_start_redirect_and_state_cookie(sclient, provider):
    r = _start(sclient, provider)
    assert r.status_code == 303
    loc = r.headers["location"]
    if provider == "kakao":
        assert "kauth.kakao.com" in loc
    else:
        assert "accounts.google.com" in loc
        assert "code_challenge_method=S256" in loc
    joined = " | ".join(_set_cookie_headers(r)).lower()
    assert STATE_COOKIE.lower() in joined
    assert "secure" in joined
    assert "httponly" in joined
    assert "samesite=lax" in joined


# c. 정상 콜백: next로 이동, 세션 쿠키, /api/me.
@pytest.mark.parametrize("provider", ["kakao", "google"])
def test_callback_success_sets_session_and_me(sclient, provider):
    r = _login(sclient, provider, next="/projects")
    assert r.headers["location"] == "/projects"
    joined = " | ".join(_set_cookie_headers(r)).lower()
    assert SESSION_COOKIE.lower() in joined
    assert "httponly" in joined
    assert "secure" in joined
    assert "samesite=lax" in joined

    me = sclient.get("/api/me")
    assert me.status_code == 200
    user = me.json()["user"]
    assert user["id"]
    assert user["nickname"]
    assert user["provider"] == provider


# d-1. state 쿠키 없음.
@pytest.mark.parametrize("provider", ["kakao", "google"])
def test_callback_state_cookie_missing(sclient, provider):
    r = _start(sclient, provider)
    state = _query_param(r.headers["location"], "state")
    sclient.cookies.clear()
    r2 = _callback(sclient, provider, state)
    assert r2.status_code == 303
    assert r2.headers["location"] == f"/?login_error={provider}_state"


# d-2. state 불일치(쿼리 변조, 쿠키 변조).
@pytest.mark.parametrize("provider", ["kakao", "google"])
def test_callback_state_mismatch(sclient, provider):
    r = _start(sclient, provider)
    state = _query_param(r.headers["location"], "state")
    r2 = _callback(sclient, provider, "tampered-" + state)
    assert r2.status_code == 303
    assert r2.headers["location"] == f"/?login_error={provider}_state"

    r = _start(sclient, provider)
    state = _query_param(r.headers["location"], "state")
    sclient.cookies.clear()
    sclient.cookies.set(STATE_COOKIE, "wrong-value", domain="testserver")
    r2 = _callback(sclient, provider, state)
    assert r2.status_code == 303
    assert r2.headers["location"] == f"/?login_error={provider}_state"


# d-3. state 재사용(두 번째 콜백은 거부).
@pytest.mark.parametrize("provider", ["kakao", "google"])
def test_callback_state_reuse_rejected(sclient, provider):
    r = _start(sclient, provider)
    state = _query_param(r.headers["location"], "state")
    first = _callback(sclient, provider, state)
    assert first.status_code == 303
    assert first.headers["location"] == "/projects"

    sclient.cookies.set(STATE_COOKIE, state, domain="testserver")
    second = _callback(sclient, provider, state, code="fake-code-2")
    assert second.status_code == 303
    assert second.headers["location"] == f"/?login_error={provider}_state"


# e. 제공자 측 거부(error=access_denied).
@pytest.mark.parametrize("provider", ["kakao", "google"])
def test_callback_denied(sclient, provider):
    r = _callback(sclient, provider, "any-state", code="any-code", error="access_denied")
    assert r.status_code == 303
    assert r.headers["location"] == f"/?login_error={provider}_denied"


# f. next 열린 리다이렉트 방지.
@pytest.mark.parametrize("evil", ["//evil.com", "https://evil.com", "/\\evil"])
def test_next_open_redirect_blocked(sclient, evil):
    r = _login(sclient, "kakao", next=evil)
    assert r.headers["location"] == "/"


# g. 같은 제공자 계정 재로그인: 같은 user id, 닉네임 갱신.
def test_repeat_login_same_user_updates_nickname(sclient, monkeypatch):
    _login(sclient, "kakao")
    first_id = sclient.get("/api/me").json()["user"]["id"]

    monkeypatch.setattr(
        auth_service, "fetch_profile",
        lambda provider, access_token: ("fake-user-1", "fake-nick-2", "fake@example.com"),
    )
    sclient.cookies.clear()
    _login(sclient, "kakao")
    user = sclient.get("/api/me").json()["user"]
    assert user["id"] == first_id
    assert user["nickname"] == "fake-nick-2"


# h-1. 세션 쿠키 없음.
def test_me_without_cookie_401(sclient):
    sclient.cookies.clear()
    assert sclient.get("/api/me").status_code == 401


# h-2. 만료 세션.
def test_me_expired_session_401(sclient):
    _login(sclient)
    token = sclient.cookies.get(SESSION_COOKIE)
    assert token
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    past = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
    with get_sessionmaker()() as db, db.begin():
        row = db.get(LoginSessionRow, token_hash)
        assert row is not None
        row.expires_at = past
    assert sclient.get("/api/me").status_code == 401


# i-1. logout Origin 검사(없음/다름은 403, 세션 유지).
def test_logout_origin_rejected(sclient):
    _login(sclient)
    assert sclient.post("/api/logout").status_code == 403
    assert sclient.post("/api/logout", headers={"Origin": "https://evil.example"}).status_code == 403
    assert sclient.get("/api/me").status_code == 200


# i-2. logout 성공(204, 이후 /api/me 401).
def test_logout_success_clears_session(sclient):
    _login(sclient)
    r = sclient.post("/api/logout", headers={"Origin": ORIGIN})
    assert r.status_code == 204
    assert sclient.get("/api/me").status_code == 401


# j-1. claim: 참여자 방만 셈, 남의 방/없는 방은 0, 재호출 0.
def test_claim_counts_only_participant_and_idempotent(sclient):
    own = _make_room_with_member(sclient, "claim-m1")
    other = _make_room_with_member(sclient, "someone-else")
    _login(sclient)
    headers = {"Origin": ORIGIN, "X-Member-Id": "claim-m1"}
    body = {"room_ids": [own, other, "no-such-room"]}

    r = sclient.post("/api/me/claim", json=body, headers=headers)
    assert r.status_code == 200
    assert r.json() == {"claimed": 1}

    r2 = sclient.post("/api/me/claim", json=body, headers=headers)
    assert r2.status_code == 200
    assert r2.json() == {"claimed": 0}


# j-2. claim Origin 검사.
def test_claim_origin_rejected(sclient):
    own = _make_room_with_member(sclient, "claim-m1")
    _login(sclient)
    body = {"room_ids": [own]}
    assert sclient.post("/api/me/claim", json=body).status_code == 403
    bad = {"Origin": "https://evil.example", "X-Member-Id": "claim-m1"}
    assert sclient.post("/api/me/claim", json=body, headers=bad).status_code == 403
