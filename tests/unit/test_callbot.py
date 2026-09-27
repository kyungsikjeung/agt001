"""음성 콜봇 PoC (VOICE_QA_REQUIREMENTS §8): 1:1 방장만 통화권, Twilio 서명 확인, 받아쓴 말 → 채팅·엔진."""
import base64
import json

import pytest

from app.api import callbot
from app.config import settings

HDR = {"X-Member-Id": "owner"}


@pytest.fixture(autouse=True)
def _twilio(monkeypatch):
    for k, v in {"twilio_account_sid": "AC1", "twilio_auth_token": "tok", "twilio_api_key_sid": "SK1",
                 "twilio_api_key_secret": "sec", "twilio_twiml_app_sid": "AP1"}.items():
        monkeypatch.setattr(settings, k, v)
    callbot._tickets.clear()


def _room(client):
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    return room_id


def _ticket(client, room_id):
    r = client.post(f"/api/callbot/token/{room_id}", headers=HDR)
    assert r.status_code == 200, r.text
    payload = r.json()["token"].split(".")[1]
    grants = json.loads(base64.urlsafe_b64decode(payload + "=="))["grants"]
    assert grants["voice"]["outgoing"]["application_sid"] == "AP1"
    return grants["identity"]


def _signed(params, url="http://testserver/api/callbot/twiml"):
    import hashlib
    import hmac
    data = url + "".join(k + params[k] for k in sorted(params))
    return base64.b64encode(hmac.new(b"tok", data.encode(), hashlib.sha1).digest()).decode()


def test_token_only_for_owner_of_one_to_one_room(client):
    room_id = _room(client)
    _ticket(client, room_id)
    assert client.post(f"/api/callbot/token/{room_id}", headers={"X-Member-Id": "stranger"}).status_code == 404
    client.post(f"/room/{room_id}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    r = client.post(f"/api/callbot/token/{room_id}", headers=HDR)
    assert r.status_code == 403 and r.json()["detail"] == "one_to_one_only"
    assert client.post(f"/api/callbot/token/{room_id}", headers={"X-Member-Id": "guest"}).json()["detail"] == "owner_only"


def test_token_off_without_keys(client, monkeypatch):
    monkeypatch.setattr(settings, "twilio_api_key_secret", None)
    assert client.post(f"/api/callbot/token/{_room(client)}", headers=HDR).status_code == 503


def test_twiml_checks_signature_and_connects_relay_in_korean(client):
    room_id = _room(client)
    ticket = _ticket(client, room_id)
    params = {"From": f"client:{ticket}", "CallSid": "CA1"}
    bad = client.post("/api/callbot/twiml", data=params, headers={"X-Twilio-Signature": "nope"})
    assert bad.status_code == 403
    r = client.post("/api/callbot/twiml", data=params, headers={"X-Twilio-Signature": _signed(params)})
    assert r.status_code == 200 and "<ConversationRelay" in r.text
    assert 'language="ko-KR"' in r.text and f'value="{ticket}"' in r.text and "wss://testserver/api/callbot/ws" in r.text
    gone = {"From": "client:unknown"}
    assert "<Hangup/>" in client.post("/api/callbot/twiml", data=gone, headers={"X-Twilio-Signature": _signed(gone)}).text


def test_spoken_answer_goes_into_chat_and_reply_is_read(client):
    room_id = _room(client)
    ticket = _ticket(client, room_id)
    with client.websocket_connect("/api/callbot/ws") as ws:
        ws.send_text(json.dumps({"type": "setup", "customParameters": {"ticket": ticket}}))
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "미용실 사이트 만들고 싶어요", "last": True}))
        assert json.loads(ws.receive_text())["token"] == callbot.MSG_WAIT
        reply = json.loads(ws.receive_text())
        assert reply["type"] == "text" and reply["token"] and "(" not in reply["token"]
    msgs = client.get(f"/room/{room_id}/messages", headers=HDR).json()["messages"]
    assert any(m["kind"] == "chat" and m["text"] == "미용실 사이트 만들고 싶어요" for m in msgs)


def test_call_ends_when_second_person_joins(client, monkeypatch):
    monkeypatch.setattr(callbot.asyncio, "sleep", _no_sleep)
    room_id = _room(client)
    ticket = _ticket(client, room_id)
    client.post(f"/room/{room_id}/chat", json={"member_id": "guest", "nickname": "손님", "message": ""})
    with client.websocket_connect("/api/callbot/ws") as ws:
        ws.send_text(json.dumps({"type": "setup", "customParameters": {"ticket": ticket}}))
        ws.send_text(json.dumps({"type": "prompt", "voicePrompt": "네", "last": True}))
        ws.receive_text()
        assert json.loads(ws.receive_text())["token"] == callbot.MSG_GROUP
        assert json.loads(ws.receive_text())["type"] == "end"


async def _no_sleep(_s):
    return None
