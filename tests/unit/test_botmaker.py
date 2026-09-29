"""봇메이커 인터뷰 (BOTMAKER_PLAN, BOOKING_BOT_IMPL_PLAN BM-1~BM-8)."""
import datetime

import pytest

from app import llm
from app.services import booking_spec as S
from app.services import botmaker as B
from app.services.slots import KST


def _talk(spec, *answers):
    reply = None
    for a in answers:
        if isinstance(a, dict):
            spec, reply = B.turn(spec, **a)
        else:
            spec, reply = B.turn(spec, text=a)
        assert reply.get("understood", True), (a, reply["reply"])
    return spec, reply


def _start(mode):
    spec = B.seed({}, mode=mode)
    return B.turn(spec)  # 첫 질문


# ── 파서 ──

def test_parse_minutes():
    assert B.parse_minutes("두 시간 반") == 150
    assert B.parse_minutes("2시간 30분") == 150
    assert B.parse_minutes("90분") == 90
    assert B.parse_minutes("한시간") == 60
    assert B.parse_minutes("150") == 150
    assert B.parse_minutes("잘 몰라요") is None


def test_parse_week_variants():
    assert B.parse_week("화~일 10시~8시, 월요일 휴무") == {d: [["10:00", "20:00"]] for d in S.DAYS[1:]}
    w = B.parse_week("평일 10시~20시, 토요일 10시~15시")
    assert w["mon"] == [["10:00", "20:00"]] and w["sat"] == [["10:00", "15:00"]] and "sun" not in w
    w = B.parse_week("매일 11시~15시, 17시~21시")
    assert w["sun"] == [["11:00", "15:00"], ["17:00", "21:00"]]
    assert B.parse_week("오후 세시부터 밤 열한시") == {d: [["15:00", "23:00"]] for d in S.DAYS}
    assert B.parse_week("모르겠어요") is None


def test_parse_days_names_ranges():
    assert B.parse_days("화요일이요") == ["tue"]
    assert B.parse_days("월, 수 쉬어요") == ["mon", "wed"]
    assert B.parse_days("없어요") == []
    assert B.parse_names("원장 김단정, 실장 박하나") == ["원장 김단정", "실장 박하나"]
    assert B.parse_names("컷 펌 염색") == ["컷", "펌", "염색"]
    assert B.parse_names("저 혼자 해요") == ["사장님"]
    assert B.parse_ranges("3시~5시") == [["15:00", "17:00"]]
    assert B.parse_ranges("오후 3시~5시") == [["15:00", "17:00"]]
    assert B.parse_ranges("11시~2시") == [["11:00", "14:00"]]
    assert B.parse_ranges("오전 9시 반~6시") == [["09:30", "18:00"]]


# ── 인터뷰 ──

def test_salon_interview_by_talking_until_ready():
    spec, first = _start("slot")
    assert "영업하는 요일" in first["reply"] and first["buttons"][-1]["action"] == "later"
    spec, reply = _talk(
        spec,
        "화~일 10시~8시, 월요일 휴무",
        "30분",
        "컷, 펌, 염색",
        "한 시간",
        "두 시간 반",
        "2시간",
        "원장, 실장",
        "2시간 전",
        "제가 확인할게요",
        # 파고들기
        "15분",
        "실장은 펌 3시간",
        "염색은 원장만",
        "없어요",          # 원장 따로 쉬는 날
        "화요일",          # 실장 휴무
        "따로 없어요",      # 마지막 예약
        "없어요",          # 브레이크
        "3시간 전",
    )
    assert reply["ready"] is True, reply["reply"]
    assert [b["action"] for b in reply["buttons"]] == ["activate", "fix"]
    assert "봇은 이렇게 답해요" in reply["reply"]
    clean = B._clean(spec)
    assert S.validate(clean) == []
    perm = S.service(clean, "펌")
    assert perm["duration_min"] == 150 and perm["staff_minutes"] == {"실장": 180} and perm["buffer_min"] == 15
    assert S.service(clean, "염색")["staff"] == ["원장"]
    assert next(r for r in clean["resources"] if r["name"] == "실장")["days_off"] == ["tue"]
    assert clean["policy"]["lead_min"] == 120 and clean["policy"]["auto_confirm"] is False
    assert clean["provenance"]["services[펌].duration_min"] == "filled"
    assert reply["progress"]["done"] == reply["progress"]["total"]


def test_table_interview_with_buttons_and_exits():
    spec, first = _start("table")
    spec, reply = _talk(
        spec,
        "매일 11시~22시",
        {"action": "pick:0"},     # 30분
        "2명 1시간, 4명 1시간 반, 6명 2시간",
        {"action": "default"},    # 팀 수 추천대로
        {"action": "let_ai"},     # 인원 한도 알아서
        "8명",
        {"action": "pick:2"},     # 전날까지
        {"action": "pick:0"},     # 바로 확정
        "3시~5시",                # 브레이크 (오후로 보지 않는 모호한 값)
    )
    clean = B._clean(spec)
    assert clean["weekly_hours"]["mon"] == [["11:00", "15:00"], ["17:00", "22:00"]]
    assert clean["meal_minutes"] == {"1-2": 60, "3-4": 90, "5-6": 120, "7+": 120}
    assert clean["pace"] == {"teams": 3, "people": 12}
    assert clean["provenance"]["pace.teams"] == "default" and clean["provenance"]["pace.people"] == "assumed"
    assert clean["policy"]["auto_confirm"] is True and clean["policy"]["lead_min"] == 1440
    spec, reply = _talk(spec, "하루 전")
    assert reply["ready"] is True, reply["reply"]


