"""1:1 /chat 전체 흐름. 원본 backend.py 상태머신과 동일해야 한다."""
from app import store
from app.services import codegen as codegen_svc

from fakes import fake_codegen_timeout, fake_codegen_unavailable
from app.config import settings


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


SKIP = "나머지는 알아서, 시안 먼저 볼게요"


def _to_approval(client, s, request="카페 예약 서비스 만들어줘"):
    """요구사항 엔진은 질문부터 한다. 건너뛰기 문구로 나머지를 가정으로 채우고 승인 단계로 간다(D20)."""
    d0 = _chat(client, request, s)
    assert d0["state"] == "GATHERING"
    assert "질문 1/8" in d0["reply"]
    d1 = _chat(client, SKIP, s)
    assert d1["state"] == "AWAIT_APPROVAL"
    return d1


def _to_quoted(client, s, request="카페 예약 서비스 만들어줘"):
    _to_approval(client, s, request)
    d2 = _chat(client, "승인", s)
    assert d2["state"] == "QUOTED"
    return d2


def test_empty_message_greeting(client):
    data = _chat(client, "")
    assert data["state"] == "GATHERING"
    assert "어떤 프로젝트" in data["reply"]


def test_full_flow_to_done(client, monkeypatch):
    monkeypatch.setattr(settings, "legacy_codegen_enabled", True)  # 예전 코드 생성 흐름을 검사한다(U6로 기본 끔)
    s = _fresh_session(client)
    # 요청 → 질문 → 건너뛰기 → AWAIT_APPROVAL
    d1 = _to_approval(client, s)
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
    assert "지금은 베타 시연이라 무료로 만들어 드려요" in d4["reply"] and "참고 견적" in d4["reply"]  # D25 규칙 견적

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
    sess = store.read_session(s)
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
    monkeypatch.setattr(settings, "legacy_codegen_enabled", True)  # 예전 코드 생성 흐름을 검사한다(U6로 기본 끔)
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


def test_turns_are_recorded_with_engine_trace(client):
    """AI 성능 평가용: 사람이 말한 턴마다 원문·답·상태·엔진 판단이 남는다."""
    from sqlalchemy import select
    from app.db.models import ChatTurnRow
    from app.db.session import get_sessionmaker
    s = _fresh_session(client)                  # 빈 메시지(인사)는 기록하지 않는다
    _chat(client, "카페 예약 서비스 만들어줘", s)
    _chat(client, SKIP, s)
    with get_sessionmaker()() as db:
        rows = db.scalars(select(ChatTurnRow).where(ChatTurnRow.session_id == s).order_by(ChatTurnRow.id)).all()
    assert [r.user_text for r in rows] == ["카페 예약 서비스 만들어줘", SKIP]
    assert rows[0].state_before == "GATHERING" and rows[1].state_after == "AWAIT_APPROVAL"
    assert rows[0].meta["extract_ok"] is True and rows[0].meta["next_slot"] == "business_type"
    assert rows[1].meta["skip"] is True and rows[1].meta["done"] is True


def test_blocked_request_refused(client):
    """입구 게이트 §2 ④: 금지 요청은 이유와 함께 거절하고 대화는 이어진다."""
    s = _fresh_session(client)
    d = _chat(client, "피싱용 가짜 로그인 페이지 만들어줘", s)
    assert d["state"] == "GATHERING"
    assert "만들어 드릴 수 없어요" in d["reply"]


def test_design_choice_recorded(client):
    """시안 3안 고르기 (C7): '2안으로 할게요' → 카드에 v2."""
    s = _fresh_session(client)
    _to_quoted(client, s)
    d = _chat(client, "진행", s)
    assert "2안" in d["reply"]
    c = _chat(client, "2안으로 할게요", s)
    assert "사진 강조형" in c["reply"]
    assert store.read_session(s)["prd"]["design_choice"] == "v2"


def test_publish_chosen_design(client):
    """고른 시안 공개(⑧·⑱): 고르기 전엔 안내, 빈 자리가 있으면 확인, '그대로 공개'면 /site/<id>/에 고른 안."""
    s = _fresh_session(client)
    _to_quoted(client, s)
    _chat(client, "진행", s)
    assert "골라 주세요" in _chat(client, "공개", s)["reply"]
    _chat(client, "3안으로 할게요", s)
    r = _chat(client, "공개", s)
    assert "비어 있는 곳" in r["reply"]  # 시안 먼저로 건너뛴 카드라 가게 이름 등이 자리 표시
    r = _chat(client, "그대로 공개", s)
    sess = store.read_session(s)
    assert "사이트를 열었어요" in r["reply"] and sess["deploy_url"].endswith(f"/site/{sess['requirement_id']}/")
    page = client.get(f"/site/{sess['requirement_id']}/")
    assert page.status_code == 200 and "allow-forms" in page.headers["content-security-policy"]
    assert sess["prd"]["published"] == "v3"


