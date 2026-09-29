"""봇메이커: 사장님 인터뷰로 예약 명세를 만든다 (BOTMAKER_PLAN, BOOKING_BOT_IMPL_PLAN BM-1~BM-8).

요구사항 엔진과 같은 원칙: 무엇을 물을지는 규칙, 답은 결정론 파서 먼저·AI는 보조, 말에 없는 숫자는 넣지 않는다.
- 한 번에 하나, 추천 답은 버튼. 출구 세 개(추천대로·나중에·알아서)는 늘 열려 있다.
- 순서: ① 모순 ② 빈 필수 칸 ③ 조건이 켜진 파고들기 질문 ④ 미뤄 둔 칸 한 번 더 → 모의 손님 시험 → 켜기.
- 상태는 draft 명세 안의 `_interview`에 둔다(물은 것·미룬 것·지금 질문).
"""
import copy
import datetime
import json
import logging
import re
from typing import Optional

from app import llm
from app.services import booking_engine
from app.services import booking_spec as S
from app.services import numbers, slots
from app.services.slots import KST

log = logging.getLogger(__name__)

DONE = ("filled", "default", "assumed")
EXITS = [{"label": "추천대로", "action": "default"}, {"label": "나중에", "action": "later"},
         {"label": "알아서 해 주세요", "action": "let_ai"}]
_KO_DAYS = "월화수목금토일"
_NATIVE = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10,
           "열한": 11, "열두": 12}
_NUM = r"(\d{1,2}|열한|열두|다섯|여섯|일곱|여덟|아홉|한|두|세|네|열)"
_YES = ("네", "예", "응", "맞아요", "맞아", "좋아요", "그래요", "있어요", "있음", "ㅇㅇ", "넵", "yes")
_NO = ("아니요", "아니오", "아니", "없어요", "없음", "없습니다", "안 해요", "no")


# ── 경로 ──

def _find(items, name):
    return next((x for x in items or [] if x.get("name") == name), None)


def get_path(spec: dict, path: str):
    m = re.fullmatch(r"(services|resources)\[(.+?)\]\.(\w+)", path)
    if m:
        item = _find(spec.get(m.group(1)), m.group(2))
        return None if item is None else item.get(m.group(3))
    cur = spec
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def set_path(spec: dict, path: str, value) -> None:
    m = re.fullmatch(r"(services|resources)\[(.+?)\]\.(\w+)", path)
    if m:
        kind, name, field = m.groups()
        items = spec.setdefault(kind, [])
        targets = items if name == "*" else [x for x in items if x.get("name") == name]
        for item in targets:
            item[field] = value
        return
    if path == "services":
        old = {s["name"]: s for s in spec.get("services") or []}
        spec["services"] = [old.get(n) or {"name": n} for n in value]
        return
    if path == "resources":
        old = {r["name"]: r for r in spec.get("resources") or []}
        used = [int(r["key"][1:]) for r in old.values() if re.fullmatch(r"r\d+", r.get("key") or "")]
        nxt = max(used, default=0)
        out = []
        for n in value:
            if n in old:
                out.append(old[n])
            else:
                nxt += 1  # 한 번 쓴 key는 다시 쓰지 않는다(예약의 resource_key가 가리킴)
                out.append({"key": f"r{nxt}", "kind": "staff", "name": n})
        spec["resources"] = out
        return
    if path == "breaks":
        spec["weekly_hours"] = {d: _subtract(spans, value) for d, spans in (spec.get("weekly_hours") or {}).items()}
        return
    parts = path.split(".")
    cur = spec
    for part in parts[:-1]:
        cur = cur.setdefault(part, {})
    cur[parts[-1]] = value


def _subtract(spans, cuts):
    out = []
    for a, b in spans:
        pieces = [(S.to_min(a), S.to_min(b))]
        for c0, c1 in ((S.to_min(x), S.to_min(y)) for x, y in cuts):
            nxt = []
            for p0, p1 in pieces:
                if c1 <= p0 or c0 >= p1:
                    nxt.append((p0, p1))
                    continue
                if p0 < c0:
                    nxt.append((p0, c0))
                if c1 < p1:
                    nxt.append((c1, p1))
            pieces = nxt
        out += [[S.hhmm(p0), S.hhmm(p1)] for p0, p1 in pieces]
    return out


# ── 파서 (결정론) ──

