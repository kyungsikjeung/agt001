"""예약 명세 검증·빈 시간 계산 (BOOKING_BOT_IMPL_PLAN SPEC-2, CAL-1~CAL-6). DB 없음."""
import copy
import datetime

from app.services import booking_spec as S
from app.services import slots
from app.services.slots import KST

# 2026-10-01 = 목요일
THU = datetime.date(2026, 10, 1)
NOW = datetime.datetime(2026, 9, 29, 9, 0, tzinfo=KST)

SALON = {
    "mode": "slot", "step_min": 30,
    "weekly_hours": {d: [["10:00", "20:00"]] for d in ("tue", "wed", "thu", "fri", "sat", "sun")},
    "services": [
        {"name": "컷", "duration_min": 60, "buffer_min": 15},
        {"name": "펌", "duration_min": 150, "buffer_min": 15, "staff_minutes": {"실장": 180}},
        {"name": "염색", "duration_min": 120, "buffer_min": 15, "staff": ["원장"]},
    ],
    "resources": [
        {"key": "r1", "kind": "staff", "name": "원장"},
        {"key": "r2", "kind": "staff", "name": "실장", "hours": {"thu": [["12:00", "20:00"]]}, "days_off": ["fri"]},
    ],
    "policy": {"lead_min": 120, "max_days": 30},
}

DINER = {
    "mode": "table", "step_min": 30,
    "weekly_hours": {"thu": [["11:30", "15:00"], ["17:00", "21:30"]]},
    "meal_minutes": {"1-2": 60, "3-4": 90, "5+": 120},
    "pace": {"teams": 2, "people": 8},
    "policy": {"lead_min": 60, "party_max": 8, "last_start": "20:00"},
}


def _at(day, hhmm):
    h, m = map(int, hhmm.split(":"))
    return datetime.datetime.combine(day, datetime.time(h, m), tzinfo=KST)


def _times(found):
    return [f["time"] for f in found]


def test_valid_specs_have_no_problems():
    assert S.validate(SALON) == []
    assert S.validate(DINER) == []


def test_validate_reports_missing_and_contradictions():
    spec = copy.deepcopy(SALON)
    spec["services"][2]["staff"] = ["없는사람"]
    spec["policy"]["last_start"] = "19:00"
    paths = {p["path"] for p in S.validate(spec)}
    assert "services.염색.staff" in paths
    assert "policy.last_start" in paths  # 19:00 + 펌 150분 > 20:00 마감
    assert {p["path"] for p in S.validate({"mode": "slot"})} >= {"step_min", "weekly_hours", "services", "resources"}
    assert S.validate({"mode": "x"})[0]["path"] == "mode"
    short = copy.deepcopy(SALON)
    short["weekly_hours"] = {"thu": [["10:00", "12:00"]]}
    assert any("펌" in p["msg"] and "구간" in p["msg"] for p in S.validate(short))


def test_perm_blocks_its_whole_duration():
    busy = [{"resource_key": "r1", "start": _at(THU, "14:00"), "end": _at(THU, "16:45")}]
    found = slots.find(SALON, THU, service="컷", staff="원장", busy=busy, now=NOW)
    times = _times(found)
    assert "12:30" in times and "13:00" not in times   # 13:00 컷 + 정리 15분 = 14:15 > 14:00 펌
    assert "13:30" not in times and "14:30" not in times and "16:30" not in times
    assert "16:45" not in times and "17:00" in times


def test_cut_before_busy_respects_buffer():
    busy = [{"resource_key": "r1", "start": _at(THU, "14:00"), "end": _at(THU, "16:45")}]
    times = _times(slots.find(SALON, THU, service="컷", staff="원장", busy=busy, now=NOW))
    # 12:45 시작은 간격(30분) 밖. 12:30 시작 → 13:45(정리 포함) 끝이라 가능, 13:00 시작 → 14:15 끝이라 겹침
    assert "12:30" in times and "13:00" not in times


def test_staff_minutes_and_last_fit():
    # 원장 펌 150분: 20:00 마감 → 마지막 17:30. 실장 180분: 17:00
    assert _times(slots.find(SALON, THU, service="펌", staff="원장", now=NOW))[-1] == "17:30"
    assert _times(slots.find(SALON, THU, service="펌", staff="실장", now=NOW))[-1] == "17:00"
    # 실장은 목요일 12시부터
    assert _times(slots.find(SALON, THU, service="펌", staff="실장", now=NOW))[0] == "12:00"


def test_capable_staff_and_days_off():
    assert all(f["resource_key"] == "r1" for f in slots.find(SALON, THU, service="염색", now=NOW))
    fri = THU + datetime.timedelta(days=1)
    assert slots.find(SALON, fri, service="컷", staff="실장", now=NOW) == []
    assert slots.find(SALON, THU - datetime.timedelta(days=3), service="컷", now=NOW) == []  # 월요일 휴무


def test_any_staff_picks_least_loaded():
    busy = [{"resource_key": "r1", "start": _at(THU, "10:00"), "end": _at(THU, "11:15")}]
    found = {f["time"]: f["resource_key"] for f in slots.find(SALON, THU, service="컷", busy=busy, now=NOW)}
    assert found["12:00"] == "r2"   # 원장은 이미 1건 → 실장
    assert found["11:30"] == "r1"   # 실장은 12시부터라 원장뿐


def test_closures_shop_and_resource():
    closures = [{"resource_key": None, "start": _at(THU, "14:00"), "end": _at(THU, "16:00")},
                {"resource_key": "r2", "start": _at(THU, "00:00"), "end": _at(THU, "23:59")}]
    found = slots.find(SALON, THU, service="컷", closures=closures, now=NOW)
    assert all(f["resource_key"] == "r1" for f in found)
    times = _times(found)
    assert "13:30" not in times and "14:00" not in times and "16:00" in times


def test_lead_time_and_max_days():
    now = datetime.datetime.combine(THU, datetime.time(13, 10), tzinfo=KST)
    assert _times(slots.find(SALON, THU, service="컷", staff="원장", now=now))[0] == "15:30"
    far = NOW.date() + datetime.timedelta(days=31)
    assert slots.find(SALON, far, service="컷", now=NOW) == []


def test_unknown_service_or_closed_day():
    assert slots.find(SALON, THU, service="네일", now=NOW) == []


def test_table_pacing_meal_time_break_and_last_start():
    times = _times(slots.find(DINER, THU, party=4, now=NOW))
    assert "13:30" in times and "14:00" not in times      # 90분 식사가 15:00 브레이크 전에 끝나야
    assert "17:00" in times and times[-1] == "20:00"      # 마지막 예약 20:00
    busy = [{"start": _at(THU, "18:00"), "party": 6}]
    assert "18:00" not in _times(slots.find(DINER, THU, party=4, busy=busy, now=NOW))  # 6+4 > 8명
    assert "18:00" in _times(slots.find(DINER, THU, party=2, busy=busy, now=NOW))
    busy2 = busy + [{"start": _at(THU, "18:00"), "party": 1}]
    assert "18:00" not in _times(slots.find(DINER, THU, party=1, busy=busy2, now=NOW))  # 2팀 한도
    assert slots.find(DINER, THU, party=9, now=NOW) == []


def test_next_days_skips_closed():
    wed = THU - datetime.timedelta(days=1)
    got = slots.next_days(DINER, wed, party=2, now=NOW)
    assert got[0]["date"] == THU and got[0]["first"] == "11:30"
