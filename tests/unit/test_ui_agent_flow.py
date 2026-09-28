"""채팅 흐름 속 UI 에이전트 (J11, DB 사용).

규칙 3안 뒤 수정 조각 저장·다시 그리기·안내 한 줄, 고른 뒤에는 안 바꿈,
레거시 코드생성 끔에서 상태가 멈추지 않음을 본다.
"""
import json

import pytest

from app import llm, store
from app.services import chat_flow, codegen as codegen_svc
from app.services import design as design_svc
from app.services import ui_agent
from app.config import settings

SKIP = "나머지는 알아서, 시안 먼저 볼게요"
PATCH_JSON = json.dumps({"v1": {"labels": {"menu": "대표 메뉴"}}, "v2": {}, "v3": {}})


def _chat(client, message, session_id=None):
    body = {"message": message}
    if session_id is not None:
        body["session_id"] = session_id
    r = client.post("/chat", json=body)
    assert r.status_code == 200
    return r.json()


def _fresh_session(client):
    d = _chat(client, "")
    assert d["state"] == "GATHERING"
    return d["session_id"]


def _to_quoted(client, s):
    d0 = _chat(client, "카페 예약 서비스 만들어줘", s)
    assert d0["state"] == "GATHERING"
    d1 = _chat(client, SKIP, s)
    assert d1["state"] == "AWAIT_APPROVAL"
    d2 = _chat(client, "승인", s)
    assert d2["state"] == "QUOTED"


@pytest.fixture(autouse=True)
def _agent_on(client, monkeypatch):
    """conftest는 에이전트를 끈다. 이 파일은 에이전트 흐름을 보므로 켠다(client 뒤에 적용)."""
    monkeypatch.setattr(settings, "ui_agent_enabled", True)


@pytest.fixture
def sync_polish(monkeypatch):
    """백그라운드 스레드 대신 동기로 돌린다."""

    def fake_chat_json(system, user, **kw):
        if "시안 3안을 다듬는" in (system or ""):
            return PATCH_JSON
        return '{"updates": []}'

    monkeypatch.setattr(llm, "chat_json", fake_chat_json)
    monkeypatch.setattr(chat_flow, "polish_runner",
                        lambda sid, rid, room: chat_flow.polish_designs(sid, rid, room))


def test_polish_saves_patch_rerenders_and_announces(client, sync_polish, monkeypatch):
    calls = []
    real_render = design_svc.render_variants

    def spy(requirement_id, card, **kw):
        calls.append((requirement_id, kw.get("log_shown", True)))
        return real_render(requirement_id, card, **kw)

    monkeypatch.setattr(design_svc, "render_variants", spy)
    s = _fresh_session(client)
    _to_quoted(client, s)
    d = _chat(client, "진행", s)
    assert d["state"] == "GENERATING" and "design_url" in d
    card = store.read_session(s)["prd"]
    assert card["design_patch"]["v1"] == {"labels": {"menu": "대표 메뉴"}}
    assert card["design_patch"]["made_at"] and card["design_patch"]["model"]
    assert len(calls) >= 2  # 규칙 3안 + 다듬은 안 다시 그리기
    assert calls[-1][1] is False  # 다시 그릴 때는 '보여 줌'을 또 세지 않는다(D45)
    nxt = _chat(client, "잘 봤어요", s)
    assert nxt["state"] == "DONE"
    assert "시안을 더 다듬었어요" in nxt["reply"] and "1안" in nxt["reply"]
    again = _chat(client, "고마워요", s)
    assert "시안을 더 다듬었어요" not in again["reply"]  # 한 번만


def test_polish_skipped_after_choice(client, sync_polish, monkeypatch):
    s = _fresh_session(client)
    _to_quoted(client, s)
    _chat(client, "진행", s)
    before = store.read_session(s)["prd"]["design_patch"]
    assert before
    renders = []
    real_render = design_svc.render_variants
    monkeypatch.setattr(design_svc, "render_variants",
                        lambda req, card: (renders.append(req), real_render(req, card))[1])
    _chat(client, "2안으로 할게요", s)
    assert store.read_session(s)["prd"]["design_choice"] == "v2"
    session = store.read_session(s)
    chat_flow.polish_designs(s, session["requirement_id"], None)
    assert store.read_session(s)["prd"]["design_patch"] == before  # 안 바꿈
    assert renders == []


def test_codegen_off_moves_to_done(client, sync_polish, monkeypatch):
    started = []
    monkeypatch.setattr(codegen_svc, "start", lambda *a: started.append(a))
    s = _fresh_session(client)
    _to_quoted(client, s)
    d = _chat(client, "진행", s)
    assert d["state"] == "GENERATING"
    assert started == []  # 레거시 코드생성을 부르지 않는다
    assert store.read_session(s)["codegen"]["status"] == "skipped"
    nxt = _chat(client, "아무 메시지", s)
    assert nxt["state"] == "DONE"  # GENERATING에 멈추지 않는다
    # 공개 전이라 사이트 주소는 아직 없다(deploy.site_url은 공개본이 있어야 주소를 준다). 대신 공개 안내가 나간다.
    assert "deploy_url" not in nxt and "공개" in nxt["reply"]


def test_polish_none_keeps_rule_variants(client, monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **kw: '{"updates": []}')
    monkeypatch.setattr(chat_flow, "polish_runner",
                        lambda sid, rid, room: chat_flow.polish_designs(sid, rid, room))
    monkeypatch.setattr(ui_agent, "improve", lambda card, variants, **kw: None)
    s = _fresh_session(client)
    _to_quoted(client, s)
    _chat(client, "진행", s)
    assert "design_patch" not in store.read_session(s)["prd"]
    nxt = _chat(client, "잘 봤어요", s)
    assert "시안을 더 다듬었어요" not in nxt["reply"]


def _room_chat(client, rid, message, member="owner"):
    r = client.post(f"/room/{rid}/chat",
                    json={"member_id": member, "nickname": "사장님", "message": message})
    assert r.status_code == 200
    return r.json()


def test_room_polish_posts_message(client, sync_polish):
    rid = client.post("/room").json()["room_id"]
    _room_chat(client, rid, "")
    _room_chat(client, rid, "카페 예약 서비스 만들어줘")
    _room_chat(client, rid, SKIP)
    _room_chat(client, rid, "승인")
    _room_chat(client, rid, "진행")
    msgs = client.get(f"/room/{rid}/messages", headers={"X-Member-Id": "owner"}).json()["messages"]
    polished = [m for m in msgs if "시안을 더 다듬었어요" in m["text"]]
    assert polished and "1안" in polished[0]["text"]
