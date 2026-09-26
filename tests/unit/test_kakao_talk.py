"""문의 → 사장님 카톡(계약 §6): 토큰은 암호화 저장, 방장 계정에만, 새 리프레시 토큰으로 교체."""
import json

import pytest

from app import store
from app.config import settings
from app.db.models import OAuthAccountRow, UserRow
from app.db.session import get_sessionmaker
from app.services import auth, kakao_talk, notify


class _Resp:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture
def kakao(monkeypatch):
    monkeypatch.setattr(settings, "kakao_rest_api_key", "k-test")
    monkeypatch.setattr(settings, "kakao_client_secret", "s-test")
    monkeypatch.setattr(notify, "SYNC", True)
    sent = []

    def post(url, data=None, headers=None, timeout=None):
        if url == kakao_talk.TOKEN_URL:
            return _Resp(200, {"access_token": "acc-1", "refresh_token": "ref-2", "refresh_token_expires_in": 5000000})
        sent.append(json.loads(data["template_object"]))
        return _Resp(200, {"result_code": 0})

    monkeypatch.setattr(kakao_talk.httpx, "post", post)
    return sent


def _owner_room_linked(client):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    with get_sessionmaker()() as db, db.begin():
        db.add(UserRow(id="u1", nickname="사장님"))
        db.flush()
        db.add(OAuthAccountRow(provider="kakao", provider_user_id="kk1", user_id="u1"))
    auth.claim_rooms("u1", "owner", [rid])
    kakao_talk.save_refresh_token("kk1", "ref-1", 5000000)
    return rid


def test_token_encrypted_and_sent_to_owner(client, kakao):
    rid = _owner_room_linked(client)
    with get_sessionmaker()() as db:
        enc = db.get(OAuthAccountRow, ("kakao", "kk1")).talk_refresh_enc
    assert enc and "ref-1" not in enc  # 원문 저장 안 함
    assert kakao_talk.send_to_room_owner(rid, "사이트로 새 문의가 왔어요")
    assert kakao[-1]["object_type"] == "text" and "새 문의" in kakao[-1]["text"]
    # 카카오가 준 새 리프레시 토큰으로 바꿔 저장했다
    with get_sessionmaker()() as db:
        enc2 = db.get(OAuthAccountRow, ("kakao", "kk1")).talk_refresh_enc
    assert kakao_talk._fernet().decrypt(enc2.encode()).decode() == "ref-2"


def test_not_linked_sends_nothing(client, kakao):
    rid = client.post("/room").json()["room_id"]
    client.post(f"/room/{rid}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    assert kakao_talk.send_to_room_owner(rid, "x") is False and kakao == []


def test_inquiry_triggers_owner_kakao(client, kakao):
    rid = _owner_room_linked(client)
    key = store.read_session(store.read_room(rid)["session_id"])["requirement_id"]
    r = client.post(f"/api/inquiries/{key}", data={"contact": "010-2222-3333", "message": "레슨 문의", "agree": "yes"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert any("레슨 문의" in t["text"] for t in kakao)


def test_start_with_talk_scope(client, kakao):
    r = client.get("/auth/kakao/start?talk=1&next=/", follow_redirects=False)
    assert r.status_code == 303 and "scope=talk_message" in r.headers["location"]