def _n(tok: str) -> int:
    return int(tok) if tok.isdigit() else _NATIVE[tok]


def parse_minutes(text: str) -> Optional[int]:
    """"두 시간 반" 150, "2시간 30분" 150, "90분" 90, "1시간" 60, "150" 150."""
    t = re.sub(r"\s+", "", text or "")
    total, hit = 0, False
    m = re.search(_NUM + r"시간(반)?", t)
    if m:
        total += _n(m.group(1)) * 60 + (30 if m.group(2) else 0)
        hit = True
    m = re.search(r"(\d{1,3})분", t)
    if m:
        total += int(m.group(1))
        hit = True
    if not hit:
        m = re.fullmatch(r"(\d{2,3})", t)
        if m:
            total, hit = int(m.group(1)), True
    return total if hit and 0 < total <= 12 * 60 else None


def _to_min(prefix: str, hour: int, minute: int) -> int:
    if prefix in ("오후", "저녁", "밤") and hour < 12:
        hour += 12
    if prefix == "오전" and hour == 12:
        hour = 0
    return hour * 60 + minute


def parse_ranges(text: str) -> list:
    """글 속의 시간 구간 [["HH:MM","HH:MM"], …]. "10시~8시"는 20시로, "오후 3시~5시"는 17시로."""
    t = re.sub(r"\s+", "", text or "")
    pat = re.compile(r"(오전|오후|저녁|밤|아침)?" + _NUM + r"(?::(\d{2}))?시?(반)?(?:부터|~|-|–)+"
                     r"(오전|오후|저녁|밤)?" + _NUM + r"(?::(\d{2}))?시?(반)?")
    out = []
    for m in pat.finditer(t):
        p1, h1, m1, half1, p2, h2, m2, half2 = m.groups()
        # 가게 영업에서 오전·오후 없이 말한 1~6시는 오후로 본다("3시~5시 브레이크")
        a = _to_min(p1 or ("오후" if 1 <= _n(h1) <= 6 else ""), _n(h1), int(m1 or 0) + (30 if half1 else 0))
        b = _to_min(p2 or ("오후" if not p1 and 1 <= _n(h1) <= 6 else ""), _n(h2), int(m2 or 0) + (30 if half2 else 0))
        if not p2 and b <= a:
            b += 12 * 60
        if 0 <= a < b <= 24 * 60:
            out.append([S.hhmm(a), S.hhmm(b)])
    return out


def parse_days(text: str) -> Optional[list]:
    """"월요일", "화, 수" → ["mon"…]. "없어요" → []. 못 읽으면 None."""
    t = re.sub(r"\s+", "", text or "")
    if any(w in t for w in ("없", "안쉬", "연중무휴")):
        return []
    found = [S.DAYS[_KO_DAYS.index(c)] for c in re.findall(r"([월화수목금토일])(?:요일|,|/|·|$|랑|이랑|하고|과|와|쉬|휴무)", t)]
    return sorted(set(found), key=S.DAYS.index) if found else None


def _scope(seg: str) -> Optional[list]:
    m = re.search(r"([월화수목금토일])(?:요일)?~([월화수목금토일])", seg)
    if m:
        a, b = _KO_DAYS.index(m.group(1)), _KO_DAYS.index(m.group(2))
        return list(S.DAYS[a:b + 1]) if b >= a else list(S.DAYS[a:]) + list(S.DAYS[:b + 1])
    if "매일" in seg or "연중무휴" in seg:
        return list(S.DAYS)
    if "평일" in seg:
        return list(S.DAYS[:5])
    if "주말" in seg:
        return list(S.DAYS[5:])
    days = re.findall(r"([월화수목금토일])(?:요일)?(?=[0-9오전후저녁밤열한두세네다여일아,]|$)", seg)
    return [S.DAYS[_KO_DAYS.index(d)] for d in days] or None


