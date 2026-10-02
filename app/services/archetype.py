"""손님 동선 원형 판정과 청사진 불러오기 (BUILD_W1_W2 §1.2·§1.3).

원형은 업종이 아니라 손님이 움직이는 방식이다 (UI_AGENT_PLAN §2).
모드는 카드 구조 데이터(card_data.build)가 정한다.
"""
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from app.config import settings

log = logging.getLogger(__name__)

# 업종 키 → 원형 글자 (other는 of()가 override → 낱말표 → A 순서로 푼다).
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
    "event": "I",  # 초대·기념(청첩장·돌잔치·칠순, EVENT_INVITE_PLAN)
    "other": "A",
}


# 업종 말 낱말 → 원형 (other일 때만 쓴다. 겹치는 말은 앞 순서가 이긴다).
# 순서 이유: 음식 판매(케이크 배달 서비스 → A)가 서비스(H)보다 먼저,
# 법률 상담 솔루션 같은 상품형(H)이 전문가 의뢰(F)보다 먼저 판정된다.
_KEYWORD_ARCHETYPE = (
    ("I", ("청첩장", "결혼식", "돌잔치", "칠순", "팔순", "환갑", "고희연", "초대장")),
    ("B", ("필라테스", "요가", "퍼스널", "피티", "네일", "속눈썹", "왁싱",
           "반려견", "애견", "미용", "바버", "타투")),
    ("D", ("수영", "태권도", "피아노", "과외", "교습", "어린이집",
           "유치원", "입시", "학원")),
    ("C", ("캠핑", "글램핑", "파티룸", "공유오피스", "대관")),
    ("E", ("원데이", "공방", "클래스", "체험", "쿠킹", "도예")),
    ("A", ("꽃집", "생화", "반찬", "케이크", "베이커리", "떡", "정육")),
    ("H", ("플랫폼", "솔루션", "서비스", "saas", "앱")),
    ("F", ("사진", "웨딩", "인테리어", "디자인", "세무", "법률", "번역", "연주")),
    ("G", ("동호회", "모임", "교회", "봉사", "동창")),
)

# 로마자 낱말은 낱말 경계로 찾는다 ("pt"가 엉뚱한 영어에 걸리지 않게).
_LATIN_KEYWORDS = {"pt", "saas"}


def keyword_archetype(business_type: str) -> str | None:
    """업종 말에서 원형을 결정론으로 고른다. 모르면 None."""
    text = (business_type or "").lower()
    if not text.strip():
        return None
    for letter, words in _KEYWORD_ARCHETYPE:
        for word in words:
            if word in _LATIN_KEYWORDS:
                if re.search(r"(?<![a-z])" + word + r"(?![a-z])", text):
                    return letter
            elif word in text:
                return letter
    return None


def _business_type_text(card: dict) -> str:
    """카드의 업종 말 (business_type 칸 값)."""
    slot = ((card or {}).get("slots") or {}).get("business_type") or {}
    value = slot.get("value")
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value or "")


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
    """(원형 글자, 모드)를 돌린다.

    업종 키가 원형표에 있으면 그대로 쓰고, other일 때만
    archetype_override(LLM) → 낱말표 → A 순서로 쓴다.
    """
    if _industry_key(card or {}) != "other":
        return (INDUSTRY_ARCHETYPE[_industry_key(card)], _mode(card))
    override = (card or {}).get("archetype_override")
    if isinstance(override, str) and override in "ABCDEFGHI" and len(override) == 1:
        return (override, _mode(card))
    return (keyword_archetype(_business_type_text(card)) or "A", _mode(card))


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


_JUDGE_SYSTEM = (
    "너는 가게 설명을 보고 손님 동선 원형 하나를 고르는 도우미다. JSON만 출력한다. "
    "원형: A(방문·메뉴형: 카페·식당) B(사람 예약형: 미용실·PT) C(공간 예약형: 펜션·스튜디오) "
    "D(상담·등록형: 학원) E(클래스·체험형: 공방) F(작업·의뢰형: 사진·전문가) "
    "G(모임·단체형: 동호회·교회) H(서비스·상품형: 웹서비스·판매) I(초대·기념형: 청첩장·돌잔치). "
    '출력 형식: {"archetype": "B", "reason": "이유 한 줄"}'
)


def _judge_summary(card: dict) -> str:
    """LLM에 주는 카드 요약. 전화·주소는 넣지 않는다."""
    from app.services import prd_schema as S
    slots = (card or {}).get("slots") or {}

    def _text(key: str) -> str:
        slot = slots.get(key) or {}
        if slot.get("status") not in (S.FILLED, S.ASSUMED):
            return ""
        value = slot.get("value")
        items = value if isinstance(value, list) else [value]
        return ", ".join(str(v) for v in items if v)

    mood = ""
    concept = (card or {}).get("concept")
    if isinstance(concept, dict) and isinstance(concept.get("mood"), list):
        mood = ", ".join(str(m) for m in concept["mood"] if m)
    return f"업종: {_text('business_type')}\n상품: {_text('offerings')}\n분위기: {mood}"


def judge(card: dict) -> str | None:
    """other 업종일 때만 LLM이 원형 하나를 고른다(8초).

    고른 값은 card["archetype_override"]에 두고 of()가 먼저 쓴다.
    실패하거나 other가 아니면 None(기존 A 흐름).
    """
    try:
        if _industry_key(card or {}) != "other":
            return None
    except Exception:
        return None
    # 낱말표로 이미 정해지면 LLM(8초)을 부르지 않는다: 첫 시안이 빨라진다(of()가 낱말표를 쓴다)
    known = keyword_archetype(_business_type_text(card))
    if known:
        return known
    try:
        from app import llm
        raw = llm.chat_json(_JUDGE_SYSTEM, _judge_summary(card), timeout_sec=8, max_tokens=300)
    except Exception:
        log.exception("원형 판정 호출 실패")
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        found = re.search(r"\{.*\}", raw or "", re.S)
        try:
            data = json.loads(found.group(0)) if found else {}
        except ValueError:
            return None
    letter = data.get("archetype") if isinstance(data, dict) else None
    if isinstance(letter, str) and letter in "ABCDEFGHI" and len(letter) == 1:
        card["archetype_override"] = letter
        return letter
    return None
