"""카드 구조 데이터 (BUILD_W1_W2 §1.1).

카드 칸·상황 답·가격 짝에서 결정론으로 계산한다. LLM을 부르지 않는다.
"""
import datetime
import re
from typing import Optional

from app.services import prd_engine as E
from app.services import photos as PH
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
# 객실이 아닌 부대시설. 객실 카드("이 객실 예약")에서 뺀다.
_FACILITY = re.compile(r"바베큐|바비큐|BBQ|수영장|풀장|족구장|캠프파이어|불멍|주차|매점|카페|노래방|찜질|스파장|놀이터", re.I)

# 가격 숫자 읽기 (D26: 사장님 말에 있는 금액만 숫자로 바꾼다)
_WON_RE = re.compile(
    r"만원|(?=\d)(?:\d[\d,]*\s*만\s*)?(?:\d+\s*천\s*)?(?:\d+\s*백\s*)?(?:\d[\d,]*\s*)?원")


def _one_won(text: str) -> Optional[int]:
    """금액 하나("8만5천원", "3천5백원", "4500원", "만원") → 원 단위 숫자. 못 읽으면 None."""
    t = re.sub(r"\s+", "", str(text or "").replace(",", ""))
    if not t.endswith("원"):
        return None
    t = t[:-1]
    if t == "만":
        return 10000
    if t == "천":
        return 1000
    m = re.fullmatch(r"(?:(\d+)만)?(?:(\d+)천)?(?:(\d+)백)?(\d+)?", t)
    if not m or not any(m.groups()):
        return None  # "원"만 있거나 숫자가 하나도 없으면 금액이 아니다
    man, chun, baek, rest = m.groups()
    total = int(baek) * 100 if baek else 0
    if man is not None:
        total += int(man) * 10000
    if chun is not None:
        total += int(chun) * 1000
    if rest:
        # "만"/"천" 뒤에 붙은 나머지는 일의 자리 (예: 8만5천원 → 만=8, 천=5)
        # 단독 숫자("4500원")도 그대로 더한다
        total += int(rest)
    return total if total > 0 else None


def price_won(text) -> Optional[int]:
    """가격 글 → 원 단위 숫자. 금액이 없거나 서로 다른 금액이 둘 이상이면 None."""
    if not text:
        return None
    found = _WON_RE.findall(str(text))
    if not found:
        return None
    values = []
    for part in found:
        v = _one_won(part)
        if v is not None:
            values.append(v)
    if not values:
        return None
    if len(set(values)) > 1:
        return None
    return values[0]


# 객실 수 세기 (BETA_FLOW §2.5: "객실 4개"·"방 4개"·"4개 객실"·"객실 4" → 4, 아니면 0)
_ROOM_COUNT = re.compile(
    r"^(?:객실|방|룸)\s*(\d+)\s*개?$|^(\d+)\s*개\s*(?:객실|방|룸)$")


def _room_count(text: str) -> int:
    """객실 수 표현이면 그 수, 아니면 0 ("101호 복층 4인"·"바베큐장"은 0)."""
    m = _ROOM_COUNT.match(str(text or "").strip())
    if not m:
        return 0
    return int(m.group(1) or m.group(2))


# 요금 이름표 (BETA_FLOW §2.5, 긴 것부터)
_LABELS = ("극성수기", "준성수기", "성수기", "비수기", "주중", "평일", "주말")
_LABEL_RE = re.compile("극성수기|준성수기|성수기|비수기|주중|평일|주말")
_PERIOD_RANGE = (r"(\d{1,2})\s*(?:/|월)\s*(\d{1,2})\s*(?:일)?\s*"
                 r"[~〜～\-－]\s*(\d{1,2})\s*(?:/|월)\s*(\d{1,2})\s*(?:일)?")
_PERIOD_RE = re.compile(r"\(\s*" + _PERIOD_RANGE + r"\s*\)")
_AMOUNT_RE = re.compile(
    r"(?:1박\s*)?(?:\d[\d,]*\s*만\s*\d+\s*천\s*원|\d[\d,]*\s*만?\s*원)")