def parse_week(text: str) -> Optional[dict]:
    """"화~일 10시~8시, 월요일 휴무", "평일 10~20시, 토요일 10~15시" → weekly_hours."""
    t = re.sub(r"\s+", "", text or "")
    weekly: dict = {}
    closed = set()
    last_scope = None
    for seg in re.split(r"[,，/\n]|그리고", t):
        if not seg:
            continue
        if re.search(r"휴무|쉬", seg) and not parse_ranges(seg):
            closed |= set(parse_days(seg) or [])
            continue
        spans = parse_ranges(seg)
        if not spans:
            continue
        scope = _scope(seg)
        if scope is None and last_scope is not None:
            # "매일 11시~15시, 17시~21시": 요일 없는 조각은 앞 조각의 요일에 구간을 더한다
            for d in last_scope:
                weekly[d] = weekly.get(d, []) + spans
            continue
        last_scope = scope or list(S.DAYS)
        for d in last_scope:
            weekly[d] = spans
    if not weekly:
        return None
    for d in closed:
        weekly.pop(d, None)
    return weekly


def parse_names(text: str) -> list:
    t = (text or "").strip()
    if re.search(r"혼자|저만|저 혼자|1인", t):
        return ["사장님"]
    parts = re.split(r"[,，/·、\n]|그리고|\s랑\s|\s하고\s", t) if re.search(r"[,，/·、\n]|그리고", t) else t.split()
    names = [re.sub(r"(이에요|예요|입니다|요|이요)$", "", p.strip()) for p in parts]
    return [n for n in names if n and len(n) <= 20]


def parse_yes(text: str) -> Optional[bool]:
    t = (text or "").strip()
    if any(t.startswith(w) for w in _NO):
        return False
    if any(t.startswith(w) for w in _YES):
        return True
    return None


def _first_int(text: str) -> Optional[int]:
    nums = sorted(n for n in numbers.numbers_in(text or "") if isinstance(n, int))
    return nums[0] if nums else None


def parse_hours_before(text: str) -> Optional[int]:
    """"전날까지" 1440분, "2시간 전" 120, "하루 전" 1440 → 분."""
    t = re.sub(r"\s+", "", text or "")
    if "전날" in t or "하루" in t:
        return 24 * 60
    m = parse_minutes(t)
    return m


# ── 질문 ──

def _q(qid, path, ask, kind, suggest=(), default=None, required=False):
    return {"id": qid, "path": path, "ask": ask, "kind": kind, "suggest": list(suggest), "default": default,
            "required": required}


def _longest_close(spec) -> int:
    return max((S.to_min(b) for spans in (spec.get("weekly_hours") or {}).values() for _, b in spans), default=0)


