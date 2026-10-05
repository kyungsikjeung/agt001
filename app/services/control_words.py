"""제어 말 표 (app/data/control_words.json): '시안 먼저'·'알아서'·'나중에'처럼 칸 값이 아닌 진행 말.

표 한 줄 = {id, phrases, match('exact'|'contains'), meaning, control?}.
phrases는 norm()으로 정규화해서 비교한다. control은 추출기가 칸 값으로 돌려줘도 버리는 말(정규화 후 일치)이다.
"""
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Optional

_PATH = Path(__file__).resolve().parents[1] / "data" / "control_words.json"

# classify 우선순위: 엔진 turn()이 보는 순서와 같다.
# 건너뛰기(부분일치) → '알아서'만(질문 대기 중이면 건너뛰기) → 직접 입력 → 다시 묻기
# → 모름 → 문장 속 '알아서'(그 칸만) → 나중에 → 없음.
ORDER = ("skip", "let_ai_skip", "type_it", "repeat", "dontknow", "let_ai_slot", "later", "none")


def norm(s: str) -> str:
    """공백·문장부호·이모지 제거 + 소문자 + NFKC (B-6 비교용). 한글·영숫자만 남긴다."""
    return re.sub(r"[^가-힣a-z0-9]", "", unicodedata.normalize("NFKC", (s or "").lower()))


@lru_cache(maxsize=1)
def table() -> dict:
    rows = json.loads(_PATH.read_text(encoding="utf-8"))
    return {r["id"]: r for r in rows}


@lru_cache(maxsize=None)
def norms(id: str) -> frozenset:
    return frozenset(norm(p) for p in table()[id]["phrases"])


@lru_cache(maxsize=1)
def control_norms() -> frozenset:
    """추출기가 칸 값으로 돌려주면 버릴 진행 말 (엔진 _CONTROL_NORMS)."""
    return frozenset(norm(p) for r in table().values() for p in r.get("control", ()))


def matches(id: str, text: str) -> bool:
    n = norm(text)
    if not n:
        return False
    if table()[id]["match"] == "exact":
        return n in norms(id)
    return any(p in n for p in norms(id))


def classify(text: str) -> Optional[str]:
    """제어 말이면 그 id(ORDER 순서로 먼저 맞는 것), 아니면 None.
    말만 본다: 질문 대기 여부('알아서'만 → 건너뛰기, 다시 묻기 등)는 엔진이 따로 본다."""
    return next((i for i in ORDER if matches(i, text)), None)
