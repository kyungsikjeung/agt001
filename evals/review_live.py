"""실제 사용자 대화 평가 보고서.

사용법::

    python -m evals.review_live [--days 7] [--limit 200] [--judge] [--out generated/evals/live-<날짜>.md]

- DB(chat_turns)에서 최근 N일 대화를 세션별로 읽는다(읽기 전용, SELECT만).
- ``--judge`` 면 가린 대화 기록을 AI 채점자에게 보내 1~5점 + 한 줄 이유를 받는다.
- 보고서는 ``generated/evals/`` (git에 안 올라감 — 실제 사용자 대화이므로 저장소에 쓰지 않는다)에
  마크다운 + 합계 JSON으로 함께 저장한다.

채점 LLM 함수는 ``build_report(..., judge_fn=...)`` 으로 주입한다. 시험은 가짜 채점자로만 한다.
"""

import argparse
import collections
import datetime as _dt
import json
from pathlib import Path

from evals import live_metrics as M

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = PROJECT_ROOT / "generated" / "evals"

JUDGE_SYSTEM = (
    "너는 소상공인 웹사이트 요구사항 대화의 평가자다. 아래는 개인정보를 가린 대화 기록이다.\n"
    "AI가 사장님에게 한 질문이 적절했는지, 사장님 말을 제대로 알아들었는지 평가한다.\n"
    "JSON만 출력한다. 스키마:\n"
    '{"q_ok": 1~5 질문이 적절했나, "heard": 1~5 사장님 말을 제대로 알아들었나, '
    '"missed": [사장님이 말했는데 카드·대답에 반영 안 된 요구 목록], '
    '"weird": [엉뚱한·맥락 안 맞는 질문 목록], "burden": 1~5 질문이 많거나 어려웠나(높을수록 부담), '
    '"fix": "다음에 고칠 점 1가지", "reason": "한 줄 이유"}'
)

JUDGE_KEYS = ("q_ok", "heard", "missed", "weird", "burden", "fix", "reason")


def default_judge_fn(transcript: str) -> dict:
    """기본 채점자 (app.llm.chat_json). 실제 NIM을 부르므로 시험에서는 쓰지 않는다."""
    from app import llm as _llm

    return json.loads(_llm.chat_json(JUDGE_SYSTEM, transcript))


def _clamp_score(v) -> int | None:
    try:
        iv = int(v)
    except (TypeError, ValueError):
        return None
    return min(5, max(1, iv))


def _str_list(v) -> list:
    if not isinstance(v, list):
        return []
    return [str(x)[:300] for x in v if str(x).strip()][:20]


def judge_session(transcript: str, judge_fn) -> dict:
    """한 대화를 채점한다. 실패해도 멈추지 않고 error로 남긴다."""
    try:
        raw = judge_fn(transcript)
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict):
            raise ValueError("채점 결과가 dict가 아님")
        return {
            "q_ok": _clamp_score(data.get("q_ok")),
            "heard": _clamp_score(data.get("heard")),
            "missed": _str_list(data.get("missed")),
            "weird": _str_list(data.get("weird")),
            "burden": _clamp_score(data.get("burden")),
            "fix": str(data.get("fix") or "")[:300],
            "reason": str(data.get("reason") or "")[:300],
        }
    except Exception as e:  # noqa: BLE001 — 한 대화 채점 실패가 전체를 망가뜨리면 안 된다
        return {"error": f"{type(e).__name__}: {e}"}


# ── DB 읽기 (읽기 전용) ──────────────────────────────────────────────────

def load_sessions(days: int = 7, limit: int = 200) -> dict:
    """최근 N일의 chat_turns를 세션별로 묶어 돌려준다. SELECT만 쓴다."""
    from app.db import session as _session
    from app.db import models as _models
    from sqlalchemy import func as _func

    cutoff = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=days)
    maker = _session.get_sessionmaker()
    with maker() as db:
        id_rows = (
            db.query(_models.ChatTurnRow.session_id)
            .filter(_models.ChatTurnRow.ts >= cutoff)
            .group_by(_models.ChatTurnRow.session_id)
            .order_by(_func.max(_models.ChatTurnRow.id).desc())
            .limit(limit)
            .all()
        )
        session_ids = [r[0] for r in id_rows]
        if not session_ids:
            return {}
        rows = (
            db.query(_models.ChatTurnRow)
            .filter(_models.ChatTurnRow.session_id.in_(session_ids),
                    _models.ChatTurnRow.ts >= cutoff)
            .order_by(_models.ChatTurnRow.session_id, _models.ChatTurnRow.id)
            .all()
        )
        turns = [{"session_id": r.session_id, "user_text": r.user_text, "ai_text": r.ai_text,
                  "state_before": r.state_before, "state_after": r.state_after,
                  "meta": r.meta, "ts": r.ts} for r in rows]
    # db 세션을 닫은 뒤이므로 여기서 묶는다.
    return group_rows(turns)