def _questions(spec: dict) -> list[dict]:
    """지금 명세에서 물을 수 있는 질문 전부 (순서 = 묻는 순서)."""
    mode = spec["mode"]
    qs = [_q("week", "weekly_hours", "영업하는 요일과 시간을 알려 주세요. 예: '화~일 10시~8시, 월요일 휴무'",
             "week", required=True),
          _q("step", "step_min", "예약은 몇 분 간격으로 받을까요? 대부분 30분이에요.", "choice",
             [("30분", 30), ("1시간", 60), ("15분", 15)], 30, required=True)]
    if mode == "slot":
        qs.append(_q("services", "services", "예약으로 받는 시술을 알려 주세요. 예: '컷, 펌, 염색, 클리닉'", "names",
                     required=True))
        for s in spec.get("services") or []:
            name = s["name"]
            guess = S.DEFAULTS["slot"]["services"].get(name)
            qs.append(_q(f"dur:{name}", f"services[{name}].duration_min",
                         f"{name}은(는) 보통 몇 분 걸리나요? 예: '두 시간 반'", "minutes",
                         [(f"{guess // 60}시간" + (f" {guess % 60}분" if guess % 60 else ""), guess)] if guess else [],
                         guess or 60, required=True))
        qs.append(_q("staff", "resources", "예약을 받는 선생님을 알려 주세요. 예: '원장, 실장' / 혼자 하시면 '혼자'",
                     "names", required=True))
    else:
        qs += [_q("meal", "meal_minutes", "손님 한 팀 식사 시간은 보통 얼마나 잡을까요? 예: '1시간 반', '2명 1시간, 4명 1시간 반'",
                  "meal", [("1시간 반", {"1-99": 90}), ("2시간", {"1-99": 120})],
                  S.DEFAULTS["table"]["meal_minutes"], required=True),
               _q("teams", "pace.teams", "같은 시각(30분 칸)에 최대 몇 팀까지 받을까요?", "number",
                  [("2팀", 2), ("3팀", 3), ("5팀", 5)], 3, required=True),
               _q("people", "pace.people", "같은 시각에 최대 몇 명까지 받을까요? 좌석 수를 생각해 주세요.", "number",
                  [("8명", 8), ("12명", 12), ("20명", 20)], 12, required=True),
               _q("party_max", "policy.party_max", "채팅으로 몇 명까지 받을까요? 넘으면 전화로 안내할게요.", "number",
                  [("6명", 6), ("8명", 8), ("10명", 10)], 8, required=True)]
    qs.append(_q("lead", "policy.lead_min", "예약은 방문 몇 시간 전까지 받을까요?", "before",
                 [("1시간 전", 60), ("2시간 전", 120), ("전날까지", 1440)], 120, required=True))
    qs.append(_q("auto", "policy.auto_confirm",
                 "빈 시간이 확실하면 제가 바로 확정할까요, 사장님이 확인하실래요?", "yesno",
                 [("바로 확정", True), ("제가 확인할게요", False)], False, required=True))
    # 파고들기 (조건이 켜질 때만, BOTMAKER_PLAN §2)
    people = S.staff(spec)
    services = spec.get("services") or []
    if mode == "slot" and services:
        qs.append(_q("buffer", "services[*].buffer_min",
                     "시술이 끝나고 다음 손님 전에 정리 시간이 필요하세요? 예: 펌 손님이 2시에 끝나면 2시 15분부터 받기",
                     "minutes", [("15분", 15), ("10분", 10), ("바로 받아요", 0)], 15))
    if mode == "slot" and len(people) >= 2:
        qs.append(_q("staff_min", "staff_minutes", "선생님마다 시간이 다른 시술이 있나요? 예: '실장은 펌 3시간'",
                     "staff_minutes", [("없어요", None)], None))
        qs.append(_q("staff_only", "staff_only", "특정 선생님만 하는 시술이 있나요? 예: '염색은 원장만'",
                     "staff_only", [("없어요", None)], None))
        for r in people:
            qs.append(_q(f"off:{r['name']}", f"resources[{r['name']}].days_off",
                         f"{r['name']} 선생님이 따로 쉬는 요일이 있나요? 예: '화요일'", "days",
                         [("가게 휴무일만", [])], []))
    if mode == "slot" and any(int(s.get("duration_min") or 0) >= 120 for s in services):
        close = _longest_close(spec)
        qs.append(_q("last", "policy.last_start",
                     f"긴 시술은 마감({S.hhmm(close)}) 전에 끝나게 제가 자동으로 막아요. 이것과 별도로 마지막 예약 시각이 있나요?",
                     "time", [("따로 없어요", None)], None))
    qs.append(_q("break", "breaks", "중간에 쉬는 시간(브레이크)이 있나요? 예: '3시~5시'", "break",
                 [("없어요", [])], []))
    qs.append(_q("cancel", "policy.cancel_deadline_hours", "손님이 채팅으로 취소할 수 있는 건 방문 몇 시간 전까지로 할까요?",
                 "number", [("3시간 전", 3), ("하루 전", 24)], 3))
    return qs


def _state(spec: dict) -> dict:
    return spec.setdefault("_interview", {"asked": [], "skipped": [], "pending": None, "later_round": False})


def _prov(spec: dict) -> dict:
    return spec.setdefault("provenance", {})


def _answered(spec: dict, q: dict) -> bool:
    return _prov(spec).get(q["path"]) in DONE


def _contradiction(spec: dict, qs: list) -> Optional[dict]:
    by_path = {q["path"]: q for q in qs}
    for p in S.validate({k: v for k, v in spec.items() if not k.startswith("_")}):
        m = re.fullmatch(r"services\.(.+?)\.(duration_min|staff)", p["path"])
        path = f"services[{m.group(1)}].duration_min" if m else p["path"]
        q = by_path.get(path) or (by_path.get("policy.last_start") if p["path"] == "policy.last_start" else None)
        if q is not None and _answered(spec, q):
            q = dict(q)
            q["ask"] = p["msg"] + " " + q["ask"]
            q["contradiction"] = True
            return q
    return None


def next_question(spec: dict) -> Optional[dict]:
    st = _state(spec)
    qs = _questions(spec)
    bad = _contradiction(spec, qs)
    if bad:
        return bad
    for q in qs:
        if q["required"] and not _answered(spec, q) and q["id"] not in st["skipped"]:
            return q
    for q in qs:
        if not q["required"] and q["id"] not in st["asked"] and not _answered(spec, q):
            return q
    for q in qs:  # 미뤄 둔 필수 칸은 끝에서 한 번 더
        if q["required"] and not _answered(spec, q) and q["id"] in st["skipped"] and not st["later_round"]:
            st["later_round"] = True
            return q
    return None


