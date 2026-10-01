"""관리자 키 API (ADMIN_CONTRACT §5 5번). 연결 테스트는 가짜로만 부른다."""
import datetime

import pytest

from app.config import settings
from app.db.models import LoginSessionRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth as auth_svc
from app.services import keystore

ADMIN, OWNER = "u_admin_k", "u_owner_k"
ORIGIN = {"Origin": "http://testserver"}
OLD_KEY, NEW_KEY = "old-secret-value-1111", "new-secret-value-2222"


@pytest.fixture
def admin_client(client, monkeypatch):
    with get_sessionmaker()() as db, db.begin():
        db.add_all([UserRow(id=ADMIN, nickname="관리자"), UserRow(id=OWNER, nickname="사장님")])
    monkeypatch.setattr(settings, "admin_user_ids", ADMIN)
    monkeypatch.setattr(settings, "token_enc_key", "test-token-enc-key-for-admin-keys")
    seen = {"ok": True, "calls": 0}

    def fake_test(name, value):
        seen["calls"] += 1
        return seen["ok"], "가짜 응답 401" if not seen["ok"] else "가짜 응답 200"

    monkeypatch.setattr(keystore, "test", fake_test)
    keystore.invalidate()
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(ADMIN))
    client.seen = seen
    yield client
    keystore.invalidate()


def _post(client, path, body=None, headers=ORIGIN):
    return client.post(path, json=body or {}, headers=headers)


def _status(body, name="gemini_api_key"):
    return next(k for k in body["keys"] if k["name"] == name)


def test_values_never_in_responses(admin_client):
    keystore.replace("gemini_api_key", OLD_KEY, ADMIN, tested=True)
    r = admin_client.get("/api/admin/keys")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert OLD_KEY not in r.text
    k = _status(r.json())
    assert k["source"] == "db" and k["last4"] == OLD_KEY[-4:]
    r = _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY})
    assert r.status_code == 200 and NEW_KEY not in r.text and _status(r.json())["last4"] == NEW_KEY[-4:]


def test_change_needs_origin_and_recent_login(admin_client):
    r = _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY}, headers={})
    assert r.status_code == 403  # 우리 출처가 아님
    token = admin_client.cookies.get(auth_svc.SESSION_COOKIE)
    with get_sessionmaker()() as db, db.begin():
        row = db.get(LoginSessionRow, auth_svc._hash(token))
        row.created_at = row.created_at - datetime.timedelta(minutes=settings.admin_reauth_minutes + 1)
    r = _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY})
    assert r.status_code == 403 and r.json()["detail"] == "reauth"
    assert admin_client.seen["calls"] == 0  # 테스트 전에 막는다


def test_errors_404_409_400(admin_client, monkeypatch):
    assert _post(admin_client, "/api/admin/keys/token_enc_key", {"value": NEW_KEY}).status_code == 404
    assert _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": "short"}).status_code == 400
    admin_client.seen["ok"] = False
    r = _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY})
    assert r.status_code == 400 and r.json()["detail"] == "가짜 응답 401"
    assert _status(admin_client.get("/api/admin/keys").json())["source"] != "db"  # 테스트 실패면 저장 안 함
    monkeypatch.setattr(settings, "token_enc_key", "")
    assert _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY}).status_code == 409
    admin_client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session(OWNER))
    assert _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY}).status_code == 404


def test_rollback_and_clear(admin_client):
    assert _post(admin_client, "/api/admin/keys/gemini_api_key/rollback").status_code == 400  # 되돌릴 키 없음
    keystore.replace("gemini_api_key", OLD_KEY, ADMIN, tested=True)
    _post(admin_client, "/api/admin/keys/gemini_api_key", {"value": NEW_KEY})
    r = _post(admin_client, "/api/admin/keys/gemini_api_key/rollback")
    assert r.status_code == 200 and _status(r.json())["last4"] == OLD_KEY[-4:]
    r = _post(admin_client, "/api/admin/keys/gemini_api_key/clear")
    assert r.status_code == 200 and _status(r.json())["source"] != "db"