def group_rows(rows: list) -> dict:
    """행 목록(세션·시간순)을 세션별 턴 목록으로 묶는다. DB 없이 시험할 수 있게 분리."""
    sessions: dict[str, list] = {}
    for r in rows:
        sessions.setdefault(r["session_id"], []).append({
            "user_text": r.get("user_text", ""), "ai_text": r.get("ai_text", ""),
            "state_before": r.get("state_before", ""), "state_after": r.get("state_after", ""),
            "meta": r.get("meta"), "ts": r.get("ts")})
    return sessions


# ── 보고서 재료 ──────────────────────────────────────────────────────────

def transcript(turns: list, max_chars: int = 6000) -> str:
    """가린 대화 기록. 채점자에게 보내는 것도, 보고서 예시도 이것을 쓴다."""
    lines = []
    for i, t in enumerate(turns, 1):
        lines.append(f"[턴 {i}] 사장님: {M.mask_pii(t.get('user_text'))}")
        lines.append(f"[턴 {i}] AI: {M.mask_pii(t.get('ai_text'))}")
    out = "\n".join(lines)
    return out if len(out) <= max_chars else out[:max_chars] + "\n…(이하 생략)"


def _fmt(v, suffix: str = "") -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.1f}{suffix}" if abs(v) < 100 else f"{v:.0f}{suffix}"
    return f"{v}{suffix}"


def _pct_str(v) -> str:
    return "-" if v is None else f"{v * 100:.0f}%"


