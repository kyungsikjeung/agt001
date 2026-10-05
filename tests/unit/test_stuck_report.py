"""막힘 지표 (UX_GAP_PLAN Q4). 가짜 대화 턴·유입 기록으로 지표마다 숫자를 맞춘다. DB 사용, 바깥 호출 없음."""
import datetime
import json
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app import store
from app.config import settings
from app.db.models import AdminAuditRow, ChatTurnRow, FunnelEventRow, UserRow
from app.db.session import get_sessionmaker
from app.main import seconds_until_next
from app.services import auth as auth_svc
from app.services import stuck_report as R

UTC = datetime.timezone.utc
KST = ZoneInfo("Asia/Seoul")
NOW = datetime.datetime(2026, 10, 5, 0, 0, tzinfo=UTC)
PHONE, ADDR = "010-1234-5678", "서울시 마포구 연남로 12"


@pytest.fixture
def db():
    store.reset_all()


def _turns(sid, hours_ago, rows, before="GATHERING"):
    """rows: (사장님 말, state_after, meta). 첫 턴이 hours_ago 시간 전, 그 뒤 1분씩."""
    start = NOW - datetime.timedelta(hours=hours_ago)
    with get_sessionmaker()() as s, s.begin():
        for i, (text, state, meta) in enumerate(rows):
            s.add(ChatTurnRow(session_id=sid, ts=start + datetime.timedelta(minutes=i), user_text=text,
                              ai_text="네", state_before=before, state_after=state, meta=meta))


def _q(asked_slot, next_slot, asked, kind="single", **extra):
    return {"asked_slot": asked_slot, "asked_kind": kind if asked_slot else None, "next_slot": next_slot,
            "next_kind": kind if next_slot else None, "asked": asked, **extra}


def _events(rows):
    with get_sessionmaker()() as s, s.begin():
        for event, site, hours_ago in rows:
            s.add(FunnelEventRow(event=event, ts=NOW - datetime.timedelta(hours=hours_ago), props={"site": site}))


@pytest.fixture
def seeded(db):
    G, A = "GATHERING", "AWAIT_APPROVAL"
    # 같은 칸을 되풀이하다 이틀째 조용함(이탈). '다시요'·'직접 입력' 글·멤버 말은 사이에 껴도 무시한다.
    # 세는 답(영업시간)에 전화·주소.
    _turns("s_rep", 48, [
        ("카페예요", G, _q(None, "hours", 1)),
        (f"음 {PHONE} {ADDR}", G, _q("hours", "hours", 1)),
        ("다시요", G, _q("hours", "hours", 1, repeat=True)),
        ("직접 입력", G, _q("hours", "hours", 1)),
        ("모르겠어요", G, _q("hours", "hours", 1, member=True)),
        ("글쎄요", G, _q("hours", "hours", 1)),
    ])
    # 같은 칸이라도 덧붙임 질문(종류가 다름)은 되풀이가 아니다
    _turns("s_follow", 3, [
        ("매일 같은 시간", G, {**_q("hours", "hours", 1), "next_kind": "followup"}),
        ("9시부터", G, _q("hours", "hours", 2, kind="followup")),
    ])
    # 창 밖 턴(20일 전)은 칸별 숫자에서 빠진다. 대화는 어제 턴이 있어 센다.
    _turns("s_long", 480, [("알아서", G, _q("hours", "goal", 1))])
    _turns("s_long", 26, [("예약", G, _q("goal", "target", 2))])
    # 빌더 방(처음부터 DONE)은 요약 전 이탈이 아니다
    _turns("s_builder", 48, [("색 바꿔줘", "DONE", None)], before="DONE")
    # 요약까지 2턴: 영업시간을 '알아서'로 넘김
    _turns("s_sum2", 30, [
        ("알아서 해주세요", G, _q("hours", "shop_name", 2, skip=True)),
        ("모퉁이", A, _q("shop_name", None, 2)),
    ])
    # 요약까지 4턴
    _turns("s_sum4", 20, [
        ("알아서", G, _q("hours", "goal", 1)),
        ("예약", G, _q("goal", "target", 2)),
        ("직장인", G, _q("target", None, 2)),
        ("승인", A, None),
    ])
    # 금지 요청 턴은 건너뛴다 → 되풀이 한 번뿐. 마지막 턴이 2시간 전이라 이탈도 아니다.
    _turns("s_blocked", 2, [
        ("x", G, _q("goal", "goal", 3, kind="multi")),
        ("y", G, _q("goal", "goal", 3, kind="multi", blocked=True)),
        ("z", G, _q("goal", "target", 4, kind="multi")),
    ])
    # 창 밖(10일 전)은 세지 않는다
    _turns("s_old", 240, [("알아서", G, _q("hours", "hours", 5))])
    _events([
        ("publish_need_login", "site_a", 5), ("publish_need_login", "site_a", 4),  # 고리
        ("publish_need_login", "site_b", 5), ("publish_need_login", "site_b", 4), ("site_published", "site_b", 3),
        ("publish_need_login", "site_c", 5),  # 한 번뿐
        ("site_published", "site_d", 6), ("publish_need_login", "site_d", 5), ("publish_need_login", "site_d", 4),  # 고리
        ("publish_need_login", "site_old", 300), ("publish_need_login", "site_old", 299),  # 창 밖
    ])


