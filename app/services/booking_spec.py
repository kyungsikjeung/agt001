"""예약 명세 (BOOKING_BOT_IMPL_PLAN SPEC-1·SPEC-2, contracts/botmaker_to_bot.schema.json).

봇 = 공통 엔진 + 가게별 명세. 이 모듈은 명세의 기본값과 검증만 한다(DB 없음).
시각은 모두 KST 벽시계 "HH:MM".
"""
import re
from typing import Optional

MODES = ("slot", "table")
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DAY_KO = dict(zip(DAYS, "월화수목금토일"))
STEPS = (10, 15, 20, 30, 60)
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$|^24:00$")

DEFAULT_POLICY = {
    "lead_min": 120,            # 지금부터 몇 분 뒤 시각부터 받나
    "max_days": 30,             # 며칠 뒤까지 받나
    "change_deadline_hours": 24,
    "cancel_deadline_hours": 3,
    "auto_confirm": False,
    "hold_hours": 24,           # 사장님이 결정 안 한 신청이 자리를 잡고 있는 시간
    "party_min": 1,
    "party_max": 8,
    "last_start": None,         # "HH:MM" 이 시각 뒤로는 시작하지 않음
}

# 업종 기본값 (봇메이커가 "추천대로"를 누르면 넣는 값, BOTMAKER_PLAN §1 규칙 5)
DEFAULTS = {
    "slot": {"step_min": 30, "buffer_min": 15,
             "services": {"컷": 60, "펌": 150, "염색": 120, "클리닉": 60}},
    "table": {"step_min": 30, "meal_minutes": {"1-2": 60, "3-4": 90, "5+": 120},
              "pace": {"teams": 3, "people": 12}},
}


def to_min(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def policy(spec: dict) -> dict:
    return {**DEFAULT_POLICY, **(spec.get("policy") or {})}


def service(spec: dict, name: Optional[str]) -> Optional[dict]:
    for s in spec.get("services") or []:
        if s.get("name") == name:
            return s
    return None


def staff(spec: dict) -> list:
    return [r for r in spec.get("resources") or [] if r.get("kind") == "staff" and r.get("active", True)]


def duration(svc: dict, staff_name: Optional[str] = None) -> int:
    """이 담당자가 이 시술에 쓰는 분(정리 시간 제외)."""
    per = svc.get("staff_minutes") or {}
    return int(per.get(staff_name) or svc.get("duration_min") or 0)


def capable(spec: dict, svc: dict) -> list:
    """이 시술을 할 수 있는 담당자. svc.staff가 비면 전원."""
    names = svc.get("staff") or []
    return [r for r in staff(spec) if not names or r.get("name") in names]


def meal_minutes(spec: dict, party: int) -> int:
    """인원별 식사 시간. 키 "1-2"·"3-4"·"5+"."""
    table = spec.get("meal_minutes") or {}
    for key, minutes in table.items():
        if key.endswith("+"):
            if party >= int(key[:-1]):
                return int(minutes)
        elif "-" in key:
            lo, hi = key.split("-")
            if int(lo) <= party <= int(hi):
                return int(minutes)
        elif key.isdigit() and int(key) == party:
            return int(minutes)
    return int(spec.get("meal_default") or 90)


def _spans_ok(spans) -> bool:
    if not isinstance(spans, list):
        return False
    for span in spans:
        if not (isinstance(span, (list, tuple)) and len(span) == 2
                and all(isinstance(t, str) and _HHMM.match(t) for t in span)
                and to_min(span[0]) < to_min(span[1])):
            return False
    return True


def validate(spec: dict) -> list[dict]:
    """문제 목록 [{path, msg}]. 비면 켤 수 있다(BM-7의 절반)."""
    out = []

    def bad(path, msg):
        out.append({"path": path, "msg": msg})

    mode = spec.get("mode")
    if mode not in MODES:
        bad("mode", "예약 방식(시술·식당)을 정해 주세요.")
        return out
    if spec.get("step_min") not in STEPS:
        bad("step_min", "예약 시작 간격(10·15·20·30·60분)을 정해 주세요.")
    weekly = spec.get("weekly_hours") or {}
    if not isinstance(weekly, dict) or not any(weekly.get(d) for d in DAYS):
        bad("weekly_hours", "영업하는 요일과 시간을 알려 주세요.")
    for d in DAYS:
        if weekly.get(d) and not _spans_ok(weekly[d]):
            bad(f"weekly_hours.{d}", f"{DAY_KO[d]}요일 영업시간 형식이 이상해요.")
    pol = policy(spec)
    longest = max((to_min(b) - to_min(a) for d in DAYS for a, b in (weekly.get(d) or []) if _spans_ok([[a, b]])),
                  default=0)
    latest_close = max((to_min(b) for d in DAYS for _, b in (weekly.get(d) or []) if _spans_ok(weekly.get(d))),
                       default=0)
    last = pol.get("last_start")
    if last is not None and not (isinstance(last, str) and _HHMM.match(last)):
        bad("policy.last_start", "마지막 예약 시각 형식이 이상해요.")
        last = None
    if not 1 <= int(pol["party_min"]) <= int(pol["party_max"]):
        bad("policy.party_max", "인원 범위가 이상해요.")

    if mode == "slot":
        services = spec.get("services") or []
        if not services:
            bad("services", "받는 시술과 걸리는 시간을 알려 주세요.")
        people = staff(spec)
        if not people:
            bad("resources", "예약을 받는 선생님(담당자)이 한 명 이상 있어야 해요.")
        for r in people:
            if r.get("hours") and not all(_spans_ok(v) for v in r["hours"].values() if v):
                bad(f"resources.{r.get('name')}.hours", f"{r.get('name')} 근무시간 형식이 이상해요.")
        for s in services:
            name = s.get("name") or "?"
            if not s.get("duration_min") or int(s["duration_min"]) <= 0:
                bad(f"services.{name}.duration_min", f"{name}은(는) 몇 분 걸리나요?")
                continue
            if people and not capable(spec, s):
                bad(f"services.{name}.staff", f"{name}을(를) 할 수 있는 선생님이 없어요.")
            need = max([duration(s, r.get("name")) for r in capable(spec, s)] or [int(s["duration_min"])])
            if longest and need > longest:
                bad(f"services.{name}.duration_min",
                    f"{name} {need}분이 들어갈 만큼 긴 영업 구간이 없어요.")
            if last and latest_close and to_min(last) + int(s["duration_min"]) > latest_close:
                bad("policy.last_start",
                    f"{last}에 {name} 손님이 오면 {hhmm(to_min(last) + int(s['duration_min']))}에 끝나요. "
                    f"마감({hhmm(latest_close)})을 넘어요.")
    else:
        if not spec.get("meal_minutes"):
            bad("meal_minutes", "식사 시간은 보통 몇 분 잡을까요?")
        pace = spec.get("pace") or {}
        if not pace.get("teams") or int(pace["teams"]) <= 0:
            bad("pace.teams", "30분마다 최대 몇 팀까지 받을까요?")
        if not pace.get("people") or int(pace["people"]) <= 0:
            bad("pace.people", "한 번에 최대 몇 명까지 받을까요?")
    return out


def with_defaults(mode: str) -> dict:
    """빈 명세 뼈대 (봇메이커 시작점)."""
    base = {"mode": mode, "weekly_hours": {}, "policy": {}, "provenance": {}}
    if mode == "slot":
        base.update({"services": [], "resources": []})
    else:
        base.update({"meal_minutes": {}, "pace": {}})
    return base
