"""API 키 저장소 (DECISIONS.md D50): 암호화 저장·뒤 4자리만·테스트 통과해야 저장·7일 되돌리기·기록·재시작 없이 적용."""
import pytest
from sqlalchemy import select

from app import llm
from app.config import settings
from app.db.models import AdminAuditRow, SecretRow
from app.db.session import get_sessionmaker
from app.services import keystore

NEW = "nvapi-NEWKEY-abcdefgh1234"
NEWER = "nvapi-NEWERKEY-zzzz9876"


@pytest.fixture
def ready(client, monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", "test-enc-key-0123456789")
    monkeypatch.setattr(settings, "nim_api_key", "env-key-00000000")
    keystore.invalidate()
    yield
    keystore.invalidate()


def test_editing_is_closed_without_separate_encryption_key(client, monkeypatch):
    monkeypatch.setattr(settings, "token_enc_key", None)
    keystore.invalidate()
    assert keystore.ready() is False
    with pytest.raises(keystore.KeyError_):
        keystore.replace("nim_api_key", NEW, "admin-1", tested=True)
    assert keystore.get("nim_api_key") == settings.nim_api_key  # .env 값 그대로


def test_replace_needs_passed_test_and_valid_format(ready):
    with pytest.raises(keystore.KeyError_):
        keystore.replace("nim_api_key", NEW, "admin-1", tested=False)
    with pytest.raises(keystore.KeyError_):
        keystore.replace("nim_api_key", "has space 12345", "admin-1", tested=True)
    with pytest.raises(keystore.KeyError_):
        keystore.replace("database_url", NEW, "admin-1", tested=True)  # 화면에서 못 바꾸는 값


def test_replace_encrypts_shows_last4_applies_now_and_audits_without_value(ready):
    assert keystore.get("nim_api_key") == "env-key-00000000"
    keystore.replace("nim_api_key", NEW, "admin-1", tested=True)
    with get_sessionmaker()() as db:
        row = db.get(SecretRow, "nim_api_key")
        audits = db.scalars(select(AdminAuditRow)).all()
    assert NEW not in row.value_enc and row.last4 == "1234"
    assert keystore.get("nim_api_key") == NEW  # 재시작 없이
    st = next(s for s in keystore.status() if s["name"] == "nim_api_key")
    assert st["source"] == "db" and st["last4"] == "1234" and st["updated_by"] == "admin-1"
    assert [(a.action, a.target) for a in audits] == [("key_replace", "nim_api_key")]
    assert NEW not in str(audits[0].detail)


def test_rollback_and_clear(ready):
    keystore.replace("nim_api_key", NEW, "admin-1", tested=True)
    keystore.replace("nim_api_key", NEWER, "admin-1", tested=True)
    assert keystore.get("nim_api_key") == NEWER
    keystore.rollback("nim_api_key", "admin-1")
    assert keystore.get("nim_api_key") == NEW
    keystore.clear("nim_api_key", "admin-1")
    assert keystore.get("nim_api_key") == "env-key-00000000"
    assert next(s for s in keystore.status() if s["name"] == "nim_api_key")["can_rollback"]


def test_llm_client_uses_new_key_after_replace(ready):
    before = llm._client().api_key
    keystore.replace("nim_api_key", NEW, "admin-1", tested=True)
    assert before == "env-key-00000000" and llm._client().api_key == NEW


def test_connection_test_uses_the_new_key(ready, monkeypatch):
    seen = {}

    class R:
        status_code = 401

    def post(url, **kw):
        seen["auth"] = kw["headers"]["Authorization"]
        return R()
    monkeypatch.setattr(keystore.httpx, "post", post)
    ok, msg = keystore.test("nim_api_key", NEW)
    assert ok is False and "401" in msg and seen["auth"] == f"Bearer {NEW}"
    ok, msg = keystore.test("google_client_secret", "GOCSPX-abcdefgh")
    assert ok and "형식만" in msg
