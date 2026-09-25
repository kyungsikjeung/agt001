"""1:1 /chat 전체 흐름. 원본 backend.py 상태머신과 동일해야 한다."""
from app import store
from app.services import codegen as codegen_svc

from conftest import fake_codegen_timeout, fake_codegen_unavailable


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


def _to_quoted(client, s, request="카페 예약 서비스 만들어줘"):
    d1 = _chat(client, request, s)
    assert d1["state"] == "AWAIT_APPROVAL"
    d2 = _chat(client, "승인", s)
    assert d2["state"] == "QUOTED"
    return d2


def test_empty_message_greeting(client):
    data = _chat(client, "")
    assert data["state"] == "GATHERING"
    assert "어떤 프로젝트" in data["reply"]


def test_full_flow_to_done(client):
    s = _fresh_session(client)
    # 요청 → AWAIT_APPROVAL
    d1 = _chat(client, "카페 예약 서비스 만들어줘", s)
    assert d1["state"] == "AWAIT_APPROVAL"
    assert "승인/거절" in d1["reply"]

    # 모호한 답 → 재질문 유지
    d2 = _chat(client, "음...", s)
    assert d2["state"] == "AWAIT_APPROVAL"
    assert "승인 또는 거절" in d2["reply"]

    # 거절 → GATHERING
    d3 = _chat(client, "거절", s)
    assert d3["state"] == "GATHERING"

    # 다시 요청 → 승인 → QUOTED (견적 텍스트 포함)
    _chat(client, "카페 예약 서비스 만들어줘", s)
    d4 = _chat(client, "승인", s)
    assert d4["state"] == "QUOTED"
    assert "추천" in d4["reply"]

    # QUOTED에서 진행 외 텍스트 → GATHERING
    d5 = _chat(client, "취소", s)
    assert d5["state"] == "GATHERING"

    # 다시 승인 → 진행 → GENERATING + design 링크가 딱 한 번
    _chat(client, "카페 예약 서비스 만들어줘", s)
    _chat(client, "승인", s)
    d6 = _chat(client, "진행", s)
    assert d6["state"] == "GENERATING"
    assert "design_url" in d6
    assert "design_preview_url" in d6

    # 다음 응답에는 design 링크가 없음 (폴링이 곧 완료 전이)
    d7 = _chat(client, "아무 메시지", s)
    assert "design_url" not in d7
    assert "design_preview_url" not in d7

    # 폴링 → DONE + deploy_url이 /site/<id>/ 로 끝남
    assert d7["state"] == "DONE"
    sess = store.sessions.get(s)
    assert sess["deploy_url"].endswith(f"/site/{sess['requirement_id']}/")
    assert d7["deploy_url"] == sess["deploy_url"]

    # DONE 후 메시지 → GATHERING
    d8 = _chat(client, "새 프로젝트 하고 싶어", s)
    assert d8["state"] == "GATHERING"


def test_design_url_sent_exactly_once(client):
    s = _fresh_session(client)
    _to_quoted(client, s)
    first = _chat(client, "진행", s)
    assert "design_url" in first
    second = _chat(client, "poll", s)
    assert "design_url" not in second
    assert "design_preview_url" not in second


def test_codegen_timeout_returns_to_quoted(client, monkeypatch):
    monkeypatch.setattr(codegen_svc, "start", fake_codegen_timeout)
    s = _fresh_session(client)
    _to_quoted(client, s)
    d = _chat(client, "진행", s)
    assert d["state"] == "GENERATING"
    nxt = _chat(client, "poll", s)
    assert nxt["state"] == "QUOTED"
    assert "실패" in nxt["reply"]


def test_codegen_unavailable_done_without_deploy(client, monkeypatch):
    monkeypatch.setattr(codegen_svc, "start", fake_codegen_unavailable)
    s = _fresh_session(client)
    _to_quoted(client, s)
    _chat(client, "진행", s)
    nxt = _chat(client, "poll", s)
    assert nxt["state"] == "DONE"
    assert "deploy_url" not in nxt