def progress(spec: dict) -> dict:
    req = [q for q in _questions(spec) if q["required"]]
    return {"done": sum(1 for q in req if _answered(spec, q)), "total": len(req)}


# ── 답 적용 ──

def _apply(spec: dict, q: dict, value, status: str) -> None:
    if q["kind"] == "staff_minutes":
        for staff_name, svc, minutes in value or []:
            s = _find(spec.get("services"), svc)
            if s is not None:
                s.setdefault("staff_minutes", {})[staff_name] = minutes
    elif q["kind"] == "staff_only":
        for svc, names in value or []:
            s = _find(spec.get("services"), svc)
            if s is not None:
                s["staff"] = names
    elif value is not None or q["kind"] in ("time",):
        set_path(spec, q["path"], value)
    _prov(spec)[q["path"]] = status
    st = _state(spec)
    if q["id"] not in st["asked"]:
        st["asked"].append(q["id"])
    if q["id"] in st["skipped"]:
        st["skipped"].remove(q["id"])


def _parse(spec: dict, q: dict, text: str):
    """(성공, 값). 결정론 파서."""
    kind = q["kind"]
    t = text.strip()
    for label, value in q["suggest"]:
        if re.sub(r"\s+", "", label) == re.sub(r"\s+", "", t):
            return True, value
    if kind == "week":
        v = parse_week(t)
        return v is not None, v
    if kind == "minutes":
        if re.search(r"바로|없", t):
            return True, 0
        v = parse_minutes(t)
        return v is not None, v
    if kind == "before":
        v = parse_hours_before(t)
        return v is not None, v
    if kind == "number":
        if "하루" in t and "cancel" in q["id"]:
            return True, 24
        v = _first_int(t)
        return v is not None and v > 0, v
    if kind == "choice":
        v = parse_minutes(t) or _first_int(t)
        allowed = [val for _, val in q["suggest"]] + list(S.STEPS)
        return v in allowed, v
    if kind == "names":
        v = parse_names(t)
        return bool(v), v
    if kind == "yesno":
        if re.search(r"바로|자동", t):
            return True, True
        if re.search(r"확인|제가", t):
            return True, False
        v = parse_yes(t)
        return v is not None, v
    if kind == "days":
        v = parse_days(t)
        return v is not None, v
    if kind == "time":
        if re.search(r"없|자동", t):
            return True, None
        m = re.search(r"(오전|오후|저녁|밤)?\s*" + _NUM + r"\s*시\s*(반)?", t)
        if m:
            return True, S.hhmm(_to_min(m.group(1) or ("오후" if _n(m.group(2)) < 9 else ""), _n(m.group(2)),
                                        30 if m.group(3) else 0))
        return False, None
    if kind == "break":
        if re.search(r"없", t):
            return True, []
        v = parse_ranges(t)
        return bool(v), v
    if kind == "meal":
        pairs = re.findall(r"(\d+)\s*명[^,]*?(" + _NUM + r"\s*시간\s*반?|\d+\s*분)", t)
        if pairs:
            out, prev = {}, 1
            for n, dur, _ in sorted(pairs, key=lambda p: int(p[0])):
                out[f"{prev}-{int(n)}"] = parse_minutes(dur)
                prev = int(n) + 1
            out[f"{prev}+"] = list(out.values())[-1]
            return True, out
        v = parse_minutes(t)
        return v is not None, {"1-99": v} if v else None
    if kind == "staff_minutes":
        if re.search(r"^없|없어", t):
            return True, []
        out = []
        for clause in re.split(r"[,，\n]|그리고", t):
            who = next((r["name"] for r in S.staff(spec) if r["name"] in clause), None)
            svc = next((s["name"] for s in spec.get("services") or [] if s["name"] in clause), None)
            minutes = parse_minutes(clause)
            if who and svc and minutes:
                out.append((who, svc, minutes))
        return bool(out), out
    if kind == "staff_only":
        if re.search(r"^없|없어", t):
            return True, []
        out = []
        for clause in re.split(r"[,，\n]|그리고", t):
            svc = next((s["name"] for s in spec.get("services") or [] if s["name"] in clause), None)
            who = [r["name"] for r in S.staff(spec) if r["name"] in clause]
            if svc and who:
                out.append((svc, who))
        return bool(out), out
    return False, None


