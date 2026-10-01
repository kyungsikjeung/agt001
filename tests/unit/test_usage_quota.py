"""무료 사용 한도 장부 (USAGE_QUOTA_CONTRACT §4). 바깥 호출 없음."""
import datetime

import pytest
from sqlalchemy import func, select

from app import store
from app.db.models import FunnelEventRow, UsageLedgerRow
from app.db.session import get_sessionmaker
from app.services import builder_agent as B
from app.services import chat_flow, usage

UTC = datetime.timezone.utc


@pytest.fixture(autouse=True)
def _clean_ledger(client):
    with get_sessionmaker()() as db, db.begin():
        db.query(UsageLedgerRow).delete()


def _start(client):
    from app.api import inquiries as inquiries_api
    with inquiries_api._lock:
        inquiries_api._hits.clear()
    r = client.post("/api/start", json={"template": "cafe"})
    assert r.status_code == 200, r.text
    return r.json()


def _site(room_id):
    return store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]


def _grants(site, action):
    with get_sessionmaker()() as db:
        return db.scalar(select(func.count()).select_from(UsageLedgerRow).where(
            UsageLedgerRow.site_key == site, UsageLedgerRow.action == action, UsageLedgerRow.kind == "grant"))


def test_defaults_use_and_kst_month_rollover():
    site = "quota-site-1"
    assert usage.left(site) | {} == {"design": {"left": 3, "total": 3}, "restyle": {"left": 20, "total": 20},
                                     "resets": usage.resets_label()}
    for _ in range(3):
        info = usage.use(site, "restyle")
    assert info == {"left": 17, "total": 20, "over": False} and _grants(site, "restyle") == 1
    # UTC 10/31 15:30 = KST 11/1 00:30 → 새 달은 다시 가득, 10월 기록은 그대로
    nov = datetime.datetime(2026, 10, 31, 15, 30, tzinfo=UTC)
    oct_ = datetime.datetime(2026, 10, 31, 14, 30, tzinfo=UTC)
    assert usage.month_of(nov) == "2026-11" and usage.month_of(oct_) == "2026-10"
    assert usage.resets_label(nov) == "12월 1일"
    usage.use(site, "design", now=nov)
    assert usage.left(site, now=nov)["design"]["left"] == 2
    assert usage.left(site, now=oct_)["design"]["left"] == 3


def test_over_limit_is_not_blocked_but_signals():
    site = "quota-site-2"
    infos = [usage.use(site, "design") for _ in range(4)]
    assert [i["left"] for i in infos] == [2, 1, 0, 0] and infos[-1]["over"] is True
    assert "다 썼어요" in usage.note(infos[-1], "design")
    assert usage.note(infos[1], "design") == "이번 달 무료 시안 만들기 1번 남았어요."
    assert usage.note({"left": 5, "total": 20, "over": False}, "restyle") == ""
    with get_sessionmaker()() as db:
        props = db.scalars(select(FunnelEventRow.props).where(FunnelEventRow.event == "quota_exceeded")).all()
    assert {"site": site, "kind": "design", "over": 1} in props


def test_alert_text_for_operator():
    from app.services import ops_alert
    text = ops_alert._EVENTS["quota_exceeded"]({"site": "k1", "kind": "restyle", "over": 2})
    assert text == "[한도] 가게 k1 · 디자인 고치기 무료 횟수 넘김 2회 (지불 의사 신호)"


def test_template_start_and_direct_edit_are_not_counted_card_shows_quota(client):
    body = _start(client)
    rid, h = body["room_id"], {"X-Member-Id": body["member_id"]}
    client.put(f"/api/rooms/{rid}/card", json={"fields": {"shop_name": "모퉁이 커피"}}, headers=h)
    card = client.get(f"/api/rooms/{rid}/card", headers=h).json()
    assert card["quota"]["design"] == {"left": 3, "total": 3} and card["quota"]["restyle"]["left"] == 20


def test_builder_style_counts_and_unknown_style_does_not(client, monkeypatch):
    from app import llm
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM 안 부름")))
    body = _start(client)
    rid = body["room_id"]
    with store.room_tx(rid) as (room, session):
        B.say(room, session, rid, "더 밝게")
    assert usage.left(_site(rid))["restyle"]["left"] == 19


def test_chat_restyle_counts_only_when_changed(client):
    body = _start(client)
    rid = body["room_id"]
    site = _site(rid)
    with store.room_tx(rid) as (room, session):
        session.setdefault("design_url", f"/design/{site}")
        assert "어떤 느낌으로" in chat_flow._restyle(session, "음")  # 못 알아들음 → 안 셈
        assert usage.left(site)["restyle"]["left"] == 20
        chat_flow._restyle(session, "더 밝게")
    assert usage.left(site)["restyle"]["left"] == 19