def test_break_splits_hours():
    spec = {"mode": "table", "weekly_hours": {"mon": [["11:00", "22:00"]]}}
    B.set_path(spec, "breaks", [["15:00", "17:00"]])
    assert spec["weekly_hours"]["mon"] == [["11:00", "15:00"], ["17:00", "22:00"]]


def test_contradiction_is_asked_back():
    spec, _ = _start("slot")
    spec, reply = _talk(spec, "매일 10시~12시", "30분", "펌", "두 시간 반")
    # 펌 150분 > 2시간 영업 구간 → 다시 묻는다
    assert "펌 150분이 들어갈" in reply["reply"]
    spec, reply = _talk(spec, "한 시간 반")
    assert "선생님" in reply["reply"]


def test_later_then_asked_again_then_assumed():
    spec, _ = _start("slot")
    spec, reply = B.turn(spec, action="later")         # 영업시간 미룸
    assert "간격" in reply["reply"]
    spec, reply = _talk(spec, "30분", "컷", "1시간", "혼자", "1시간 전", "바로 확정")
    # 파고들기 뒤에 미룬 영업시간을 다시 묻는다
    for _ in range(6):
        if "영업하는 요일" in reply["reply"]:
            break
        spec, reply = B.turn(spec, action="default")
    assert "영업하는 요일" in reply["reply"]
    spec, reply = _talk(spec, "매일 10시~7시")
    assert B._clean(spec)["weekly_hours"]["mon"] == [["10:00", "19:00"]]


def test_not_understood_keeps_question():
    spec, _ = _start("slot")
    spec, reply = B.turn(spec, text="음 글쎄요")
    assert reply["understood"] is False and "영업하는 요일" in reply["reply"]


def test_llm_fallback_must_be_grounded(monkeypatch):
    spec, _ = _talk(_start("slot")[0], "매일 10시~8시", "30분", "펌")
    monkeypatch.setattr(llm, "chat_json", lambda system, user, **kw: '{"value": 150}')
    spec2, reply = B.turn(spec, text="꽤 오래 걸려요")        # 150이 말에 없음 → 버림
    assert reply["understood"] is False
    spec3, reply = B.turn(spec, text="백오십분쯤이요")          # 말에 150 있음(한자어 수)
    assert B.get_path(B._clean(spec3), "services[펌].duration_min") == 150


def test_seed_from_card_is_confirmed_not_trusted():
    card = {"slots": {"hours": {"status": "filled", "value": "화~일 오전 10시~오후 8시, 월요일 휴무"}}}
    spec = B.seed(card, mode="slot")
    assert spec["weekly_hours"]["tue"] == [["10:00", "20:00"]] and spec["provenance"]["weekly_hours"] == "card"
    spec, reply = B.turn(spec)
    assert "제가 이렇게 알고 있어요" in reply["reply"] and reply["buttons"][0]["action"] == "keep"
    spec, reply = B.turn(spec, action="keep")
    assert spec["provenance"]["weekly_hours"] == "filled" and "간격" in reply["reply"]


def test_fix_and_redo():
    spec, _ = _talk(_start("slot")[0], "매일 10시~8시")
    spec, reply = B.turn(spec, action="fix")
    assert any(b["action"] == "redo:week" for b in reply["buttons"])
    spec, reply = B.turn(spec, action="redo:week")
    assert "영업하는 요일" in reply["reply"]


def test_resource_keys_never_reused():
    spec = {"mode": "slot"}
    B.set_path(spec, "resources", ["원장"])
    B.set_path(spec, "resources", ["실장", "원장"])
    keys = {r["name"]: r["key"] for r in spec["resources"]}
    assert keys == {"원장": "r1", "실장": "r2"}


def test_simulate_flags_impossible_spec():
    spec = {"mode": "slot", "step_min": 30, "weekly_hours": {"mon": [["10:00", "11:00"]]},
            "services": [{"name": "펌", "duration_min": 150}], "resources": [{"key": "r1", "kind": "staff", "name": "원장"}]}
    res = B.simulate(spec, now=datetime.datetime(2026, 9, 29, 9, 0, tzinfo=KST))
    assert res[0]["ok"] is False


# ── 켜기 (DB) ──

def test_activate_through_engine(client):
    from app import store
    from app.db.session import get_sessionmaker
    from app.services import booking_engine, shops
    room_id = client.post("/room").json()["room_id"]
    client.post(f"/room/{room_id}/chat", json={"member_id": "owner", "nickname": "사장님", "message": ""})
    key = store.read_session(store.read_room(room_id)["session_id"])["requirement_id"]
    with get_sessionmaker()() as db, db.begin():
        shop_id = shops.ensure_in(db, key)
    spec, _ = _talk(_start("slot")[0], "매일 10시~8시", "30분", "컷", "1시간", "혼자", "1시간 전", "바로 확정")
    booking_engine.save_draft(shop_id, spec, None)
    with pytest.raises(booking_engine.EngineError):
        booking_engine.save_draft(shop_id, {**spec, "services": []}, None)
        B.activate(shop_id, None)
    booking_engine.save_draft(shop_id, spec, None)
    assert B.activate(shop_id, None)["version"] == 1
    active = booking_engine.get_spec(shop_id)["spec"]
    assert "_interview" not in active and active["services"][0]["name"] == "컷"


def test_no_default_questions_only_allow_later():
    spec, first = _start("slot")
    assert [b["action"] for b in first["buttons"]] == ["later"]
    spec, reply = B.turn(spec, action="let_ai")
    assert "제가 정할 수 없어요" in reply["reply"] and "weekly_hours" not in spec["provenance"]
