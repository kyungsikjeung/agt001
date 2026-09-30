"""S3 말로 고치기 평가 실행기.

사용법:
    .venv/bin/python evals/run_builder_say.py --check   # LLM 없이 파일 검사만
    .venv/bin/python evals/run_builder_say.py           # 실제 LLM으로 돌림 (Claude가 실행)

계약: docs/product/SAY_CONTRACT.md §2, §3, §4, §8.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

CASES_DEFAULT = Path(__file__).resolve().parent / "builder_say" / "cases.jsonl"
EVALS_DIR = Path(__file__).resolve().parent.parent / "docs" / "product" / "evals"

# 업종 → 청사진 파일 (계약 §8: 업종별 실제 구역 id 사용)
INDUSTRY_BLUEPRINT = {
    "cafe": "A-dinein",
    "restaurant": "A-dinein",
    "salon": "B-solo",
    "academy": "D",
    "workshop": "E",
    "pension": "C",
}

# §3 명령별 허용 칸 (op 키 제외)
ALLOWED_FIELDS = {
    "set_field": {"key", "value"},
    "item": {"name", "rename", "price", "note", "add", "remove"},
    "section": {"id", "action"},
    "notice": {"text", "popup", "off"},
    "style": {"text"},
    "variant": {"variant"},
    "feature": {"key"},
    "ask": {"question"},
}

SET_FIELD_KEYS = {"shop_name", "phone", "hours", "location", "detail", "contact_method"}  # PUT /card fields와 같은 칸 이름
SECTION_ACTIONS = {"add", "hide", "show", "up", "down"}
VARIANTS = {"v1", "v2", "v3"}
FEATURE_KEYS = {"stamps", "order"}


# ── 케이스 로딩 ──────────────────────────────────────────────

def load_cases(path: str | Path = CASES_DEFAULT) -> list[dict]:
    """cases.jsonl을 읽어 dict 목록으로 돌려준다."""
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
    return items


def blueprint_pool(name: str) -> set[str]:
    """청사진 3개 전략의 구역 id 모음."""
    path = (
        Path(__file__).resolve().parent.parent
        / "templates" / "blueprints" / f"{name}.json"
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    pool: set[str] = set()
    for strategy in data.get("strategies", []):
        for section in strategy.get("sections", []):
            if isinstance(section, dict) and section.get("id"):
                pool.add(section["id"])
    return pool


def check_op(op: dict, pool: set[str]) -> list[str]:
    """expect_ops 한 항목이 §3 이름·칸만 쓰는지 본다."""
    errors: list[str] = []
    if not isinstance(op, dict):
        return ["명령이 dict가 아님"]
    name = op.get("op")
    if name not in ALLOWED_FIELDS:
        return [f"모르는 명령: {name!r}"]
    extra = set(op) - {"op"} - ALLOWED_FIELDS[name]
    if extra:
        errors.append(f"{name}: 허용 밖 칸 {sorted(extra)}")
    if name == "set_field" and "key" in op and op["key"] not in SET_FIELD_KEYS:
        errors.append(f"set_field: 허용 밖 key {op['key']!r}")
    if name == "section":
        if "action" in op and op["action"] not in SECTION_ACTIONS:
            errors.append(f"section: 허용 밖 action {op['action']!r}")
        if "id" in op and op["id"] not in pool:
            errors.append(f"section: 풀에 없는 id {op['id']!r}")
    if name == "variant" and "variant" in op and op["variant"] not in VARIANTS:
        errors.append(f"variant: 허용 밖 값 {op['variant']!r}")
    if name == "feature" and "key" in op and op["key"] not in FEATURE_KEYS:
        errors.append(f"feature: 허용 밖 key {op['key']!r}")
    return errors


def check_cases(cases: list[dict]) -> list[str]:
    """--check 본문. LLM을 부르지 않는다."""
    errors: list[str] = []
    if len(cases) != 60:
        errors.append(f"케이스 수 {len(cases)}개 (60개여야 함)")
    counts = Counter(c.get("industry") for c in cases)
    for industry in INDUSTRY_BLUEPRINT:
        if counts.get(industry, 0) != 10:
            errors.append(f"{industry}: {counts.get(industry, 0)}개 (10개여야 함)")
    for industry in counts:
        if industry not in INDUSTRY_BLUEPRINT:
            errors.append(f"모르는 업종: {industry!r}")
    seen_ids: set[str] = set()
    pools = {ind: blueprint_pool(bp) for ind, bp in INDUSTRY_BLUEPRINT.items()}
    for case in cases:
        cid = case.get("id", "?")
        for key in ("id", "industry", "card", "sections", "addable",
                    "text", "expect_ops", "expect_source", "must_not"):
            if key not in case:
                errors.append(f"{cid}: 빠진 칸 {key}")
        if cid in seen_ids:
            errors.append(f"중복 id: {cid}")
        seen_ids.add(cid)
        industry = case.get("industry")
        pool = pools.get(industry, set())
        for sec in case.get("sections", []) + case.get("addable", []):
            if sec.get("id") not in pool:
                errors.append(f"{cid}: 풀에 없는 구역 id {sec.get('id')!r}")
        text = case.get("text", "")
        if not (1 <= len(text) <= 300):
            errors.append(f"{cid}: text 길이 {len(text)}자 (1~300자여야 함)")
        if case.get("expect_source") not in ("rule", "llm"):
            errors.append(f"{cid}: expect_source는 rule|llm이어야 함")
        for op in case.get("expect_ops", []):
            for e in check_op(op, pool):
                errors.append(f"{cid}: {e}")
        dumped = json.dumps(case.get("expect_ops", []), ensure_ascii=False)
        for bad in case.get("must_not", []):
            if bad and bad in dumped:
                errors.append(f"{cid}: must_not {bad!r}가 expect_ops에 있음")
    return errors


# ── 기본 모드 (실제 LLM, Claude가 실행) ──────────────────────

def build_card(case: dict) -> dict:
    """케이스에서 plan(card, text)에 넘길 작은 카드를 만든다."""
    card = dict(case.get("card", {}))
    card["sections"] = case.get("sections", [])
    card["addable"] = case.get("addable", [])
    return card


def _norm_value(value) -> str:
    if isinstance(value, bool):
        return str(value)
    return str(value)


# 명령 종류만 보는 명령: 되묻기 문장·디자인 느낌 글은 표현이 달라도 같은 뜻이다.
_KIND_ONLY = {"ask", "style"}


def _same(key: str, a, b) -> bool:
    """칸별 비교: 가격은 원 단위 숫자, 전화는 숫자만, 글은 공백 빼고. 나머지는 그대로."""
    if key == "price":
        from app.services.card_data import price_won
        return price_won(str(a or "")) == price_won(str(b or "")) and price_won(str(b or "")) is not None
    if key == "value" or key in ("text", "note", "name", "rename"):
        sa, sb = re.sub(r"\s+", "", str(a or "")), re.sub(r"\s+", "", str(b or ""))
        if re.fullmatch(r"[\d\-\s]{9,}", str(b or "")):
            return re.sub(r"\D", "", sa) == re.sub(r"\D", "", sb)
        return sa == sb
    return _norm_value(a) == _norm_value(b)


def ops_match(expect: list[dict], actual: list[dict]) -> int:
    """명령 일치 수 (순서 무시, 이름+주요 칸 비교, 칸별 정규화)."""
    remaining = [dict(a) for a in actual if isinstance(a, dict)]
    matched = 0
    for exp in expect:
        for i, act in enumerate(remaining):
            if act.get("op") != exp.get("op"):
                continue
            # 영업시간·위치는 사장님 말을 다듬어도 된다(SAY_CONTRACT §4): 숫자가 모두 같으면 맞다
            if (exp.get("op") == "set_field" and exp.get("key") in ("hours", "location")
                    and act.get("key") == exp.get("key")
                    and sorted(_digits(str(act.get("value") or ""))) == sorted(_digits(str(exp.get("value") or "")))):
                matched += 1
                remaining.pop(i)
                break
            if exp.get("op") in _KIND_ONLY or all(_same(k, act.get(k), v)
                                                  for k, v in exp.items() if k != "op"):
                matched += 1
                remaining.pop(i)
                break
    return matched


def _digits(s: str) -> list[str]:
    return re.findall(r"\d+", s.replace(",", ""))


def fabricated(text: str, ops: list[dict], must_not: list[str]) -> list[str]:
    """지어낸 값 찾기. must_not 문자열 또는 말에 없는 숫자."""
    found: list[str] = []
    dumped = json.dumps(ops, ensure_ascii=False)
    for bad in must_not:
        if bad and bad in dumped:
            found.append(bad)
    text_digits = set(_digits(text))
    for op in ops:
        if not isinstance(op, dict):
            continue
        for key, value in op.items():
            if key == "op" or not isinstance(value, str):
                continue
            for num in _digits(value):
                if num not in text_digits and len(num) >= 2:
                    found.append(f"{key}={value}")
                    break
    return found


def run_live(cases: list[dict], out: Path | None) -> int:
    """실제 builder_agent.plan으로 돌리고 표를 쓴다."""
    try:
        from app.services import builder_agent
    except Exception as e:
        print(f"builder_agent를 못 읽음 (S1 선행): {e}", file=sys.stderr)
        return 2
    rows: list[dict] = []
    for case in cases:
        card = build_card(case)
        started = time.monotonic()
        try:
            result = builder_agent.plan(card, case["text"])
        except Exception as e:  # LLM 실패·시간 초과는 되묻기로 친다
            result = {"ops": [], "source": "none", "rejected": [str(e)]}
        latency = time.monotonic() - started
        ops = result.get("ops", []) if isinstance(result, dict) else []
        source = result.get("source", "none") if isinstance(result, dict) else "none"
        expect = case.get("expect_ops", [])
        rows.append({
            "id": case["id"],
            "match": f"{ops_match(expect, ops)}/{len(expect)}",
            "fab": ",".join(fabricated(case["text"], ops, case.get("must_not", []))) or "-",
            "source": source,
            "latency": round(latency, 2),
        })
    total_expect = sum(len(c.get("expect_ops", [])) for c in cases)
    matched = sum(int(r["match"].split("/")[0]) for r in rows)
    rule_share = sum(1 for r in rows if r["source"] == "rule") / max(len(rows), 1)
    mean_latency = sum(r["latency"] for r in rows) / max(len(rows), 1)
    fab_total = sum(1 for r in rows if r["fab"] != "-")
    kst = timezone(timedelta(hours=9))
    stamp = datetime.now(kst).strftime("%Y-%m-%d")
    out = out or (EVALS_DIR / f"builder-say-{stamp}.md")
    lines = [
        f"# 말로 고치기 평가 ({stamp} KST)",
        "",
        f"- 명령 일치율: {matched}/{total_expect}",
        f"- 지어낸 값: {fab_total}건",
        f"- 규칙 비율: {rule_share:.1%}",
        f"- 평균 지연: {mean_latency:.2f}초",
        "",
        "| id | 일치 | 지어낸 값 | 출처 | 지연(초) |",
        "|---|---|---|---|---|",
    ]
    lines += [f"| {r['id']} | {r['match']} | {r['fab']} | {r['source']} | {r['latency']} |"
              for r in rows]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"명령 일치율: {matched}/{total_expect}, 지어낸 값: {fab_total}건, "
          f"규칙 {rule_share:.1%}, 평균 {mean_latency:.2f}초 → {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="말로 고치기 평가 (S3)")
    parser.add_argument("--check", action="store_true",
                        help="LLM 없이 케이스 파일만 검사한다")
    parser.add_argument("--cases", default=str(CASES_DEFAULT))
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    try:
        cases = load_cases(args.cases)
    except (OSError, ValueError) as e:
        print(f"검사 실패: {e}", file=sys.stderr)
        return 1
    if args.check:
        errors = check_cases(cases)
        if errors:
            print(f"검사 실패 {len(errors)}건:", file=sys.stderr)
            for e in errors:
                print(f"- {e}", file=sys.stderr)
            return 1
        counts = Counter(c["industry"] for c in cases)
        print(f"검사 통과: {len(cases)}개 " +
              ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))
        return 0
    return run_live(cases, Path(args.out) if args.out else None)


if __name__ == "__main__":
    raise SystemExit(main())
