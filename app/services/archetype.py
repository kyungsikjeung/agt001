"""손님 동선 원형 판정과 청사진 불러오기 (BUILD_W1_W2 §1.2·§1.3).

원형은 업종이 아니라 손님이 움직이는 방식이다 (UI_AGENT_PLAN §2).
모드는 카드 구조 데이터(card_data.build)가 정한다.
"""
import json
from functools import lru_cache
from pathlib import Path

from app.config import settings

# 업종 키 → 원형 글자 (other는 1주차 임시로 A, 2주차 J11이 LLM 판정).
INDUSTRY_ARCHETYPE = {
    "cafe": "A",
    "restaurant": "A",
    "salon": "B",
    "pension": "C",
    "academy": "D",
    "workshop": "E",
    "individual": "F",
    "group": "G",
    "webservice": "H",
    "other": "A",
}


def _industry_key(card: dict) -> str:
    """카드의 업종 키. 대화로 만든 카드는 industry가 비어 있어 business_type에서 계산한다(industry_of)."""
    from app.services import prd_engine
    key = prd_engine.industry_of(card).key
    return key if key in INDUSTRY_ARCHETYPE else "other"


def _mode(card: dict) -> str:
    """카드 구조 데이터의 mode를 쓴다. 없으면 card_data.build로 계산한다."""
    data = card.get("data") or _build_data(card)
    return (data or {}).get("mode") or ""


def _build_data(card: dict) -> dict:
    """card_data.build를 늦게 불러온다 (J1a와 순환 없이)."""
    from app.services import card_data
    return card_data.build(card)


def of(card: dict) -> tuple:
    """(원형 글자, 모드)를 돌린다."""
    return (INDUSTRY_ARCHETYPE[_industry_key(card)], _mode(card))


def _blueprint_dir() -> Path:
    return Path(settings.templates_dir) / "blueprints"


@lru_cache(maxsize=16)
def load(name: str) -> dict:
    """청사진 파일 하나를 읽는다 (이름에 .json이 없어도 된다)."""
    filename = name if name.endswith(".json") else name + ".json"
    return json.loads((_blueprint_dir() / filename).read_text(encoding="utf-8"))


def blueprint(card: dict) -> dict | None:
    """<원형>-<모드> → <원형> → None 순서로 청사진을 찾는다."""
    arch, mode = of(card)
    names = ([f"{arch}-{mode}"] if mode else []) + [arch]
    for name in names:
        try:
            return load(name)
        except FileNotFoundError:
            continue
    return None
