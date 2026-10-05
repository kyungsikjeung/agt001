"""막힘 지표 (UX_GAP_PLAN Q4): 사장님이 어디서 멈추는지 매일 숫자로 본다.

대화 턴(chat_turns)의 엔진 판단(meta)과 유입 기록(funnel_events)만 읽는다. 내보내는 것은 숫자와 칸 키·칸 이름뿐,
사장님 말 원문은 넣지 않는다. DB 바꾸기·LLM 호출 없음.
"""
import datetime

from sqlalchemy import select

from app.db.models import ChatTurnRow, FunnelEventRow
from app.db.session import get_sessionmaker
from app.services import prd_engine as E
from app.services import prd_schema as S
from evals import live_metrics as M

DROPOFF_AFTER = datetime.timedelta(hours=24)  # 마지막 턴 뒤 이만큼 조용하면 이탈
LET_AI_MIN_ASKED = 3  # 이만큼 물은 칸만 '알아서' 비율을 본다
TOP = 5
# 받기(요약 전) 단계를 거친 대화만 본다. 빌더 방은 처음부터 DONE이라 요약 전 이탈로 잘못 잡힌다.
INTAKE_STATES = ("GREETING", "GATHERING", "AWAIT_APPROVAL")
# 아침 보고 길이. 계약은 700자 이하지만 ops_alert.send가 500자에서 자르므로 그 안에 맞춘다.
MORNING_MAX = 500


def label(slot: str) -> str:
    """보고는 여러 업종을 묶으니 업종별 이름(label_for) 대신 공통 이름."""
    return S.SLOTS[slot].label if slot in S.SLOTS else slot


def _skip_turn(text: str, tr: dict) -> bool:
    """'다시요' 같은 되묻기·금지 요청·'직접 입력' 글·방 멤버의 말은 사장님이 질문에 한 답이 아니다."""
    n = E._norm(text)
    return bool(not n or n == E._norm(S.TYPE_IT) or tr.get("repeat") or tr.get("blocked") or tr.get("member"))


def _repeat_twice(traces: list):
    """앞 턴에 물은 질문(칸·종류)을 다음 턴에 또 묻는 일이 두 턴 이어졌으면 그 칸. 같은 칸의 덧붙임 질문은 다른 질문이다."""
    prev = None
    for tr in traces:
        if not tr:
            continue
        s = tr.get("asked_slot")
        hit = s if s and tr.get("next_slot") == s and tr.get("next_kind") == tr.get("asked_kind") else None
        if hit and hit == prev:
            return hit
        prev = hit
    return None


def _load(since: datetime.datetime) -> tuple[dict, list]:
    """창 안에 턴이 하나라도 있는 대화의 모든 턴(요약 도달을 창 밖까지 보려고), 공개 관련 기록."""
    with get_sessionmaker()() as db:
        sids = db.scalars(select(ChatTurnRow.session_id).where(ChatTurnRow.ts >= since).distinct()).all()
        # ponytail: 대화 수천 개면 IN 목록이 커진다. 그때 창 기준 조인으로 바꾼다.
        rows = db.scalars(select(ChatTurnRow).where(ChatTurnRow.session_id.in_(sids))
                          .order_by(ChatTurnRow.session_id, ChatTurnRow.id)).all() if sids else []
        events = db.execute(select(FunnelEventRow.event, FunnelEventRow.ts, FunnelEventRow.props)
                            .where(FunnelEventRow.ts >= since,
                                   FunnelEventRow.event.in_(("publish_need_login", "site_published")))
                            .order_by(FunnelEventRow.id)).all()
    turns: dict = {}
    for r in rows:
        turns.setdefault(r.session_id, []).append(
            {"user_text": r.user_text or "", "state_before": r.state_before or "", "state_after": r.state_after or "", "meta": r.meta, "ts": r.ts})
    return turns, events


def _login_loops(events) -> int:
    """로그인 안내를 2번 이상 받고 그 뒤로 공개하지 못한 가게 수."""
    need: dict = {}
    published: dict = {}
    for event, ts, props in events:
        site = (props or {}).get("site")
        if not site:
            continue
        if event == "publish_need_login":
            need.setdefault(site, []).append(ts)
        else:
            published[site] = max(ts, published.get(site, ts))
    return sum(1 for site, ts_list in need.items()
               if len(ts_list) >= 2 and not (site in published and published[site] > max(ts_list)))


