"""실제 사용자 대화의 규칙 지표 (순수 함수 — DB·LLM·파일 없음).

입력: 세션별 턴 목록. 턴 하나는 dict이다::

    {"user_text": str, "ai_text": str, "state_before": str, "state_after": str,
     "meta": dict | None, "ts": datetime | str | None}

``meta``는 ``prd_engine.turn`` 의 trace
(answered_by_rule, extract_ok, extract_ms, extracted, applied, skip,
asked_slot, next_slot, done, asked) 또는 None(수집 단계 밖 턴)이다.
"""

import datetime as _dt
import re

# 이탈 판정: 요약 전에 끝났고 마지막 턴 뒤 이 시간 이상 무입력이면 이탈.
CHURN_GAP = _dt.timedelta(minutes=30)
# 카드에 반영 안 된 요구 후보: 추출 결과가 비었는데 이 길이 이상인 사장님 말.
MISSED_MIN_LEN = 15
# INTAKE_GATE_DESIGN.md §5의 헷갈림 표현.
CONFUSION_PHRASES = (
    "무슨 말", "무슨말", "뭔 말", "무슨 소리", "무슨소리",
    "모르겠", "뭐라고", "뭐라", "무슨 뜻", "무슨뜻",
    "이해가 안", "이해 안", "헷갈",
)
SUMMARY_STATE = "AWAIT_APPROVAL"


# ── 가림 (static/privacy.html: 평가 시 전화·주소 가림 약속) ──────────────

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}(?!\d)"  # 010-1234-5678, 010 1234 5678
    r"|(?<!\d)0\d{1,2}[-\s]\d{3,4}[-\s]\d{4}(?!\d)"  # 02-123-4567, 031-123-4567
    r"|(?<!\d)0\d{8,10}(?!\d)"  # 01012345678 (구분자 없음)
)
_KDIGITS = "공일이삼사오육칠팔구0-9"
_KDIGIT_RUN_RE = re.compile(f"[{_KDIGITS}][{_KDIGITS}\\s\\-~]{{7,}}[{_KDIGITS}]")
_REGION_RE = re.compile(r"[가-힣]{2,}(?:도|시)\s+[가-힣0-9]{1,}(?:시|군|구)")
_STREET_RE = re.compile(r"[가-힣0-9]{2,}(?:로|길)\s*\d+(?:-\d+)?(?:번지)?")
_BUNJI_RE = re.compile(r"[가-힣0-9]{1,}(?:동|읍|면|리)\s*\d+(?:-\d+)?번지")


def _mask_korean_digits(m: re.Match) -> str:
    run = m.group(0)
    stripped = re.sub(r"[\s\-~]", "", run)
    # 숫자(한글 포함) 9자리 이상이어야 전화번호로 본다. 날짜·가격 오탐 방지.
    if len(stripped) >= 9 and all(ch in _KDIGITS for ch in stripped):
        return "[전화]"
    return run


def mask_pii(text: str | None) -> str:
    """전화·주소·이메일을 가린다. 멱등하다(가린 결과에 다시 걸어도 안 바뀐다)."""
    if not text:
        return ""
    out = _EMAIL_RE.sub("[이메일]", text)
    out = _PHONE_RE.sub("[전화]", out)
    out = _KDIGIT_RUN_RE.sub(_mask_korean_digits, out)
    out = _REGION_RE.sub("[주소]", out)
    out = _STREET_RE.sub("[주소]", out)
    out = _BUNJI_RE.sub("[주소]", out)
    return out


# ── 작은 도구 ────────────────────────────────────────────────────────────

def _trace(turn: dict) -> dict:
    meta = turn.get("meta")
    return meta if isinstance(meta, dict) else {}


def _as_dt(ts) -> _dt.datetime | None:
    if ts is None:
        return None
    if isinstance(ts, _dt.datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=_dt.timezone.utc)
    if isinstance(ts, str):
        try:
            d = _dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return None
        return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)
    return None


def percentile(sorted_vals: list, p: float) -> float | None:
    """정렬된 값 목록의 p 백분위수(0~100). 비어 있으면 None."""
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    rank = (p / 100) * (len(sorted_vals) - 1)
    lo, hi = int(rank), min(int(rank) + 1, len(sorted_vals) - 1)
    frac = rank - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def _ms_stats(ms_list: list) -> tuple[float | None, float | None]:
    s = sorted(ms_list)
    return percentile(s, 50), percentile(s, 95)


def _repeat_runs(slots: list) -> list:
    """같은 칸이 연속 3회 이상 나온 구간의 칸 목록 (None은 제외, 구간당 1개)."""
    runs = []
    i = 0
    while i < len(slots):
        if slots[i] is None:
            i += 1
            continue
        j = i
        while j + 1 < len(slots) and slots[j + 1] == slots[i]:
            j += 1
        if j - i + 1 >= 3:
            runs.append(slots[i])
        i = j + 1
    return runs


# ── 세션 지표 ────────────────────────────────────────────────────────────

