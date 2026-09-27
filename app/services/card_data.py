"""카드 구조 데이터 (BUILD_W1_W2 §1.1).

카드 칸·상황 답·가격 짝에서 결정론으로 계산한다. LLM을 부르지 않는다.
"""
import re

from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services.archetype import INDUSTRY_ARCHETYPE

# 업종 키 → 원형은 archetype.py 한 곳에 둔다
ARCHETYPE = INDUSTRY_ARCHETYPE

# 원형 → 기본 행동
PRIMARY_ACTION = {
    "A-dinein": "visit", "A-pickup": "order",
    "B": "reserve", "C": "reserve", "D": "consult",
    "E": "apply", "F": "inquire", "G": "inquire", "H": "inquire",
}

# 직함 낱말 (staff 파싱용)
TITLES = ("원장", "실장", "부원장", "디자이너", "선생님", "강사", "대표", "팀장")

# 카페 분류 낱말표
_COFFEE = ("아메리카노", "라떼", "에스프레소", "콜드브루", "드립", "카푸치노")
_FLAVORED_LATTE = ("딸기", "녹차", "초코", "고구마")
_DRINK = ("에이드", "티", "차", "주스", "스무디")
_DESSERT = ("케이크", "쿠키", "휘낭시에", "마카롱", "빵", "스콘", "와플", "크로플")


def _values(card: dict, key: str) -> list:
    """칸 읽기 (FILLED·ASSUMED만). design_variants와 같은 규칙."""
    slot = (card.get("slots") or {}).get(key) or {}
    if slot.get("status") not in (S.FILLED, S.ASSUMED):
        return []
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return [v for v in items if v]


def _text(card: dict, key: str) -> str:
    return ", ".join(str(v) for v in _values(card, key))


def _slot_value(card: dict, key: str) -> str:
    """상황 탐색 칸 값 한 줄 (FILLED·ASSUMED만)."""
    slot = (card.get("slots") or {}).get(key) or {}
    if slot.get("status") not in (S.FILLED, S.ASSUMED):
        return ""
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(v) for v in items if v)


def _custom_categories(card: dict) -> list:
    """menu_categories 칸 값 (FILLED만). 순서대로 분류 이름."""
    slot = (card.get("slots") or {}).get("menu_categories") or {}
    if slot.get("status") != S.FILLED:
        return []
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    cats = []
    for v in items:
        for part in re.split(r"[,·/]", str(v)):
            name = part.strip()
            if name and name not in cats:
                cats.append(name)
    return cats


def _classify(industry_key: str, name: str) -> str:
    """품목 → 분류 이름. 카페·미용실 낱말표, 나머지는 기본값."""
    if industry_key == "salon":
        if any(w in name for w in ("염색", "컬러", "탈색")):
            return "염색"
        if any(w in name for w in ("펌", "매직", "볼륨")):
            return "펌"
        if any(w in name for w in ("클리닉", "두피", "트리트먼트")):
            return "케어"
        if "컷" in name:
            return "컷"
        return "시술"
    if industry_key in ("cafe", "restaurant"):
        if any(w in name for w in _DESSERT):
            return "디저트"
        if any(w in name for w in _DRINK) or (
                "라떼" in name and any(w in name for w in _FLAVORED_LATTE)):
            return "음료"
        if any(w in name for w in _COFFEE):
            return "커피"
        return "메뉴"
    return "시술" if industry_key == "salon" else "메뉴"


def _catalog(card: dict, industry_key: str) -> list:
    """offerings → 분류 묶음. 가격은 price_pairs, 없으면 빈 문자열.

    menu_categories가 FILLED면 분류 이름을 그 순서로 쓰고,
    낱말표로 못 넣는 품목은 첫 분류에 넣는다.
    """
    pairs = card.get("price_pairs") or {}
    custom = _custom_categories(card)
    groups: dict = {}
    for item in _values(card, "offerings"):
        name = str(item)
        cat = _classify(industry_key, name)
        if custom and cat not in custom:
            cat = custom[0]
        groups.setdefault(cat, []).append(
            {"name": name, "price": pairs.get(name, ""), "desc": "", "source": "owner"})
    ordered = list(groups.items())
    if custom:
        ordered = [(c, groups[c]) for c in custom if c in groups] + \
            [(c, items) for c, items in ordered if c not in custom]
    return [{"name": cat, "source": "assumed", "items": items} for cat, items in ordered]


def _parse_staff(value: str) -> dict:
    """담당자 한 줄 → 이름·직함·전문 분야."""
    s = str(value or "")
    specialties: list = []
    if "(" in s and s.endswith(")"):
        head, tail = s[:-1].split("(", 1)
        specialties = [p.strip() for p in tail.replace("/", "·").split("·") if p.strip()]
    else:
        head = s
    role, name = "", head.strip()
    for tok in head.split():
        if tok in TITLES:
            role = tok
            name = head.replace(tok, "").strip()
            break
        for t in TITLES:
            if tok.endswith(t) and len(tok) > len(t):
                rest = tok[: -len(t)]
                role = t
                name = rest if len(rest) >= 2 else tok
                break
        if role:
            break
    return {"name": name, "role": role, "specialties": specialties, "source": "owner"}


def _staff(card: dict) -> list:
    return [_parse_staff(v) for v in _values(card, "staff")]


def _mode(card: dict, archetype: str, staff: list) -> str:
    """원형별 모드. A: 픽업 여부, B: 인원 수, 그 외 빈 문자열."""
    if archetype == "A":
        situation = card.get("situation") or {}
        if str(situation.get("order_mode") or "") in ("pickup", "픽업"):
            return "pickup"
        if "픽업 주문" in _slot_value(card, "order_mode"):
            return "pickup"
        if "픽업" in _text(card, "contact_method") or "주문" in _text(card, "contact_method"):
            return "pickup"
        return "dinein"
    if archetype == "B":
        situation = card.get("situation") or {}
        team = str(situation.get("team_mode") or "")
        if team:
            if "혼자" in team or team == "solo":
                return "solo"
            return "team"
        slot_team = _slot_value(card, "team_mode")
        if slot_team:
            return "solo" if "혼자" in slot_team else "team"
        return "team" if len(staff) >= 2 else "solo"
    return ""


def _primary_action(archetype: str, mode: str) -> str:
    if archetype == "A":
        return PRIMARY_ACTION["A-pickup" if mode == "pickup" else "A-dinein"]
    return PRIMARY_ACTION.get(archetype, "inquire")


def build(card: dict) -> dict:
    """카드 → 구조 데이터. 카드가 바뀔 때마다 다시 계산한다."""
    industry_key = E.industry_of(card).key
    archetype = ARCHETYPE.get(industry_key, "A")
    staff = _staff(card)
    mode = _mode(card, archetype, staff)
    return {
        "version": 1,
        "mode": mode,
        "primary_action": _primary_action(archetype, mode),
        "catalog": _catalog(card, industry_key),
        "staff": staff,
        "classes": [],
        "rooms": [],
        "schedule": None,
    }
