"""디자인 학습 기록 (DECISIONS.md D44·D45): 시안 → 고르기 → 말로 고치기 → 공개 → 문의, 못 담은 요구, 개인정보 없음."""
import pytest
from sqlalchemy import select

from app import store
from app.api import inquiries as inquiries_api
from app.db.models import FunnelEventRow
from app.db.session import get_sessionmaker
from app.services import design_log, funnel
from app.services import prd_engine as E
from app.services import prd_schema as S


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    inquiries_api._hits.clear()


def _events(name=None):
    with get_sessionmaker()() as db:
        q = select(FunnelEventRow).order_by(FunnelEventRow.id)
        if name:
            q = q.where(FunnelEventRow.event == name)
        return db.scalars(q).all()


def _chat(client, message, session_id):
    r = client.post("/chat", json={"session_id": session_id, "message": message})
    assert r.status_code == 200
    return r.json()


def test_props_keep_only_allowed_keys_and_no_digits_in_label(client):
    funnel.record("unmet_need", props={"site": "abc<1>", "label": "바비큐장 010-1234-5678", "phone": "010-1234-5678",
                                       "kind": "section", "count": 3})
    [e] = _events()
    assert e.props == {"site": "abc1", "label": "바비큐장", "kind": "section"}


def test_full_design_flow_is_recorded_and_reported(client):
    s = "sess-dlog"
    for m in ("", "카페 홈페이지 만들어줘", "시안 먼저 볼게요", "승인", "진행"):
        _chat(client, m, s)
    rid = store.read_session(s)["requirement_id"]
    [shown] = _events("design_shown")
    assert shown.props["site"] == rid and shown.props["industry"]  # 테스트용 가짜 LLM은 업종을 못 뽑아 other
    assert {"v1", "v2", "v3"} <= set(shown.props)  # 팔레트:글꼴:첫 화면:다음 부품
    assert shown.props["v1"].count(":") == 3

    _chat(client, "2안으로 할게요", s)
    _chat(client, "더 고급스럽게 해 주세요", s)
    _chat(client, "그대로 공개", s)
    r = client.post(f"/api/inquiries/{rid}", data={"name": "손님", "contact": "010-1234-5678", "message": "문의요",
                                                    "agree": "yes", "website": ""}, follow_redirects=False)
    assert r.status_code == 303

    assert [e.props["variant"] for e in _events("design_chosen")] == ["v2"]
    [restyle] = _events("design_restyled")
    assert restyle.props["palette"] == "charcoal-gold" and "text" not in restyle.props
    assert [e.props["variant"] for e in _events("site_published")] == ["v2"]
    [inq] = _events("inquiry_received")
    assert inq.props == {"site": rid}  # 문의 내용·연락처는 남기지 않는다
    # 어떤 기록에도 연락처·대화 원문이 없다
    assert not any("010" in str(e.props) or "고급스럽게" in str(e.props) for e in _events())

    rep = design_log.report()
    assert rep["sites_shown"] == 1 and rep["choice_rate"] == 1.0 and rep["publish_rate"] == 1.0
    assert rep["chosen_variant"] == {"v2": 1} and rep["inquiries_30d_total"] == 1
    assert rep["published_with_inquiry_rate"] == 1.0
    assert rep["restyle_changes"]["palette=charcoal-gold"] == 1


def _card(sections, features_judged=()):
    card = E.new_card("pension")
    E._put(card, "business_type", "펜션", S.FILLED)
    E._put(card, "sections", list(sections), S.FILLED)
    card["features_judged"] = list(features_judged)
    return card


def test_unmet_items_finds_sections_and_features_parts_cannot_hold():
    card = _card(["객실 소개", "주변 안내", "오시는 길", "바비큐장"],
                 [{"id": "online_payment", "verdict": "out_of_beta", "text": "카드 결제"},
                  {"id": None, "verdict": "unknown", "text": "드론 촬영 예약 7대"},
                  {"id": "kakao_channel_chat", "verdict": "owner_setup", "text": "카톡 채널"}])
    items = design_log.unmet_items(card)
    assert {"kind": "section", "label": "바비큐장", "ref": "none"} in items
    assert {"kind": "feature", "verdict": "out_of_beta", "ref": "online_payment"} in items
    assert {"kind": "feature", "verdict": "unknown", "ref": "none", "label": "드론 촬영 예약 7대"} in items
    assert not any(i.get("label") in ("객실 소개", "주변 안내", "오시는 길") for i in items)
    assert not any(i.get("ref") == "kakao_channel_chat" for i in items)  # 사장님 준비만 하면 되는 기능은 담긴다


def test_unmet_is_checked_once_at_first_design_not_on_redraw(client, monkeypatch):
    calls = []
    monkeypatch.setattr(design_log, "unmet", lambda site, card: calls.append(site))
    s = "sess-unmet"
    for m in ("", "펜션 홈페이지 만들어줘", "시안 먼저 볼게요", "승인", "진행", "더 고급스럽게", "2안으로 할게요"):
        _chat(client, m, s)
    assert calls == [store.read_session(s)["requirement_id"]]  # 말로 고쳐 다시 그려도 다시 세지 않는다


def test_report_unmet_rate_is_share_of_shown_sites(client):
    for site in ("a", "b", "c", "d"):
        funnel.record("design_shown", props={"site": site})
    funnel.record("unmet_need", props={"site": "a", "kind": "section", "label": "바비큐장"})
    funnel.record("unmet_need", props={"site": "a", "kind": "feature", "ref": "online_payment"})
    rep = design_log.report()
    assert rep["unmet_site_rate"] == 0.25  # D44: 10% 넘으면 느린 경로를 켤 조건 하나 충족
    assert rep["unmet_top"] == {"section:바비큐장": 1, "feature:online_payment": 1}


def test_logging_failure_never_breaks_the_flow(client, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(funnel, "record", boom)
    design_log.chosen("site-x", _card(["객실 소개"]), "v1")  # 예외가 밖으로 나오지 않는다