def session_metrics(session_id: str, turns: list, now: _dt.datetime | None = None) -> dict:
    """한 대화의 규칙 지표를 잰다. turns는 시간순이다."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    traces = [_trace(t) for t in turns]

    first_summary = next(
        (i for i, t in enumerate(turns) if t.get("state_after") == SUMMARY_STATE), None)
    reached = first_summary is not None

    next_slots = [tr.get("next_slot") for tr in traces]
    repeats = _repeat_runs(next_slots)

    extracted_lists = [tr.get("extracted") for tr in traces]
    empty_twice = sum(
        1 for a, b in zip(extracted_lists, extracted_lists[1:])
        if a == [] and b == [])

    confusion_hits, confusion_slots = [], []
    for i, t in enumerate(turns):
        if any(p in (t.get("user_text") or "") for p in CONFUSION_PHRASES):
            confusion_hits.append(i + 1)  # 1부터 세는 턴 번호
            asked = traces[i].get("asked_slot")
            if asked:
                confusion_slots.append(asked)

    missed = []
    for t, tr in zip(turns, traces):
        if not tr:  # 수집 단계 밖 턴(확정·견적 등)은 요구 후보로 보지 않는다
            continue
        if tr.get("answered_by_rule") or tr.get("skip"):
            continue
        if tr.get("extracted") == [] and tr.get("applied") == []:
            if len((t.get("user_text") or "").strip()) >= MISSED_MIN_LEN:
                missed.append(t.get("user_text") or "")

    rule_traced = [tr for tr in traces if "answered_by_rule" in tr]
    rule_answered = sum(1 for tr in rule_traced if tr.get("answered_by_rule"))
    extracts = [tr for tr in traces if tr.get("extract_ok") is not None]
    extract_failed = sum(1 for tr in extracts if not tr.get("extract_ok"))
    ms_list = [tr["extract_ms"] for tr in extracts
               if isinstance(tr.get("extract_ms"), (int, float))]
    p50, p95 = _ms_stats(ms_list)

    last_ts = _as_dt(turns[-1].get("ts")) if turns else None
    if reached or not turns:
        churned = False if turns else None
    elif last_ts is None:
        churned = None  # 시각을 몰라 판정 불가
    else:
        churned = (now - last_ts) >= CHURN_GAP

    return {
        "session_id": session_id,
        "n_turns": len(turns),
        "reached_summary": reached,
        "turns_to_summary": (first_summary + 1) if reached else None,
        "num_questions": sum(1 for s in next_slots if s is not None),
        "used_skip": any(bool(tr.get("skip")) for tr in traces),
        "rule_answered": rule_answered,
        "rule_traced": len(rule_traced),
        "rule_ratio": (rule_answered / len(rule_traced)) if rule_traced else None,
        "extract_total": len(extracts),
        "extract_failed": extract_failed,
        "extract_fail_rate": (extract_failed / len(extracts)) if extracts else None,
        "extract_ms": ms_list,
        "extract_p50_ms": p50,
        "extract_p95_ms": p95,
        "repeat_slots": repeats,
        "repeat_count": len(repeats),
        "empty_twice": empty_twice,
        "confusion_hits": confusion_hits,
        "confusion_slots": confusion_slots,
        "missed": missed,
        "churned": churned,
        "last_next_slot": next(s for s in reversed(next_slots) if s is not None) if any(
            s is not None for s in next_slots) else None,
    }


# ── 전체 집계 ────────────────────────────────────────────────────────────

def aggregate(metrics: list) -> dict:
    """세션 지표 목록을 전체 요약으로 묶는다."""
    n = len(metrics)
    reached = [m for m in metrics if m["reached_summary"]]
    unreached_known = [m for m in metrics if not m["reached_summary"] and m["churned"] is not None]
    churned = [m for m in unreached_known if m["churned"]]
    questions = [m["num_questions"] for m in metrics]
    to_summary = [m["turns_to_summary"] for m in reached if m["turns_to_summary"] is not None]
    all_ms = sorted(ms for m in metrics for ms in m.get("extract_ms", []))
    g50, g95 = _ms_stats(all_ms)

    rule_a = sum(m["rule_answered"] for m in metrics)
    rule_t = sum(m["rule_traced"] for m in metrics)
    ext_t = sum(m["extract_total"] for m in metrics)
    ext_f = sum(m["extract_failed"] for m in metrics)

    slot_stuck: dict[str, int] = {}
    slot_churn: dict[str, int] = {}

    def _bump(d: dict, slot) -> None:
        if slot:
            d[slot] = d.get(slot, 0) + 1

    for m in metrics:
        for s in m["repeat_slots"]:
            _bump(slot_stuck, s)
        for s in m["confusion_slots"]:
            _bump(slot_stuck, s)
        if m["empty_twice"]:
            _bump(slot_stuck, m["last_next_slot"])
        if m["churned"]:
            _bump(slot_churn, m["last_next_slot"])
    ranked = sorted(set(slot_stuck) | set(slot_churn),
                    key=lambda s: (-(slot_stuck.get(s, 0) + slot_churn.get(s, 0)), s))
    slot_rank = [{"slot": s, "stuck": slot_stuck.get(s, 0),
                  "churn_last": slot_churn.get(s, 0)} for s in ranked]

    return {
        "n_sessions": n,
        "n_reached": len(reached),
        "summary_rate": (len(reached) / n) if n else None,
        "n_churned": len(churned),
        "churn_rate": (len(churned) / len(unreached_known)) if unreached_known else None,
        "avg_questions": (sum(questions) / n) if n else None,
        "avg_turns_to_summary": (sum(to_summary) / len(to_summary)) if to_summary else None,
        "skip_sessions": sum(1 for m in metrics if m["used_skip"]),
        "rule_ratio": (rule_a / rule_t) if rule_t else None,
        "extract_total": ext_t,
        "extract_failed": ext_f,
        "extract_fail_rate": (ext_f / ext_t) if ext_t else None,
        "extract_p50_ms": g50,
        "extract_p95_ms": g95,
        "repeat_total": sum(m["repeat_count"] for m in metrics),
        "empty_twice_sessions": sum(1 for m in metrics if m["empty_twice"]),
        "confusion_total": sum(len(m["confusion_hits"]) for m in metrics),
        "missed_total": sum(len(m["missed"]) for m in metrics),
        "slot_rank": slot_rank,
    }
