"""WP P-1d: 요구사항 추출 평가 실행기 (T2).

사용법:
    python -m evals.run_extraction [--limit N] [--out docs/product/evals/extraction-<날짜>.md]

흐름(케이스마다):
    extract(text, last_question) -> apply_updates(new_card(), ...) 규칙 통과 값만
    -> evals/extraction/README.md 채점 규칙으로 칸별 일치·must_not 위반 판정.

주입 설계 (openai 불필요):
    - 이 모듈은 import 시점에 ``app.llm`` / ``app.services.prd_engine`` 을
      import 하지 않는다 (``app.llm`` 은 ``openai`` 패키지를 요구한다).
    - 실제 실행에서만 ``default_extract`` 안에서 ``prd_engine`` 을 lazy import
      하므로, 실제 AI 호출은 Claude가 직접 실행할 때만 일어난다.
    - 단위시험에서는 가짜 ``extract_fn(text, last_question)`` 을 넘긴다.
      즉 "llm 함수를 인자로 받게" 하는 요구는 ``extract_fn`` 주입으로
      만족한다. 실제 NVIDIA/NIM 호출은 이 모듈에서 절대 하지 않는다.

채점 규칙 (README 그대로):
    - 칸별 일치: 기대 값이 추출 값에 포함되면 일치 (부분 문자열 포함).
      기대 값이 리스트면 항목마다 각각 판정한다.
    - must_not 칸이 하나라도 추출되면 그 케이스는 실패.
    - 빈 기대(expect: {}): 추출이 비어 있어야 통과.
    - 사실 칸(phone, hours, location, price)은 근거 없는 값을 버린 것으로
      친다 (prd_engine.grounded 와 동일한 로컬 규칙으로 필터링한 뒤 판정.
      실제 실행에서는 진짜 prd_engine.apply_updates 를 거쳐 같은 결과가 된다).

합격선: 칸 정확도 90% 이상, 지어낸 사실(must_not 위반) 0건.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

# prd_schema 는 표준 라이브러리만 쓰므로 안전하게 import 한다.
# (prd_engine / app.llm 은 openai 가 필요해서 함수 안에서만 lazy import.)
try:
    from app.services import prd_schema as _SCHEMA
except Exception:  # pragma: no cover - import 실패 시 폴백
    _SCHEMA = None

if _SCHEMA is not None:
    FACT_SLOTS = set(_SCHEMA.FACT_SLOTS)
else:  # pragma: no cover
    FACT_SLOTS = {"phone", "hours", "location", "price"}

CASES_DEFAULT = Path(__file__).resolve().parent / "extraction" / "cases.jsonl"

PASS_SLOT_ACCURACY = 0.90
PASS_MUST_NOT = 0


# ── 케이스 로딩 ──────────────────────────────────────────────────

def load_cases(path: str | Path = CASES_DEFAULT, limit: int | None = None) -> list[dict]:
    """cases.jsonl 을 읽어 dict 목록으로 돌려준다."""
    items: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{lineno}: JSON 오류: {e}") from e
    if limit is not None:
        items = items[:limit]
    return items


# ── grounded 로컬 규칙 (prd_engine.grounded 과 동일) ─────────────

def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def local_grounded(slot: str, value: str, text: str) -> bool:
    """사실 칸 값이 메시지에 근거가 있는지. prd_engine.grounded 와 같은 규칙."""
    if slot not in FACT_SLOTS:
        return True
    d = _digits(value)
    if d:
        return d in _digits(text)
    words = [w for w in re.split(r"[\s,·/]+", value) if len(w) >= 2]
    return bool(words) and any(w in text for w in words)


# ── 추출값 -> 실제값 dict ────────────────────────────────────────

def _as_str_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None and str(v) != ""]
    s = str(value)
    return [s] if s != "" else []


def actual_from_updates(updates: list[dict], text: str) -> dict[str, list[str]]:
    """가짜 추출기용: grounded 필터 + 슬롯별 값 모으기.

    근거 없는 사실 칸 값은 버려진 것으로 친다 (README 규칙).
    """
    actual: dict[str, list[str]] = {}
    for u in updates or []:
        if not isinstance(u, dict):
            continue
        slot, value = u.get("slot"), u.get("value")
        if not isinstance(slot, str) or not isinstance(value, str):
            continue
        value = value.strip()
        if not value:
            continue
        if not local_grounded(slot, value, text):
            continue
        if value not in actual.setdefault(slot, []):
            actual[slot].append(value)
    return actual


def actual_from_card(card: dict) -> dict[str, list[str]]:
    """실제 prd_engine 카드에서 슬롯별 값 목록을 뽑는다."""
    actual: dict[str, list[str]] = {}
    for key, slot in (card.get("slots") or {}).items():
        vals = _as_str_list(slot.get("value"))
        if vals:
            actual[key] = vals
    return actual


# ── 채점 (순수 함수: 외부 의존 없음) ────────────────────────────

def score_case(case: dict, actual: dict[str, list[str]]) -> dict:
    """한 케이스 판정. README 채점 규칙 그대로.

    Returns:
        dict(passed, slot_results, matched, expected_total,
             must_not_violations, empty_expect, reason)
    """
    expect: dict = case.get("expect") or {}
    must_not: list = list(case.get("must_not") or [])

    slot_results: list[dict] = []
    matched = 0
    expected_total = 0
    for slot, exp_val in expect.items():
        for ev in _as_str_list(exp_val):
            expected_total += 1
            got = actual.get(slot, [])
            # 기대 값이 추출 값에 포함되면 일치 (부분 문자열 포함)
            hit = any(ev in av for av in got)
            matched += 1 if hit else 0
            slot_results.append({"slot": slot, "expected": ev, "matched": hit, "actual": list(got)})

    violations = [s for s in must_not if actual.get(s)]
    empty_expect = not expect
    if empty_expect:
        passed = (len(actual) == 0)
        reason = "ok" if passed else "empty-expect-violated"
    else:
        passed = (matched == expected_total) and not violations
        if passed:
            reason = "ok"
        elif violations:
            reason = "must-not-violated"
        else:
            reason = "slot-mismatch"
    return {
        "passed": passed,
        "slot_results": slot_results,
        "matched": matched,
        "expected_total": expected_total,
        "must_not_violations": violations,
        "empty_expect": empty_expect,
        "reason": reason,
    }


# ── 추출 (주입 가능; 기본은 실제 prd_engine.extract) ────────────

def default_extract(text: str, last_question: str | None) -> list[dict]:
    """실제 추출. 함수 안에서만 prd_engine 을 import (openai 지연 로딩)."""
    from app.services import prd_engine  # 지연 import: 시험 때는 불러오지 않는다

    return prd_engine.extract(text, last_question)


def run_one_case(
    case: dict,
    extract_fn=None,
    *,
    use_engine_apply: bool = True,
) -> dict:
    """한 케이스 실행: 추출 -> 규칙 적용 -> 채점. 시간 측정 포함.

    Args:
        case: cases.jsonl 한 줄.
        extract_fn: ``(text, last_question) -> [{slot, value}]``.
            None 이면 실제 ``prd_engine.extract`` 를 쓴다 (실제 AI 호출!).
        use_engine_apply: True 이고 실제 prd_engine 을 import 할 수 있으면
            진짜 ``new_card/apply_updates`` 를 거친다. 가짜 추출기로 시험할 때는
            False 로 두면 로컬 규칙만으로 판정한다 (openai 불필요).
    """
    fn = extract_fn or default_extract
    text = case.get("text", "")
    last_q = case.get("last_question")

    started = time.perf_counter()
    updates = fn(text, last_q)
    actual: dict[str, list[str]] | None = None
    if use_engine_apply:
        try:
            from app.services import prd_engine  # lazy

            card = prd_engine.new_card()
            prd_engine.apply_updates(card, updates or [], text)
            actual = actual_from_card(card)
        except Exception:
            # 실제 엔진 사용 불가(openai 미설치 등) → 로컬 규칙으로 폴백
            actual = actual_from_updates(updates or [], text)
    else:
        actual = actual_from_updates(updates or [], text)
    elapsed = time.perf_counter() - started

    scored = score_case(case, actual)
    return {
        "id": case.get("id"),
        "industry": case.get("industry"),
        "note": case.get("note", ""),
        "expect": case.get("expect") or {},
        "must_not": list(case.get("must_not") or []),
        "actual": actual,
        "updates_raw": list(updates or []),
        "elapsed_sec": elapsed,
        **scored,
    }


def run_all(
    cases: list[dict],
    extract_fn=None,
    *,
    use_engine_apply: bool = True,
) -> dict:
    """전체 케이스 실행 + 집계."""
    case_results = [run_one_case(c, extract_fn, use_engine_apply=use_engine_apply) for c in cases]

    total_expected = sum(r["expected_total"] for r in case_results)
    total_matched = sum(r["matched"] for r in case_results)
    slot_accuracy = (total_matched / total_expected) if total_expected else 1.0
    passed_cases = sum(1 for r in case_results if r["passed"])
    must_not_cases = sum(1 for r in case_results if r["must_not_violations"])
    must_not_slots = sum(len(r["must_not_violations"]) for r in case_results)

    per_slot: dict[str, dict] = {}
    for r in case_results:
        for s in r["slot_results"]:
            agg = per_slot.setdefault(s["slot"], {"expected": 0, "matched": 0})
            agg["expected"] += 1
            agg["matched"] += 1 if s["matched"] else 0
    for agg in per_slot.values():
        agg["accuracy"] = (agg["matched"] / agg["expected"]) if agg["expected"] else 1.0

    per_industry: dict[str, dict] = {}
    for r in case_results:
        agg = per_industry.setdefault(
            r["industry"], {"cases": 0, "passed": 0, "expected": 0, "matched": 0, "violations": 0}
        )
        agg["cases"] += 1
        agg["passed"] += 1 if r["passed"] else 0
        agg["expected"] += r["expected_total"]
        agg["matched"] += r["matched"]
        agg["violations"] += len(r["must_not_violations"])
    for agg in per_industry.values():
        agg["accuracy"] = (agg["matched"] / agg["expected"]) if agg["expected"] else 1.0
        agg["pass_rate"] = (agg["passed"] / agg["cases"]) if agg["cases"] else 1.0

    elapsed = [r["elapsed_sec"] for r in case_results]
    avg_t = sum(elapsed) / len(elapsed) if elapsed else 0.0
    max_t = max(elapsed) if elapsed else 0.0

    verdict = (slot_accuracy >= PASS_SLOT_ACCURACY) and (must_not_slots == PASS_MUST_NOT)
    return {
        "total_cases": len(case_results),
        "passed_cases": passed_cases,
        "case_pass_rate": (passed_cases / len(case_results)) if case_results else 1.0,
        "total_expected": total_expected,
        "total_matched": total_matched,
        "slot_accuracy": slot_accuracy,
        "must_not_cases": must_not_cases,
        "must_not_slots": must_not_slots,
        "per_slot": per_slot,
        "per_industry": per_industry,
        "avg_sec": avg_t,
        "max_sec": max_t,
        "verdict": verdict,
        "case_results": case_results,
    }


# ── 마크다운 리포트 ────────────────────────────────────────────

def render_markdown(summary: dict, title_date: str | None = None) -> str:
    day = title_date or date.today().isoformat()
    lines: list[str] = []
    lines.append(f"# T2 추출 평가 결과 ({day})")
    lines.append("")
    verdict = "합격" if summary["verdict"] else "불합격"
    lines.append("## 요약")
    lines.append("")
    lines.append(f"- 판정: **{verdict}**")
    lines.append(
        f"- 칸 정확도: **{summary['slot_accuracy']:.1%}** "
        f"({summary['total_matched']}/{summary['total_expected']}) — 합격선 90% 이상"
    )
    lines.append(
        f"- 케이스 통과율: {summary['case_pass_rate']:.1%} "
        f"({summary['passed_cases']}/{summary['total_cases']})"
    )
    lines.append(
        f"- must_not 위반(지어낸 사실): **{summary['must_not_slots']}건** "
        f"({summary['must_not_cases']}개 케이스) — 0이어야 합격"
    )
    lines.append(f"- 평균 응답 시간: {summary['avg_sec']:.3f}s, 최대: {summary['max_sec']:.3f}s")
    lines.append("")

    lines.append("## 칸별 정확도")
    lines.append("")
    lines.append("| 칸 | 일치/기대 | 정확도 |")
    lines.append("|---|---|---|")
    for slot in sorted(summary["per_slot"]):
        agg = summary["per_slot"][slot]
        lines.append(f"| {slot} | {agg['matched']}/{agg['expected']} | {agg['accuracy']:.1%} |")
    if not summary["per_slot"]:
        lines.append("| (없음) | 0/0 | - |")
    lines.append("")

    lines.append("## 업종별")
    lines.append("")
    lines.append("| 업종 | 케이스 통과 | 칸 정확도 | must_not 위반 |")
    lines.append("|---|---|---|---|")
    for ind in sorted(summary["per_industry"]):
        agg = summary["per_industry"][ind]
        lines.append(
            f"| {ind} | {agg['passed']}/{agg['cases']} "
            f"({agg['pass_rate']:.0%}) | {agg['matched']}/{agg['expected']} "
            f"({agg['accuracy']:.1%}) | {agg['violations']} |"
        )
    lines.append("")

    lines.append("## 실패 사례")
    lines.append("")
    failed = [r for r in summary["case_results"] if not r["passed"]]
    if not failed:
        lines.append("없음 (전원 통과).")
    else:
        lines.append("| id | 업종 | 사유 | 기대 | 실제 |")
        lines.append("|---|---|---|---|---|")
        for r in failed:
            exp = json.dumps(r["expect"], ensure_ascii=False)
            act = json.dumps(r["actual"], ensure_ascii=False)
            lines.append(f"| {r['id']} | {r['industry']} | {r['reason']} | `{exp}` | `{act}` |")
        lines.append("")
        for r in failed:
            lines.append(f"- {r['id']}: {r['note']}")
    lines.append("")
    lines.append("## 응답 시간")
    lines.append("")
    lines.append(f"- 평균: {summary['avg_sec']:.3f}s, 최대: {summary['max_sec']:.3f}s")
    lines.append("")
    return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="T2 요구사항 추출 평가 실행기 (WP P-1d)")
    p.add_argument("--limit", type=int, default=None, help="앞에서 N개 케이스만 실행")
    p.add_argument(
        "--out",
        type=str,
        default=None,
        help="결과 markdown 저장 경로 (예: docs/product/evals/extraction-2026-09-26.md)",
    )
    p.add_argument(
        "--cases",
        type=str,
        default=str(CASES_DEFAULT),
        help="cases.jsonl 경로 (기본: evals/extraction/cases.jsonl)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = load_cases(args.cases, limit=args.limit)
    summary = run_all(cases)  # 기본: 실제 prd_engine.extract (실제 AI 호출!)
    md = render_markdown(summary)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md, encoding="utf-8")
        print(f"{summary['passed_cases']}/{summary['total_cases']} 통과, "
              f"칸 정확도 {summary['slot_accuracy']:.1%}, "
              f"must_not {summary['must_not_slots']}건 -> {args.out}")
    else:
        print(md)
    return 0 if summary["verdict"] else 1


if __name__ == "__main__":
    sys.exit(main())