# 사장님이 기간을 안 말했을 때 기본 기간 (준성수기는 없음)
_DEFAULT_PERIOD = {"성수기": "7/15~8/20", "극성수기": "7/25~8/10"}

# 지금 요금 우선순위 (낮을수록 먼저)
_SEASON_ORDER = {"극성수기": 0, "성수기": 1, "준성수기": 2,
                 "비수기": 3, "주중": 4, "주말": 5, "": 6}


def _features_period(features_text: str, label: str) -> str:
    """features 칸에서 "<이름표> 기간 ..." 날짜 범위를 찾는다. 없으면 빈 문자열."""
    if not label or not features_text:
        return ""
    pat = re.compile(r"(?<![극준])" + re.escape(label)
                     + r"\s*기간\s*[:：]?\s*" + _PERIOD_RANGE)
    m = pat.search(features_text)
    if not m:
        return ""
    groups = [int(g) for g in m.groups()]
    return f"{groups[0]}/{groups[1]}~{groups[2]}/{groups[3]}"


def season_prices(card: dict) -> list:
    """price 칸 글 → [{"label", "price", "period"}] (BETA_FLOW §2.5).

    이름표 뒤 첫 금액을 가져오고, 바로 뒤 괄호 안 기간이 있으면 period로 둔다.
    이름표가 없고 금액 하나뿐이면 [{"label": "", "price": ...}].
    """
    text = " ".join(str(v) for v in _values(card, "price")).strip()
    if not _LABEL_RE.search(text):
        pairs = card.get("price_pairs") or {}
        if isinstance(pairs, dict):
            season_pairs = [(k, v) for k, v in pairs.items()
                            if k and _LABEL_RE.search(str(k))]
            if season_pairs:
                text = " ".join(f"{k} {v}" for k, v in season_pairs)
    if not text:
        return []
    found = list(_LABEL_RE.finditer(text))
    if found:
        out = []
        for pos, match in enumerate(found):
            end = found[pos + 1].start() if pos + 1 < len(found) else len(text)
            seg = text[match.end():end]
            rest = seg.lstrip()
            period = ""
            period_match = _PERIOD_RE.match(rest)
            if period_match:
                groups = [int(g) for g in period_match.groups()]
                period = f"{groups[0]}/{groups[1]}~{groups[2]}/{groups[3]}"
                rest = rest[period_match.end():]
            amount = _AMOUNT_RE.search(rest)
            if not amount:
                continue
            label = match.group(0)
            if label == "평일":
                label = "주중"
            price = re.sub(r"\s+", " ", amount.group(0)).strip()
            if not period:
                features_text = " ".join(str(v) for v in _values(card, "features"))
                period = _features_period(features_text, label)
            out.append({"label": label, "price": price,
                        "period": period or _DEFAULT_PERIOD.get(label, "")})
        return out
    amounts = _AMOUNT_RE.findall(text)
    if len(amounts) == 1:
        return [{"label": "", "price": re.sub(r"\s+", " ", amounts[0]).strip()}]
    return []


def _period_md(period: str):
    """"7/15~8/20" → ((7, 15), (8, 20)). 못 읽으면 None."""
    m = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})~(\d{1,2})/(\d{1,2})\s*", str(period or ""))
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))


def _in_period(period: str, today) -> bool:
    """연도 무시 기간 안에 오늘이 있는지 (12/20~2/28처럼 해를 넘겨도 된다)."""
    span = _period_md(period)
    if span is None:
        return False
    (month1, day1), (month2, day2) = span
    now = (today.month, today.day)
    start, end = (month1, day1), (month2, day2)
    if start <= end:
        return start <= now <= end
    return now >= start or now <= end