_LLM_SYSTEM = (
    "너는 가게 예약 설정 도우미다. 사장님의 답에서 지금 질문에 해당하는 값만 JSON으로 뽑는다. "
    '형식: {"value": <값 또는 null>}. 사장님이 말하지 않은 숫자는 절대 만들지 않는다. 모르면 null.')


def _llm_parse(q: dict, text: str):
    try:
        raw = llm.chat_json(_LLM_SYSTEM, json.dumps({"question": q["ask"], "kind": q["kind"], "answer": text},
                                                    ensure_ascii=False))
        value = json.loads(raw).get("value")
    except Exception:
        log.warning("봇메이커 LLM 추출 실패", exc_info=True)
        return False, None
    if value is None:
        return False, None
    if not numbers.grounded_numbers(json.dumps(value, ensure_ascii=False), text):
        return False, None  # 말에 없는 숫자 (BM-2)
    ok_kind = {"minutes": int, "number": int, "before": int, "choice": int, "names": list, "days": list,
               "yesno": bool, "week": dict, "break": list, "meal": dict}.get(q["kind"])
    if ok_kind is None or not isinstance(value, ok_kind):
        return False, None
    if q["kind"] == "week" and not all(d in S.DAYS and S._spans_ok(v) for d, v in value.items()):
        return False, None
    return True, value


# ── 인터뷰 ──

def seed(card: Optional[dict], mode: Optional[str] = None) -> dict:
    """카드에서 아는 것을 불러온 새 명세. 불러온 값은 'card'(확인 필요)로 표시한다."""
    card = card or {}
    if mode is None:
        from app.services import archetype as arch
        try:
            code, _ = arch.of(card)
        except Exception:
            code = "A"
        mode = "slot" if code in ("B", "F") else "table"
    spec = S.with_defaults(mode)
    prov = _prov(spec)
    from app.services import availability, card_data
    try:
        sched = availability.schedule(card) if card else {"source": "assumed"}
        if sched.get("source") == "owner":
            spec["weekly_hours"] = sched["weekly"]
            prov["weekly_hours"] = "card"
    except Exception:
        pass
    if mode == "slot":
        try:
            data = card_data.build(card) if card.get("slots") else {}
        except Exception:
            data = {}
        names = [s.get("name") for s in data.get("staff") or [] if s.get("name")]
        if names:
            set_path(spec, "resources", names)
            prov["resources"] = "card"
        items = [i["name"] for cat in data.get("catalog") or [] for i in cat.get("items") or []]
        if items:
            set_path(spec, "services", items[:12])
            for cat in data.get("catalog") or []:
                for item in cat.get("items") or []:
                    name = item.get("name")
                    if item.get("duration_min") is not None:
                        set_path(spec, f"services[{name}].duration_min", item["duration_min"])
                    if item.get("price_won") is not None:
                        set_path(spec, f"services[{name}].price", item["price_won"])
            prov["services"] = "card"
    return spec


def _buttons(spec: dict, q: dict) -> list:
    out = []
    current = get_path(spec, q["path"]) if _prov(spec).get(q["path"]) == "card" else None
    if current:
        out.append({"label": "지금 알고 있는 대로", "action": "keep"})
    out += [{"label": label, "action": f"pick:{i}"} for i, (label, _) in enumerate(q["suggest"])]
    if q["default"] is None and q["required"]:
        # 영업시간·시술·선생님처럼 대신 정할 값이 없는 칸은 미루기만 된다
        return out + [e for e in EXITS if e["action"] == "later"]
    return out + EXITS


def _show(spec: dict, q: dict) -> str:
    if _prov(spec).get(q["path"]) != "card":
        return q["ask"]
    cur = get_path(spec, q["path"])
    if q["path"] == "weekly_hours":
        cur = ", ".join(f"{S.DAY_KO[d]} " + " · ".join(f"{a}~{b}" for a, b in spans)
                        for d, spans in cur.items()) or "없음"
    elif isinstance(cur, list):
        cur = ", ".join(x.get("name", str(x)) if isinstance(x, dict) else str(x) for x in cur)
    return f"제가 이렇게 알고 있어요: {cur}\n맞으면 '지금 알고 있는 대로'를, 다르면 말씀해 주세요. ({q['ask']})"


