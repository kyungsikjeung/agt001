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
    # 포함량은 요금제에서 읽는다 (D61, plans.py). 구독이 없으면 무료 요금제
    assert usage.left(site) | {} == {"design": {"left": 3, "total": 3, "unlimited": False},
                                     "restyle": {"left": 20, "total": 20, "unlimited": False},
                                     "chat_ai": {"left": 300, "total": 300, "unlimited": False},
                                     "resets": usage.resets_label()}
    for _ in range(3):
        info = usage.use(site, "restyle")
    assert info == {"left": 17, "total": 20, "over": False, "unlimited": False}
    assert _grants(site, "restyle") == 1
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
    assert card["quota"]["design"] == {"left": 3, "total": 3, "unlimited": False}
    assert card["quota"]["restyle"]["left"] == 20


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


def test_guest_chat_ai_answer_counts(client):
    """손님 채팅 AI 답은 요금제 포함량에서 깎는다. 사장님 대기 중 글은 AI를 안 거치니 안 센다 (D61)."""
    from app import store
    from app.api import chat_agent as chat_api
    from app.services import usage

    from app.services import shops

    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    shops.ensure(key, "모퉁이 커피", room_id)  # 공개된 가게여야 손님 채팅이 열린다
    token = None

    def say(**body):
        """손님 한 명으로 계속 말한다(채팅 쿠키는 Secure라 직접 들고 보낸다 — test_guest_chat와 같은 방식)."""
        nonlocal token
        headers = {"Origin": "http://testserver"}
        if token:
            headers["Cookie"] = f"{chat_api.cookie_name(key)}={token}"
        r = client.post(f"/api/chat/{key}", json=body, headers=headers)
        assert r.status_code == 200, r.text
        token = r.cookies.get(chat_api.cookie_name(key)) or token
        return r.json()

    assert usage.left(key)["chat_ai"] == {"left": 300, "total": 300, "unlimited": False}
    assert say(action="ask")["reply"]  # 봇이 답한다
    assert usage.left(key)["chat_ai"]["left"] == 299

    # 봇이 모르면 사장님께 넘긴다(mode=owner) — 그건 AI 답이 아니라 전달이라 세지 않는다
    before = usage.left(key)["chat_ai"]["left"]
    assert say(text="주차 돼요?")["mode"] == "owner"
    say(text="주말에 10명 가도 돼요?")
    assert usage.left(key)["chat_ai"]["left"] == before, "사장님께 넘긴 글이 AI 답으로 세졌어요"


def test_plans_table():
    """요금제 표 한 곳 (D61). 무료에도 스탬프·회원·예약이 켜져 있고, 주문·결제는 유료부터."""
    from app.services import plans

    assert plans.of("없는-가게") == "free" and plans.get(None)["won"] == 0
    assert [plans.get(p)["won"] for p in ("free", "shop", "pro")] == [0, 9900, 24900]
    # 원가 0인 기능은 무료에도 (D61 ①)
    for f in ("stamp", "member", "booking", "chat", "push"):
        assert plans.has(f, "free"), f
    # 원가가 드는 것은 유료부터·포함량으로
    assert not plans.has("order", "free") and plans.has("order", "shop")
    assert plans.quota("chat_ai", "free") == 300 and plans.quota("chat_ai", "pro") == 3000
    assert plans.quota("restyle", "shop") is None  # 무제한
    assert plans.quota("alimtalk", "free") == 0
    assert plans.overage_won("alimtalk", "free") == 15 and plans.overage_won("alimtalk", "pro") == 12
    assert plans.SETUP_WON == 99000 and plans.GUEST_PAY_FEE_RATE == 0.0


def test_paid_plan_quota_and_unlimited(client):
    """유료 요금제면 포함량이 요금제 값이고, 무제한은 남은 횟수를 말하지 않는다."""
    from app import store
    from app.db.models import SubscriptionRow
    from app.db.session import get_sessionmaker
    from app.services import plans, shops, usage

    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    shops.ensure(key, "모퉁이 커피", room_id)
    with get_sessionmaker()() as db, db.begin():
        db.add(SubscriptionRow(site_key=key, plan="pro", status="active"))

    assert plans.of(key) == "pro"
    assert usage.left(key)["chat_ai"]["total"] == 3000
    info = usage.use(key, "restyle")
    assert info["unlimited"] and usage.note(info, "restyle") == ""  # 무제한은 안내를 붙이지 않는다