def current_label(prices: list, today) -> str:
    """지금 요금 이름표 (BETA_FLOW §2.5, 오늘은 KST 날짜).

    기간 안이면 그 이름표(극성수기가 성수기보다 먼저), 아니면 비수기,
    주중·주말은 금·토요일이면 주말 아니면 주중, 모르면 "".
    """
    if isinstance(today, datetime.datetime):
        today = today.date()
    entries = [p for p in (prices or []) if isinstance(p, dict)]
    best = None
    for entry in entries:
        if entry.get("period") and _in_period(entry["period"], today):
            label = str(entry.get("label") or "")
            if best is None or _SEASON_ORDER.get(label, 9) < _SEASON_ORDER.get(best, 9):
                best = label
    if best is not None:
        return best
    labels = {str(p.get("label") or "") for p in entries}
    if "비수기" in labels:
        return "비수기"
    want = "주말" if today.weekday() in (4, 5) else "주중"
    if want in labels:
        return want
    return ""


def period_mmdd(period: str) -> tuple:
    """"7/15~8/20" → ("07-15", "08-20"). 못 읽으면 ("", "")."""
    span = _period_md(period)
    if span is None:
        return "", ""
    (month1, day1), (month2, day2) = span
    return f"{month1:02d}-{day1:02d}", f"{month2:02d}-{day2:02d}"


def item_photo(card: dict, name: str):
    """항목 사진: 사장님 사진만 본다 (BETA_FLOW §2.7 순서 1).

    tag == "item:"+이름 또는 설명에 이름이 들어 있는 것(공백 무시) 중 첫 장.
    없으면 None.
    """
    want = str(name or "").strip()
    if not want:
        return None
    flat = want.replace(" ", "")
    for photo in PH.site_photos(card):  # 공지 사진은 항목 사진 후보에서 뺀다 (NOTICE_PHOTO_CONTRACT §1-2)
        if not isinstance(photo, dict):
            continue
        if not str(photo.get("url") or "").startswith("/uploads/"):
            continue
        if photo.get("tag") == "item:" + want:
            return photo
        caption = str(photo.get("caption") or "")
        if flat and flat in caption.replace(" ", ""):
            return photo
    return None

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


def _pair_for(pairs: dict, name: str):
    """이름에 맞는 짝값 (정확히 일치 먼저, 없으면 짝 키가 이름에 들어간 것)."""
    if name in pairs:
        return pairs[name]
    for key, value in pairs.items():
        if key and key in name:
            return value
    return None


def _catalog(card: dict, industry_key: str) -> list:
    """offerings → 분류 묶음. 가격은 price_pairs, 없으면 빈 문자열.

    menu_categories가 FILLED면 분류 이름을 그 순서로 쓰고,
    낱말표로 못 넣는 품목은 첫 분류에 넣는다.
    사장님이 그룹을 적은 항목(item_groups)은 그 그룹이 목록에 있을 때 그 그룹이다 (GROUP_CARDS_CONTRACT §2-4).
    """
    pairs = card.get("price_pairs") or {}
    durations = card.get("duration_pairs") or {}
    custom = _custom_categories(card)
    pinned = card.get("item_groups") if isinstance(card.get("item_groups"), dict) else {}
    groups: dict = {}
    for item in _values(card, "offerings"):
        name = str(item)
        cat = pinned.get(name)
        if cat not in custom:
            cat = _classify(industry_key, name)
            if custom and cat not in custom:
                cat = custom[0]
        price = pairs.get(name, "")
        groups.setdefault(cat, []).append(
            {"name": name, "price": price, "price_won": price_won(price),
             "duration_min": _pair_for(durations, name), "desc": "", "source": "owner"})
    ordered = list(groups.items())
    if custom:
        ordered = [(c, groups[c]) for c in custom if c in groups] + \
            [(c, items) for c, items in ordered if c not in custom]
    return [{"name": cat, "source": "assumed", "items": items} for cat, items in ordered]