def build_report(sessions: dict, judge_fn=None, now: _dt.datetime | None = None,
                 date_str: str | None = None) -> tuple[str, dict]:
    """보고서 마크다운 + 합계 dict. sessions는 group_rows 결과. judge_fn이 None이면 채점 생략."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    date_str = date_str or now.date().isoformat()
    mets = {sid: M.session_metrics(sid, turns, now) for sid, turns in sessions.items()}
    agg = M.aggregate(list(mets.values()))

    judged: dict[str, dict] = {}
    if judge_fn is not None:
        for sid, turns in sessions.items():
            judged[sid] = judge_session(transcript(turns), judge_fn)
    ok_judged = {s: j for s, j in judged.items() if "error" not in j}

    def _avg(key: str):
        vals = [j[key] for j in ok_judged.values() if j.get(key) is not None]
        return (sum(vals) / len(vals)) if vals else None

    judge_summary = None
    if judge_fn is not None:
        dist = {k: collections.Counter(
            j[k] for j in ok_judged.values() if j.get(k) is not None) for k in ("q_ok", "heard", "burden")}
        missed_all = [m for j in ok_judged.values() for m in j.get("missed", [])]
        weird_all = [w for j in ok_judged.values() for w in j.get("weird", [])]
        fixes = collections.Counter(
            j["fix"].strip() for j in ok_judged.values() if j.get("fix", "").strip())
        judge_summary = {
            "n_judged": len(ok_judged), "n_errors": len(judged) - len(ok_judged),
            "avg_q_ok": _avg("q_ok"), "avg_heard": _avg("heard"), "avg_burden": _avg("burden"),
            "dist": {k: dict(sorted(v.items())) for k, v in dist.items()},
            "missed": missed_all[:50],
            "weird": weird_all[:50],
            "improvements": [{"fix": f, "count": c} for f, c in fixes.most_common(5)],
        }

    missed_masked = []
    for m in mets.values():
        missed_masked.extend(M.mask_pii(t) for t in m["missed"])
    missed_masked = missed_masked[:50]

    # 예시 3개: 막힘·이탈 / 요약 도달 / 요구 빠뜨림 순으로 고른다.
    def _pick(pred):
        return next((sid for sid, m in mets.items() if pred(sid, m)), None)

    example_ids = []
    for sid in (_pick(lambda s, m: m["churned"] or m["repeat_count"] or m["empty_twice"]),
                _pick(lambda s, m: m["reached_summary"] and s not in example_ids),
                _pick(lambda s, m: m["missed"] and s not in example_ids)):
        if sid and sid not in example_ids:
            example_ids.append(sid)
    for sid in mets:
        if len(example_ids) >= 3:
            break
        if sid not in example_ids:
            example_ids.append(sid)
    example_ids = example_ids[:3]
    examples = [{"session_id": sid, "transcript": transcript(sessions[sid], 1500),
                 "reached_summary": mets[sid]["reached_summary"],
                 "churned": mets[sid]["churned"]} for sid in example_ids]

    summary = {
        "date": date_str,
        "aggregate": agg,
        "judge": judge_summary,
        "missed_masked": missed_masked,
        "examples": examples,
    }

    # ── 마크다운 ──
    L = [f"# 실제 대화 평가 ({date_str})", "",
         f"- 대화 수: {agg['n_sessions']}, 요약 도달률: {_pct_str(agg['summary_rate'])}, "
         f"이탈률: {_pct_str(agg['churn_rate'])}, 평균 질문 수: {_fmt(agg['avg_questions'])}, "
         f"추출 실패율: {_pct_str(agg['extract_fail_rate'])} "
         f"({agg['extract_failed']}/{agg['extract_total']}), 추출 p95: {_fmt(agg['extract_p95_ms'], 'ms')}",
         "",
         "## 전체 요약", "",
         f"- 요약 도달: {agg['n_reached']}/{agg['n_sessions']} "
         f"- 이탈: {agg['n_churned']} - 건너뛰기 사용 대화: {agg['skip_sessions']}",
         f"- 요약까지 평균 턴: {_fmt(agg['avg_turns_to_summary'])} "
         f"- 규칙 답(버튼) 비율: {_pct_str(agg['rule_ratio'])} "
         f"- 추출 p50: {_fmt(agg['extract_p50_ms'], 'ms')}",
         f"- 같은 칸 3연속 반복: {agg['repeat_total']}건 "
         f"- 추출 빈 결과 2연속: {agg['empty_twice_sessions']}개 대화 "
         f"- 헷갈림 표현: {agg['confusion_total']}건 "
         f"- 카드 미반영 요구 후보: {agg['missed_total']}건",
         "",
         "## 막힘·이탈이 많은 질문 칸", ""]
    if agg["slot_rank"]:
        L.append("| 칸 | 막힘 | 마지막 칸에서 이탈 |")
        L.append("|---|---|---|")
        for r in agg["slot_rank"][:10]:
            L.append(f"| {r['slot']} | {r['stuck']} | {r['churn_last']} |")
    else:
        L.append("막힘·이탈 신호 없음.")
    L += [""]

    if judge_summary is not None:
        L += ["## AI 채점", "",
              f"- 채점 대화: {judge_summary['n_judged']} (실패 {judge_summary['n_errors']})",
              f"- 질문 적절: {_fmt(judge_summary['avg_q_ok'])} / 알아들음: {_fmt(judge_summary['avg_heard'])} "
              f"/ 부담: {_fmt(judge_summary['avg_burden'])} (1~5점)",
              f"- 점수 분포: {json.dumps(judge_summary['dist'], ensure_ascii=False)}",
              "",
              "## 빠뜨린 요구 모음 (가림 적용)", ""]
        all_missed = list(dict.fromkeys(judge_summary["missed"] + missed_masked))
        L += [f"- {M.mask_pii(m)}" for m in all_missed[:50]] or ["없음."]
        weird_lines = [f"- {M.mask_pii(w)}" for w in judge_summary["weird"][:20]] or ["없음."]
        L += ["",
              "## 엉뚱한 질문 모음", "",
              *weird_lines,
              "",
              "## 개선 제안 상위 5", ""]
        L += ([f"{i + 1}. {M.mask_pii(it['fix'])} ({it['count']}건)"
               for i, it in enumerate(judge_summary["improvements"])] or ["없음."])
        L += [""]
    else:
        L += ["## 빠뜨린 요구 후보 (규칙, 가림 적용)", "",
              *([f"- {m}" for m in missed_masked[:50]] or ["없음."]),
              "",
              "(AI 채점은 `--judge` 로 실행하면 이 자리에 들어간다.)",
              ""]

    L += ["## 대화 예시 3개 (가림 적용)", ""]
    for i, ex in enumerate(examples, 1):
        L += [f"### 예시 {i} (`{ex['session_id']}`, 요약 도달: {ex['reached_summary']}, 이탈: {ex['churned']})",
              "", ex["transcript"], ""]
    if not examples:
        L += ["대화 없음.", ""]
    return "\n".join(L), summary


# ── 실행 ─────────────────────────────────────────────────────────────────

def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="실제 사용자 대화 평가 보고서")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--judge", action="store_true")
    p.add_argument("--out", default=None)
    return p.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    today = _dt.datetime.now().date().isoformat()
    out_md = Path(args.out) if args.out else (DEFAULT_OUT_DIR / f"live-{today}.md")
    # 실제 사용자 대화이므로 작업 폴더 밖에는 쓰지 않는다.
    if PROJECT_ROOT not in out_md.resolve().parents and out_md.resolve() != PROJECT_ROOT:
        raise SystemExit(f"작업 폴더 밖에는 쓰지 않습니다: {out_md}")
    sessions = load_sessions(days=args.days, limit=args.limit)
    md, summary = build_report(sessions, judge_fn=default_judge_fn if args.judge else None)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text(md, encoding="utf-8")
    out_json = out_md.with_suffix(".json")
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    agg = summary["aggregate"]
    print(f"대화 {agg['n_sessions']}개, 요약 도달률 {_pct_str(agg['summary_rate'])}, "
          f"이탈률 {_pct_str(agg['churn_rate'])}")
    print(f"보고서: {out_md}\n합계: {out_json}")


if __name__ == "__main__":
    main()