def report(days: int = 7, now: datetime.datetime | None = None) -> dict:
    """최근 days일 막힘 지표. 숫자·칸 키·칸 이름만 담는다."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    days = max(1, min(days, 90))
    since = now - datetime.timedelta(days=days)
    turns, events = _load(since)
    turns = {sid: ts for sid, ts in turns.items()
             if any(t["state_before"] in INTAKE_STATES or t["state_after"] in INTAKE_STATES for t in ts)}

    reached, to_summary, dropoff = 0, [], {}
    repeat_slots: dict = {}
    asked: dict = {}
    let_ai: dict = {}
    for sid, ts in turns.items():
        m = M.session_metrics(sid, ts, now)
        traces = [t["meta"] if isinstance(t["meta"], dict) else {} for t in ts]
        if m["reached_summary"]:
            reached += 1
            to_summary.append(m["turns_to_summary"])
        else:
            last = M._as_dt(ts[-1]["ts"])
            if last is not None and now - last >= DROPOFF_AFTER:
                n_q = max((tr.get("asked") or 0 for tr in traces), default=0)
                dropoff[n_q] = dropoff.get(n_q, 0) + 1
        # 턴별 숫자는 창 안의 답만 센다(요약 도달은 위에서 대화 전체로 본다)
        answers = [(t, tr) for t, tr in zip(ts, traces)
                   if (M._as_dt(t["ts"]) or now) >= since and not _skip_turn(t["user_text"], tr)]
        slot = _repeat_twice([tr for _, tr in answers])
        if slot:
            repeat_slots[slot] = repeat_slots.get(slot, 0) + 1
        for t, tr in answers:
            s = tr.get("asked_slot")
            if not s or tr.get("asked_kind") != "single":
                continue
            n = E._norm(t["user_text"])
            asked[s] = asked.get(s, 0) + 1
            if E._is_let_ai_norm(n) or E._is_dontknow_norm(n):
                let_ai[s] = let_ai.get(s, 0) + 1

    rates = [{"slot": s, "label": label(s), "asked": a, "let_ai": let_ai.get(s, 0), "rate": let_ai.get(s, 0) / a}
             for s, a in asked.items() if a >= LET_AI_MIN_ASKED]
    rates.sort(key=lambda r: (-r["rate"], -r["asked"], r["slot"]))
    to_summary.sort()
    return {
        "days": days,
        "sessions": len(turns),
        "reached_summary": reached,
        "repeat_twice": {"sessions": sum(repeat_slots.values()),
                         "top": [{"slot": s, "label": label(s), "sessions": n}
                                 for s, n in sorted(repeat_slots.items(), key=lambda x: (-x[1], x[0]))[:TOP]]},
        "let_ai_by_slot": rates[:TOP],
        "dropoff": dict(sorted(dropoff.items())),
        "publish_login_loops": _login_loops(events),
        "turns_to_summary": {k: None if v is None else round(v, 1)
                             for k, v in (("p50", M.percentile(to_summary, 50)), ("p90", M.percentile(to_summary, 90)))},
    }


def _n(x: float) -> str:
    return f"{x:g}" if x == int(x) else f"{x:.1f}"


def morning_text(rep: dict) -> str:
    """텔레그램 아침 보고 한 통. 0인 줄은 뺀다."""
    lines = [f"[아침 보고] 지난 {rep['days']}일"]
    n = rep["sessions"]
    if not n:
        return lines[0] + "\n대화가 없었어요."
    r = rep["reached_summary"]
    lines.append(f"대화 {n}건" + (f" · 요약까지 {r}건 ({round(r * 100 / n)}%)" if r else ""))
    tts = rep["turns_to_summary"]
    if tts["p50"] is not None:
        lines.append(f"요약까지 턴: 보통 {_n(tts['p50'])} · 느린 쪽(90%) {_n(tts['p90'])}")
    rt = rep["repeat_twice"]
    if rt["sessions"]:
        lines.append(f"같은 질문 두 번 되풀이: {rt['sessions']}건 ("
                     + ", ".join(f"{x['label']} {x['sessions']}" for x in rt["top"][:3]) + ")")
    la = [x for x in rep["let_ai_by_slot"] if x["let_ai"]]
    if la:
        lines.append("'알아서'·'모르겠어요' 많은 칸: "
                     + ", ".join(f"{x['label']} {round(x['rate'] * 100)}%({x['let_ai']}/{x['asked']})" for x in la[:3]))
    if rep["publish_login_loops"]:
        lines.append(f"로그인에 막혀 공개 못 한 가게: {rep['publish_login_loops']}곳")
    if rep["dropoff"]:
        # 많은 칸 5개만 (긴 분포 한 줄이 넘쳐 다른 줄까지 잘리지 않게)
        top = sorted(sorted(rep["dropoff"].items(), key=lambda x: -x[1])[:TOP])
        lines.append("요약 전 멈춤(24시간 조용): " + ", ".join(f"질문 {q}개에서 {c}건" for q, c in top)
                     + (" …" if len(rep["dropoff"]) > TOP else ""))
    while len(lines) > 1 and len("\n".join(lines)) > MORNING_MAX:
        lines.pop()
    return "\n".join(lines)[:MORNING_MAX]