def _clean(spec: dict) -> dict:
    return {k: v for k, v in spec.items() if k != "_interview"}


def _reply_for(spec: dict, lead: str = "") -> dict:
    q = next_question(spec)
    st = _state(spec)
    if q is None:
        st["pending"] = None
        results = simulate(_clean(spec))
        ok = all(r["ok"] for r in results)
        problems = S.validate(_clean(spec))
        lines = [lead] if lead else []
        lines.append("설정이 다 모였어요. 손님이 이렇게 물으면 봇은 이렇게 답해요:")
        lines += [f"{'✅' if r['ok'] else '⚠'} 손님: {r['customer']}\n   봇: {r['bot']}" for r in results]
        buttons = ([{"label": "봇 켜기", "action": "activate"}] if ok and not problems else []) + \
            [{"label": "고칠래요", "action": "fix"}]
        return {"reply": "\n".join(lines), "buttons": buttons, "progress": progress(spec),
                "ready": ok and not problems, "simulation": results}
    st["pending"] = q["id"]
    text = (lead + "\n" if lead else "") + _show(spec, q)
    return {"reply": text, "buttons": _buttons(spec, q), "progress": progress(spec), "ready": False}


def turn(spec: dict, *, text: Optional[str] = None, action: Optional[str] = None) -> tuple[dict, dict]:
    """(바뀐 명세, 답). 저장은 부른 쪽(API)이 draft로 한다."""
    spec = copy.deepcopy(spec)
    st = _state(spec)
    q = next((x for x in _questions(spec) if x["id"] == st.get("pending")), None)
    if action == "fix":
        st["pending"] = None
        return spec, {"reply": "어느 것을 고칠까요?", "ready": False, "progress": progress(spec),
                      "buttons": [{"label": lbl, "action": f"redo:{qid}"} for lbl, qid in
                                  (("영업시간", "week"), ("예약 간격", "step"), ("시술·메뉴", "services"),
                                   ("선생님", "staff"), ("받는 규칙", "lead"), ("자동 확정", "auto"))]}
    if action and action.startswith("redo:"):
        qid = action[5:]
        target = next((x for x in _questions(spec) if x["id"] == qid), None)
        if target:
            _prov(spec).pop(target["path"], None)
            if qid in st["asked"]:
                st["asked"].remove(qid)
        return spec, _reply_for(spec)
    if q is None:
        return spec, _reply_for(spec)
    lead = ""
    if action == "keep":
        _apply(spec, q, get_path(spec, q["path"]), "filled")
    elif action and action.startswith("pick:"):
        i = int(action[5:])
        if 0 <= i < len(q["suggest"]):
            _apply(spec, q, q["suggest"][i][1], "filled")
    elif action in ("default", "let_ai") and q["default"] is None and q["required"]:
        return spec, _reply_for(spec, "이건 사장님만 아시는 거라 제가 정할 수 없어요.")
    elif action == "default":
        _apply(spec, q, q["default"], "default")
    elif action == "let_ai":
        _apply(spec, q, q["default"], "assumed")
        lead = "제가 보통 값으로 넣어 둘게요. 규칙 카드에 표시해 두고 나중에 다시 여쭤볼게요."
    elif action == "later":
        if q["id"] not in st["skipped"]:
            st["skipped"].append(q["id"])
        if q["id"] not in st["asked"]:
            st["asked"].append(q["id"])
        if st.get("later_round") and q["required"]:
            _apply(spec, q, q["default"], "assumed")  # 두 번째로 미루면 보통 값으로
    elif text:
        ok, value = _parse(spec, q, text)
        if not ok:
            ok, value = _llm_parse(q, text)
        if not ok:
            return spec, {**_reply_for(spec, "잘 못 알아들었어요. 예처럼 말씀해 주시거나 버튼을 눌러 주세요."),
                          "understood": False}
        _apply(spec, q, value, "filled")
    return spec, _reply_for(spec, lead)


# ── 모의 손님 시험 (BM-6) ──

