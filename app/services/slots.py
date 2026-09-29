"""빈 시간 계산 (BOOKING_BOT_IMPL_PLAN CAL-1~CAL-6). 순수 함수, DB 없음.

busy: 자리를 잡고 있는 예약 [{resource_key, start, end, party}] (held·requested·confirmed만 넘긴다).
closures: 막힌 구간 [{resource_key(None = 가게 전체), start, end}].
시각은 KST aware datetime.
"""
import datetime
from typing import Optional

from app.services import booking_spec as S

KST = datetime.timezone(datetime.timedelta(hours=9))


def _at(day: datetime.date, minutes: int) -> datetime.datetime:
    return datetime.datetime.combine(day, datetime.time(0, 0), tzinfo=KST) + datetime.timedelta(minutes=minutes)


def _overlap(a0, a1, b0, b1) -> bool:
    return a0 < b1 and b0 < a1


def _blocked(closures, key, start, end) -> bool:
    return any((c.get("resource_key") in (None, key)) and _overlap(start, end, c["start"], c["end"])
               for c in closures)


def _starts(spec: dict, spans, length: int, day: datetime.date, now: datetime.datetime):
    """구간 안에서 length분이 들어가는 시작 시각(분). lead·max_days·last_start 적용."""
    pol = S.policy(spec)
    step = int(spec.get("step_min") or 30)
    today = now.astimezone(KST).date()
    if day > today + datetime.timedelta(days=int(pol["max_days"])):
        return
    earliest = now + datetime.timedelta(minutes=int(pol["lead_min"]))
    last = S.to_min(pol["last_start"]) if pol.get("last_start") else None
    for a, b in spans:
        t, end = S.to_min(a), S.to_min(b)
        while t + length <= end:
            if (last is None or t <= last) and _at(day, t) >= earliest:
                yield t
            t += step


def _resource_spans(spec: dict, res: dict, dow: str):
    if dow in (res.get("days_off") or []):
        return []
    hours = res.get("hours") or spec.get("weekly_hours") or {}
    return hours.get(dow) or []


def find(spec: dict, day: datetime.date, *, service: Optional[str] = None, staff: Optional[str] = None,
         party: int = 1, busy=(), closures=(), now: Optional[datetime.datetime] = None) -> list[dict]:
    """가능한 시각 [{time, start, end, resource_key}]. 시각 순."""
    now = now or datetime.datetime.now(KST)
    dow = S.DAYS[day.weekday()]
    if not (spec.get("weekly_hours") or {}).get(dow):
        return []
    if spec.get("mode") == "table":
        return _find_table(spec, day, dow, party, busy, closures, now)
    svc = S.service(spec, service)
    if svc is None:
        return []
    buffer = int(svc.get("buffer_min") or 0)
    people = [r for r in S.capable(spec, svc) if staff in (None, "", r.get("name"))]
    load = {r["key"]: sum(1 for b in busy if b.get("resource_key") == r["key"] and b["start"].astimezone(KST).date() == day)
            for r in people}
    best: dict = {}
    for r in people:
        minutes = S.duration(svc, r.get("name"))
        for t in _starts(spec, _resource_spans(spec, r, dow), minutes, day, now):
            start, end = _at(day, t), _at(day, t + minutes)
            hold_end = end + datetime.timedelta(minutes=buffer)
            if _blocked(closures, r["key"], start, end):
                continue
            if any(b.get("resource_key") == r["key"] and _overlap(start, hold_end, b["start"], b["end"]) for b in busy):
                continue
            prev = best.get(t)
            # "상관없음"이면 그날 예약이 가장 적은 담당자 (같으면 목록 순서)
            if prev is None or load[r["key"]] < load[prev["resource_key"]]:
                best[t] = {"time": S.hhmm(t), "start": start, "end": hold_end, "resource_key": r["key"]}
    return [best[t] for t in sorted(best)]


def _find_table(spec, day, dow, party, busy, closures, now) -> list[dict]:
    pol = S.policy(spec)
    if not int(pol["party_min"]) <= party <= int(pol["party_max"]):
        return []
    minutes = S.meal_minutes(spec, party)
    pace = spec.get("pace") or {}
    teams, people = int(pace.get("teams") or 0), int(pace.get("people") or 0)
    out = []
    for t in _starts(spec, spec["weekly_hours"][dow], minutes, day, now):
        start, end = _at(day, t), _at(day, t + minutes)
        if _blocked(closures, None, start, end):
            continue
        same = [b for b in busy if b["start"] == start]
        if len(same) + 1 > teams or sum(int(b.get("party") or 1) for b in same) + party > people:
            continue
        out.append({"time": S.hhmm(t), "start": start, "end": end, "resource_key": None})
    return out


def next_days(spec: dict, start_day: datetime.date, *, count: int = 3, busy_for=None, closures=(), **kw) -> list[dict]:
    """start_day부터 가능한 날 count개 [{date, first}]. busy_for(day) -> busy 목록."""
    now = kw.pop("now", None) or datetime.datetime.now(KST)
    limit = int(S.policy(spec)["max_days"])
    out, day = [], start_day
    for _ in range(limit + 1):
        found = find(spec, day, busy=(busy_for(day) if busy_for else ()), closures=closures, now=now, **kw)
        if found:
            out.append({"date": day, "first": found[0]["time"]})
            if len(out) >= count:
                break
        day += datetime.timedelta(days=1)
    return out
