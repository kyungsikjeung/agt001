"""처음 보는 업종 원형 판정 평가 (G2, LLM·DB 불필요).

evals/archetype_cases.json을 읽어 규칙 판정(business_type으로 만든 카드의
archetype.of)으로 맞힌 비율과 틀린 목록을 출력한다.
--llm이면 archetype.judge도 돌려 비교한다 (키가 필요하므로 Claude가 돌린다).

사용법: .venv/bin/python scripts/archetype_eval.py [--llm] [evals/archetype_cases_llm.json]
(_llm 목록은 낱말표에 없는 업종 30개: 규칙 판정은 낮은 게 정상, --llm 결과를 본다)
규칙 판정 80% 미만이면 exit 1.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import archetype  # noqa: E402
from app.services import prd_engine as E  # noqa: E402
from app.services import prd_schema as S  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_FILE = next((a for a in sys.argv[1:] if a.endswith(".json")), "evals/archetype_cases.json")
CASES = json.loads((_ROOT / _FILE).read_text(encoding="utf-8"))


def rule_of(business_type: str) -> str:
    """업종 말 → 규칙 판정 원형."""
    card = E.new_card()
    E._put(card, "business_type", business_type, S.FILLED, 1)
    return archetype.of(card)[0]


def main() -> int:
    use_llm = "--llm" in sys.argv
    hits, misses = 0, []
    llm_hits, llm_misses = 0, []
    for case in CASES:
        got = rule_of(case["business_type"])
        if got == case["expect"]:
            hits += 1
        else:
            misses.append((case["business_type"], case["expect"], got))
        if use_llm:
            card = E.new_card()
            E._put(card, "business_type", case["business_type"], S.FILLED, 1)
            if case.get("offerings"):
                E._put(card, "offerings", case["offerings"], S.FILLED, 1)
            judged = archetype.judge(card)
            final = archetype.of(card)[0]
            if final == case["expect"]:
                llm_hits += 1
            else:
                llm_misses.append((case["business_type"], case["expect"], final, judged))
    total = len(CASES)
    rate = hits / total if total else 0
    print(f"rule: {hits}/{total} ({rate:.1%})")
    for bt, want, got in misses:
        print(f"  miss rule: {bt} expect={want} got={got}")
    if use_llm:
        lrate = llm_hits / total if total else 0
        print(f"llm: {llm_hits}/{total} ({lrate:.1%})")
        for bt, want, got, judged in llm_misses:
            print(f"  miss llm: {bt} expect={want} got={got} judged={judged}")
    return 0 if rate >= 0.8 else 1


if __name__ == "__main__":
    raise SystemExit(main())
