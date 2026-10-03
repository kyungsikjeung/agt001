"""주변 안내 (10/4 대표 요청): 대제목(장소 이름) + 소제목(도보 n분·차로 n분·n km·직접 쓴 글)과 보이는 모양.

card["nearby"] = {"items": [{"name", "unit", "value", "text"}], "style": "stack"|"badge"|"inline"}
- unit: walk(도보 n분) · car(차로 n분) · km(거리, 1 미만은 m) · text(직접 쓴 글)
- style: stack(제목 아래 작게) · badge(소제목을 사진 위 배지로) · inline(한 줄 "이름 · 도보 3분")
줄마다 사진은 "nearby:<이름>" 태그(선생님 사진과 같은 방식, photos.row_photo_url).
값은 숫자로 따로 둬서 나중에 정렬·필터(가까운 순)나 다른 단위로 바꾸기 쉽게 한다.
"""
import re

TAG_PREFIX = "nearby:"
UNITS = ("walk", "car", "km", "text")
STYLES = ("stack", "badge", "inline")
MAX_ITEMS = 8
NAME_MAX = 30
TEXT_MAX = 30


def sub_text(item: dict) -> str:
    """소제목 글: 도보 3분 · 차로 10분 · 1.2km · 500m · 직접 쓴 글."""
    unit = item.get("unit")
    value = item.get("value")
    if unit == "text":
        return str(item.get("text") or "").strip()
    if not isinstance(value, (int, float)) or value <= 0:
        return ""
    if unit == "walk":
        return f"도보 {int(value)}분"
    if unit == "car":
        return f"차로 {int(value)}분"
    if unit == "km":
        return f"{int(round(value * 1000))}m" if value < 1 else f"{value:g}km"
    return ""


def _number(raw, unit: str):
    try:
        v = float(str(raw).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    if unit in ("walk", "car"):
        return int(v) if 1 <= v <= 600 and v == int(v) else None
    return round(v, 2) if 0.05 <= v <= 500 else None


def clean(raw_items: list, style: str | None) -> tuple[dict, list[str]]:
    """화면에서 온 줄들을 검사해 저장 모양으로. (값, 틀린 곳 목록)."""
    errors: list[str] = []
    items: list[dict] = []
    seen: set[str] = set()
    for pos, raw in enumerate(raw_items or [], start=1):
        if not isinstance(raw, dict):
            continue
        name = " ".join(str(raw.get("name") or "").split())
        unit = raw.get("unit") if raw.get("unit") in UNITS else "walk"
        if not name and not str(raw.get("value") or raw.get("text") or "").strip():
            continue  # 빈 줄은 버린다
        if not name:
            errors.append(f"{pos}번째 줄: 장소 이름을 적어 주세요")
            continue
        if len(name) > NAME_MAX or re.search(r"[<>]", name):
            errors.append(f"{name[:10]}: 이름은 {NAME_MAX}자까지예요")
            continue
        if name in seen:
            errors.append(f"{name}: 같은 이름이 두 번 있어요")
            continue
        seen.add(name)
        one = {"name": name, "unit": unit}
        if unit == "text":
            text = " ".join(str(raw.get("text") or "").split())[:TEXT_MAX]
            one["text"] = text
        else:
            raw_value = raw.get("value")
            if raw_value in (None, ""):
                one["value"] = None  # 거리는 나중에 — 제목만 보인다
            else:
                value = _number(raw_value, unit)
                if value is None:
                    errors.append(f"{name}: " + ("1~600분 사이 숫자로 적어 주세요" if unit != "km"
                                                 else "0.05~500km 사이 숫자로 적어 주세요"))
                    continue
                one["value"] = value
        items.append(one)
    if len(items) > MAX_ITEMS:
        errors.append(f"주변 안내는 {MAX_ITEMS}곳까지예요")
    return {"items": items[:MAX_ITEMS], "style": style if style in STYLES else "stack"}, errors


def of(card: dict) -> dict:
    raw = (card or {}).get("nearby")
    if not isinstance(raw, dict):
        return {"items": [], "style": "stack"}
    items = [i for i in raw.get("items") or [] if isinstance(i, dict) and i.get("name")]
    return {"items": items, "style": raw.get("style") if raw.get("style") in STYLES else "stack"}


def view(card: dict) -> dict:
    """화면·사이트용: 줄마다 소제목 글과 사진 주소를 붙인다."""
    from app.services import photos
    data = of(card)
    return {"style": data["style"],
            "items": [{**i, "sub": sub_text(i), "photo": photos.row_photo_url(card, TAG_PREFIX, i["name"])}
                      for i in data["items"]]}
