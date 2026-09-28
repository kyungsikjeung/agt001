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

# 업종 → 상품 묶음 이름 (카페·식당 밖, 분류를 모를 때). 모르는 업종은 메뉴
ITEM_LABEL = {"salon": "시술", "pension": "객실", "academy": "수업", "workshop": "수업",
              "individual": "작업", "group": "모임", "webservice": "요금제"}

# 직함 낱말 (staff 파싱용)
TITLES = ("원장", "실장", "부원장", "디자이너", "선생님", "강사", "대표", "팀장")

# 요일 글자 (정규 순서)
_DAYS = ("월", "화", "수", "목", "금", "토", "일")

# 반 대상 낱말 (이름에서 찾는다, 없으면 target 칸)
_TARGETS = ("초등", "중등", "고등", "성인", "유아")

# 객실 번호 모양 (뒤의 낱말은 시설로 본다)
_ROOM_NO = re.compile(r"^\S*?\d+\s*호")

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
    return ITEM_LABEL.get(industry_key, "메뉴")


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


def _day_token(token: str) -> bool:
    """낱말 하나가 요일 토막인지 ("월수"·"월·수"·"월요일" O, "토익반" X)."""
    return bool(re.fullmatch(r"[월화수목금토일·,/.]+(요일)?", token))


def _class_days(text: str) -> str:
    """요일 읽기 ("월수"·"월·수"·"평일" → "월·수"). 없으면 빈 문자열."""
    found = []
    for token in re.split(r"\s+", text):
        if token in ("평일",):
            return "월·화·수·목·금"
        if token in ("주말",):
            return "토·일"
        if token in ("매일",):
            return "월·화·수·목·금·토·일"
        if _day_token(token):
            for day in token:
                if day in _DAYS and day not in found:
                    found.append(day)
    return "·".join(d for d in _DAYS if d in found)


def _class_time(text: str) -> str:
    """시간 읽기 ("16:00"·"오후 4시"·"4시" → "16:00"). 없으면 빈 문자열."""
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return f"{int(m.group(1)):02d}:{m.group(2)}"
    m = re.search(r"(오후|저녁|밤|오전|아침)\s*(\d{1,2})\s*시", text)
    if m:
        hour = int(m.group(2)) % 12
        if m.group(1) in ("오후", "저녁", "밤"):
            hour += 12
        return f"{hour:02d}:00"
    m = re.search(r"(\d{1,2})\s*시", text)
    if m:
        hour = int(m.group(1))
        if 1 <= hour <= 7:  # 학원은 낮·저녁 수업이라 작은 숫자는 오후로 본다
            hour += 12
        return f"{hour:02d}:00"
    return ""


def _headcount(text: str) -> str:
    """인원 읽기 ("정원 8명"·"8명" → "8명"). 없으면 빈 문자열."""
    m = re.search(r"정원\s*(\d+)\s*명?", text)
    if m:
        return f"{m.group(1)}명"
    m = re.search(r"(\d+)\s*인", text)
    if m:
        return f"{m.group(1)}인"
    m = re.search(r"(\d+)\s*명", text)
    if m:
        return f"{m.group(1)}명"
    return ""


def _strip_class_tokens(text: str) -> str:
    """반 이름에서 요일·시간·인원 토막을 뺀다."""
    kept = [tok for tok in re.split(r"\s+", text)
            if not _day_token(tok) and tok not in ("평일", "주말", "매일")]
    out = " ".join(kept)
    out = re.sub(r"\d{1,2}:\d{2}", " ", out)
    out = re.sub(r"(오후|저녁|밤|오전|아침)?\s*\d{1,2}\s*시", " ", out)
    out = re.sub(r"정원\s*\d+\s*명?", " ", out)
    out = re.sub(r"\d+\s*명", " ", out)
    return re.sub(r"\s+", " ", out).strip(" ·,/-")


def _classes(card: dict) -> list:
    """offerings 품목 → 반 목록 (학원 D). 이름·대상·요일·시간·정원·수강료를 결정론으로."""
    pairs = card.get("price_pairs") or {}
    fallback = _slot_value(card, "target").split(",")[0].strip()
    out = []
    for item in _values(card, "offerings"):
        text = str(item)
        name = _strip_class_tokens(text) or text
        target = next((w for w in _TARGETS if w in name), fallback)
        fee = pairs.get(name, "")
        if not fee:
            for key, value in pairs.items():
                if key and key in name:
                    fee = value
                    break
        out.append({"name": name, "target": target, "days": _class_days(text),
                    "time": _class_time(text), "capacity": _headcount(text),
                    "fee": fee, "source": "owner"})
    return out


def _rooms(card: dict) -> list:
    """offerings 품목 → 객실 목록 (펜션 C). 이름·인원·요금을 결정론으로."""
    pairs = card.get("price_pairs") or {}
    out = []
    for item in _values(card, "offerings"):
        text = str(item)
        features: list = []
        capacity = ""
        for paren in re.findall(r"\(([^)]*)\)", text):
            head = _headcount(paren)
            if head:
                capacity = f"({head})" if "인" in paren else head
            elif paren.strip():
                features.append(paren.strip())
        if not capacity:
            head = _headcount(re.sub(r"\([^)]*\)", " ", text))
            capacity = head
        name = re.sub(r"\([^)]*\)", " ", text)
        name = re.sub(r"\d+\s*인", " ", name)
        name = re.sub(r"\s+", " ", name).strip(" ·,/-")
        room_no = _ROOM_NO.match(name)
        rest = name[room_no.end():].strip() if room_no else ""
        if rest:
            features = [rest] + features
        price = pairs.get(name, "")
        if not price:
            for key, value in pairs.items():
                if key and key in name:
                    price = value
                    break
        entry = {"name": name, "capacity": capacity, "price": price, "source": "owner"}
        if features:
            entry["features"] = features
        out.append(entry)
    return out


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
    classes = _classes(card) if archetype in ("D", "E") else []
    rooms = _rooms(card) if archetype == "C" else []
    return {
        "version": 1,
        "mode": mode,
        "primary_action": _primary_action(archetype, mode),
        "catalog": _catalog(card, industry_key),
        "staff": staff,
        "classes": classes,
        "rooms": rooms,
        "schedule": None,
    }