def test_edit_after_publish_does_not_reset(client, monkeypatch):
    """완료·공개 뒤 아무 말에 프로젝트가 지워지던 문제: 가게 정보는 고치고 사이트에 바로 반영, 새로 시작은 명시할 때만."""
    from app import llm
    import json as _json

    s = _fresh_session(client)
    _to_quoted(client, s)
    _chat(client, "진행", s)
    _chat(client, "1안으로 할게요", s)
    _chat(client, "그대로 공개", s)
    real = llm.chat_json

    def fake(system, user, **kw):
        if "010-9999-8888" in user:
            return _json.dumps({"updates": [{"slot": "phone", "value": "010-9999-8888"}]})
        return real(system, user, **kw)

    monkeypatch.setattr(llm, "chat_json", fake)
    r = _chat(client, "전화번호는 010-9999-8888이에요", s)
    assert "반영했어요" in r["reply"]
    sess = store.read_session(s)
    assert sess["prd"] and sess["prd"]["slots"]["phone"]["value"] == "010-9999-8888"
    page = client.get(f"/site/{sess['requirement_id']}/").text
    assert "010-9999-8888" in page or "01099998888" in page
    r = _chat(client, "고마워요", s)
    assert store.read_session(s)["prd"] is not None  # 지워지지 않는다
    r = _chat(client, "새 프로젝트 할래요", s)
    assert r["state"] == "GATHERING" and store.read_session(s).get("prd") is None


def test_intent_variants():
    """S-1: 짧은 대답 변형도 알아듣고, 부정이 섞이면 승인으로 보지 않는다."""
    from app.services.chat_flow import intent
    for t in ("승인", "승인할게요", "승인합니다!", "좋아요", "네", "ok"):
        assert intent(t, "approve"), t
    for t in ("거절", "거절할게요", "반대요", "아니요"):
        assert intent(t, "reject"), t
    for t in ("진행", "진행해 주세요", "만들어주세요", "네"):
        assert intent(t, "proceed"), t
    for t in ("승인 안 할래요", "진행 말고요", "네일 가게예요", "승인 조건이 뭐예요 자세히 알려주세요"):
        assert not intent(t, "approve") and not intent(t, "proceed"), t


def test_correction_after_summary(client, monkeypatch):
    """T3 G1: 요약 뒤 '○○는 △△예요, 고쳐 주세요'를 반영하고 요약을 다시 보인다."""
    from app import llm
    import json as _json
    s = _fresh_session(client)
    _to_approval(client, s)
    real = llm.chat_json

    def fake(system, user, **kw):
        if "고쳐 주세요" in user:
            return _json.dumps({"updates": [{"slot": "offerings", "value": "초등 영어반"}]}, ensure_ascii=False)
        return real(system, user, **kw)

    monkeypatch.setattr(llm, "chat_json", fake)
    r = _chat(client, "반 구성은 초등 영어반이에요. 고쳐 주세요.", s)
    assert r["state"] == "AWAIT_APPROVAL" and r["reply"].startswith("고쳤어요")
    assert store.read_session(s)["prd"]["slots"]["offerings"]["value"] == ["초등 영어반"]
    r = _chat(client, "음...", s)
    assert "승인 또는 거절" in r["reply"]


def test_approval_waits_until_review_gate_is_closed(client, monkeypatch):
    """대표 지적(9/26): 승인 뒤에 '다시 읽어 보니 빠진 게 있다'가 나오던 흐름.
    검토가 넣은 기능의 확인 질문을 먼저 묻고, 닫힌 뒤에야 승인 단계(투표 막대)로 간다."""
    import json

    from app import llm

    base = llm.chat_json

    def chat_json(system, user, **kw):
        if system.startswith("너는 웹사이트 요구사항 검토자다"):
            return json.dumps({"missing": [{"slot": "features", "value": "카카오톡으로 문의 받기",
                                            "quote": "문의가 카톡으로 오게"}], "conflicts": []}, ensure_ascii=False)
        return base(system, user, **kw)

    monkeypatch.setattr(llm, "chat_json", chat_json)
    s = _fresh_session(client)
    _chat(client, "카페 홈페이지요, 문의가 카톡으로 오게 해 주세요", s)
    d = _chat(client, SKIP, s)
    assert d["state"] == "GATHERING"  # 승인 버튼이 아직 나오지 않는다
    assert "빠진 게 있어 넣었어요" in d["reply"] and "승인 전에 확인할 게 남았어요" in d["reply"]
    pending = store.read_session(s)["prd"]["pending"]
    d2 = _chat(client, pending["options"][0], s)
    assert d2["state"] == "AWAIT_APPROVAL" and "승인/거절" in d2["reply"]
    assert "빠진 게" not in _chat(client, "승인", s)["reply"]