def group_view(card: dict) -> tuple:
    """편집기용 그룹 (GROUP_CARDS_CONTRACT §2-6): (그룹 순서, {항목 이름: 지금 보이는 그룹}).

    순서 = 그룹 목록(빈 그룹 포함) + 그 밖에 보이는 분류(낱말표).
    """
    order = list(_custom_categories(card))
    shown = {}
    for cat in _catalog(card, E.industry_of(card).key):
        if cat["name"] not in order:
            order.append(cat["name"])
        for it in cat["items"]:
            shown[it["name"]] = cat["name"]
    return order, shown


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


def _note_for(card: dict, name: str) -> tuple:
    """이름에 맞는 설명 토막 (prd_engine._record_item_notes) → (가격 뺀 글, 가격 글 하나 또는 "")."""
    notes = card.get("item_notes") or {}
    note = notes.get(name, "")
    if not note:
        for key, value in notes.items():
            if key and (key in name or name in key):
                note = value
                break
    if not note:
        return "", ""
    prices = [p.strip() for p in E._PRICE_RE.findall(note)]
    fee = prices[0] if prices and price_won(" ".join(prices)) is not None else ""
    return E._PRICE_RE.sub(" ", note), fee  # "월 20만원"의 '월'을 요일로 읽지 않게 가격을 먼저 뺀다


def _classes(card: dict) -> list:
    """offerings 품목 → 반 목록 (학원 D). 이름·대상·요일·시간·정원·수강료를 결정론으로."""
    pairs = card.get("price_pairs") or {}
    fallback = _slot_value(card, "target").split(",")[0].strip()
    out = []
    for item in _values(card, "offerings"):
        text = str(item)
        name = _strip_class_tokens(text) or text
        target = next((w for w in _TARGETS if w in name), fallback)
        note, note_fee = _note_for(card, name)
        fee = pairs.get(name, "")
        if not fee:
            for key, value in pairs.items():
                if key and key in name:
                    fee = value
                    break
        fee = fee or note_fee
        out.append({"name": name, "target": target,
                    "days": _class_days(text) or _class_days(note),
                    "time": _class_time(text) or _class_time(note),
                    "capacity": _headcount(text) or _headcount(note),
                    "fee": fee, "price_won": price_won(fee), "source": "owner"})
    return out


def _rooms(card: dict) -> list:
    """offerings 품목 → 객실 목록 (펜션 C). 이름·인원·요금을 결정론으로.

    "객실 4개"처럼 수를 말하면 "객실 1"…"객실 N"(최대 8)으로 편다 (§2.5).
    그 객실 요금이 price_pairs에 없으면 prices = season_prices(card).
    """
    pairs = card.get("price_pairs") or {}
    out = []
    for item in _values(card, "offerings"):
        text = str(item)
        if _FACILITY.search(text) and not _ROOM_NO.match(text.strip()):
            continue  # 바베큐장·수영장 같은 부대시설은 객실이 아니다
        if _LABEL_RE.search(text) and not _ROOM_NO.match(text.strip()):
            continue  # 성수기 1박 같은 요금 이름표는 객실이 아니다
        count = _room_count(text)
        if count:
            for pos in range(1, min(count, 8) + 1):
                name = f"객실 {pos}"
                price = pairs.get(name, "")
                out.append({"name": name, "capacity": "", "price": price,
                            "price_won": price_won(price),
                            "source": "owner", "numbered": True})
            continue
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
        note, note_price = _note_for(card, name)
        if not capacity:
            capacity = _headcount(note)
        price = pairs.get(name, "")
        if not price:
            for key, value in pairs.items():
                if key and key in name:
                    price = value
                    break
        price = price or note_price
        entry = {"name": name, "capacity": capacity, "price": price,
                 "price_won": price_won(price), "source": "owner"}
        if features:
            entry["features"] = features
        out.append(entry)
    prices = None
    for entry in out:
        if not entry.get("price"):
            if prices is None:
                prices = season_prices(card)
            if prices:
                entry["prices"] = prices
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