def test_each_metric(seeded):
    rep = R.report(7, now=NOW)
    assert rep["days"] == 7 and rep["sessions"] == 6 and rep["reached_summary"] == 2
    assert rep["repeat_twice"] == {"sessions": 1, "top": [{"slot": "hours", "label": "영업시간", "sessions": 1}]}
    # 영업시간 5번 물음: 음 / 글쎄요(모름) / 알아서 해주세요 / 알아서 / 매일 같은 시간. '다시요'·'직접 입력'·멤버 말·창 밖 턴은 빠진다.
    # 덧붙임 질문(followup)은 single이 아니라 세지 않는다. 3번 미만 칸은 없다.
    assert rep["let_ai_by_slot"] == [{"slot": "hours", "label": "영업시간", "asked": 5, "let_ai": 3, "rate": 0.6}]
    assert rep["dropoff"] == {1: 1, 2: 1}  # s_rep, s_long (빌더 방은 없음)
    assert rep["publish_login_loops"] == 2
    assert rep["turns_to_summary"] == {"p50": 3.0, "p90": 3.8}


def test_pii_absent_and_morning_text(seeded):
    rep = R.report(7, now=NOW)
    text = R.morning_text(rep)
    for out in (json.dumps(rep, ensure_ascii=False), text):
        assert PHONE not in out and "연남로" not in out and "마포구" not in out and "카페예요" not in out
    assert text.startswith("[아침 보고] 지난 7일") and len(text) <= 700
    assert "영업시간" in text and "60%(3/5)" in text and "로그인에 막혀 공개 못 한 가게: 2곳" in text
    assert "질문 1개에서 1건, 질문 2개에서 1건" in text


def test_morning_text_skips_zero_parts(db):
    assert R.morning_text(R.report(7, now=NOW)) == "[아침 보고] 지난 7일\n대화가 없었어요."
    _turns("s", 1, [("가게 이름은 모퉁이", "GATHERING", _q(None, "hours", 1))])
    text = R.morning_text(R.report(7, now=NOW))
    assert text == "[아침 보고] 지난 7일\n대화 1건"


def test_morning_text_long_dropoff_keeps_login_line():
    rep = {"days": 7, "sessions": 300, "reached_summary": 0, "turns_to_summary": {"p50": None, "p90": None},
           "repeat_twice": {"sessions": 0, "top": []}, "let_ai_by_slot": [],
           "dropoff": {q: q + 1 for q in range(60)}, "publish_login_loops": 4}
    text = R.morning_text(rep)
    assert "로그인에 막혀 공개 못 한 가게: 4곳" in text and "질문 59개에서 60건" in text and text.endswith(" …")
    assert "질문 0개" not in text and len(text) <= R.MORNING_MAX


def test_chat_publish_records_need_login(client, monkeypatch):
    from test_publish_login import OWNER, _drive_to_pickable, _post
    monkeypatch.setattr(settings, "publish_login_required", True)
    room_id = _drive_to_pickable(client)
    _post(client, room_id, OWNER, "그대로 공개")
    _post(client, room_id, OWNER, "그대로 공개")
    with get_sessionmaker()() as s:
        props = s.scalars(select(FunnelEventRow.props).where(FunnelEventRow.event == "publish_need_login")).all()
    site = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    assert props == [{"site": site, "ref": room_id}] * 2
    assert R.report(7)["publish_login_loops"] == 1


@pytest.mark.parametrize("now, expected", [
    (datetime.datetime(2026, 10, 5, 8, 0, tzinfo=KST), 3600),
    (datetime.datetime(2026, 10, 5, 9, 0, tzinfo=KST), 24 * 3600),  # 딱 9시면 내일
    (datetime.datetime(2026, 10, 5, 9, 0, 1, tzinfo=KST), 24 * 3600 - 1),
    (datetime.datetime(2026, 10, 5, 23, 30, tzinfo=KST), 9.5 * 3600),
    # UTC로는 아직 4일이지만 한국은 5일 0시 30분 → 같은 날 9시
    (datetime.datetime(2026, 10, 4, 15, 30, tzinfo=UTC), 8.5 * 3600),
    # 미국·유럽 서머타임 바뀌는 날에도 한국 시각은 그대로
    (datetime.datetime(2026, 3, 8, 8, 0, tzinfo=KST), 3600),
    (datetime.datetime(2026, 3, 29, 8, 0, tzinfo=KST), 3600),
    (datetime.datetime(2026, 11, 1, 8, 0, tzinfo=KST), 3600),
])
def test_seconds_until_next(now, expected):
    assert seconds_until_next(9, now) == expected


def test_admin_stuck_auth_and_view(client, monkeypatch):
    with get_sessionmaker()() as s, s.begin():
        s.add_all([UserRow(id="u_admin_s", nickname="관리자"), UserRow(id="u_owner_s", nickname="사장님")])
    monkeypatch.setattr(settings, "admin_user_ids", "u_admin_s")
    assert client.get("/api/admin/stuck").status_code == 401
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session("u_owner_s"))
    assert client.get("/api/admin/stuck").status_code == 404
    client.cookies.set(auth_svc.SESSION_COOKIE, auth_svc.create_session("u_admin_s"))
    r = client.get("/api/admin/stuck", params={"days": 7})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert {"sessions", "reached_summary", "repeat_twice", "let_ai_by_slot", "dropoff", "publish_login_loops",
            "turns_to_summary"} <= set(r.json())
    with get_sessionmaker()() as s:
        assert s.scalar(select(AdminAuditRow.action).where(AdminAuditRow.user_id == "u_admin_s")) == "view:stuck"


def test_morning_loop_survives_send_error(monkeypatch):
    import asyncio
    from app import main
    calls = []

    def send():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("텔레그램 안 됨")

    monkeypatch.setattr(main, "seconds_until_next", lambda hour: -1)  # 기다리지 않고 바로
    monkeypatch.setattr(main, "_send_morning", send)

    async def run():
        task = asyncio.create_task(main._morning_report())
        for _ in range(200):
            await asyncio.sleep(0.01)
            if len(calls) >= 2:
                break
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    assert len(calls) >= 2