def simulate(spec: dict, now: Optional[datetime.datetime] = None) -> list[dict]:
    now = now or datetime.datetime.now(KST)
    out = []
    pol = S.policy(spec)
    mode = spec.get("mode")
    svc = (spec.get("services") or [{}])[0].get("name") if mode == "slot" else None
    kw = {"service": svc} if mode == "slot" else {"party": 2}
    start = now.date() + datetime.timedelta(days=1)
    days = slots.next_days(spec, start, count=1, now=now, **kw)
    if not days:
        out.append({"case": "book", "customer": f"{svc or '2명'} 예약하고 싶어요", "ok": False,
                    "bot": f"{pol['max_days']}일 안에 예약 가능한 시간이 하나도 없어요. 영업시간·시술 시간을 확인해 주세요."})
        return out
    day = days[0]["date"]
    found = slots.find(spec, day, now=now, **kw)
    label = f"{day.month}/{day.day}({_KO_DAYS[day.weekday()]})"
    out.append({"case": "book", "customer": f"{label}에 {svc or '2명'} 예약돼요?", "ok": True,
                "bot": f"{label} 가능한 시간: " + ", ".join(f["time"] for f in found[:4]) + (" …" if len(found) > 4 else "")})
    # 겹침: 첫 시각을 누가 잡으면 그 담당자·팀 한도로 다시 막히는지
    first = found[0]
    busy = [{"resource_key": first["resource_key"], "start": first["start"], "end": first["end"], "party": 99}]
    again = slots.find(spec, day, busy=busy, now=now, **kw)
    same = [f for f in again if f["time"] == first["time"] and f["resource_key"] == first["resource_key"]]
    out.append({"case": "overlap", "customer": f"{first['time']}요 (방금 다른 손님이 잡은 시간)", "ok": not same,
                "bot": "그 시간은 방금 찼어요. " + (f"{again[0]['time']}은 어떠세요?" if again else "다른 날을 보여 드릴게요.")})
    if mode == "slot":
        longest = max(spec.get("services") or [], key=lambda s: int(s.get("duration_min") or 0))
        close = max(S.to_min(b) for _, b in spec["weekly_hours"][S.DAYS[day.weekday()]])
        late = S.hhmm(close - int(longest["duration_min"]) + int(spec.get("step_min") or 30))
        late_found = slots.find(spec, day, service=longest["name"], now=now)
        ok = all(S.to_min(f["time"]) + S.duration(longest) <= close for f in late_found)
        out.append({"case": "late", "customer": f"{label} {late}에 {longest['name']}요", "ok": ok,
                    "bot": f"{longest['name']}은(는) {S.duration(longest)}분 걸려서 마감 전에 끝나는 "
                           f"{late_found[-1]['time'] if late_found else '시간'}까지만 받아요."})
    closed = [d for d in S.DAYS if not (spec.get("weekly_hours") or {}).get(d)]
    if closed:
        out.append({"case": "closed", "customer": f"{S.DAY_KO[closed[0]]}요일에 돼요?", "ok": True,
                    "bot": f"{S.DAY_KO[closed[0]]}요일은 쉬는 날이에요."})
    if mode == "table":
        big = int(pol["party_max"]) + 1
        out.append({"case": "party", "customer": f"{big}명이요", "ok": not slots.find(spec, day, party=big, now=now),
                    "bot": f"{big}명 이상 단체는 가게로 전화 주세요."})
    out.append({"case": "cancel_late", "customer": "1시간 뒤 예약 취소할게요", "ok": True,
                "bot": f"방문 {pol['cancel_deadline_hours']}시간 전부터는 채팅으로 취소할 수 없어요. 가게로 전화 주세요."})
    out.append({"case": "unknown", "customer": "강아지 데려가도 돼요?", "ok": True,
                "bot": "그건 사장님께 여쭤보고 이 채팅으로 알려 드릴게요."})
    return out


def activate(shop_id: str, user_id: Optional[str]) -> dict:
    """draft를 켠다(BM-7): 검증 문제 0 + 시험 실패 0. 켤 때 _interview는 빼고 저장한다."""
    got = booking_engine.get_spec(shop_id, "draft")
    if got is None:
        raise booking_engine.NotFound("만들고 있는 설정이 없어요.")
    spec = _clean(got["spec"])
    bad = [r for r in simulate(spec) if not r["ok"]]
    if bad:
        raise booking_engine.EngineError("시험에서 걸린 곳이 있어요: " + bad[0]["bot"])
    booking_engine.save_draft(shop_id, spec, user_id)
    return booking_engine.activate(shop_id, user_id)
