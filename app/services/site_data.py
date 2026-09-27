"""청사진 바인딩 리졸버 (BUILD_W1_W2 §1.4).

청사진(전략·바인딩) + 카드(사실·구조 데이터) → 렌더러 명세.
사실(이름·전화·주소·영업시간)은 FILLED 칸만 쓰고 지어내지 않는다.
"""
import copy
import datetime
import hashlib
import json
import re

from app.config import settings
from app.services import prd_schema as S

# 한국 날짜 기준 (예시 현황 계산용)
KST = datetime.timezone(datetime.timedelta(hours=9))

# 예시 현황 요일 글자 (월요일=0)
_DOW = ("월", "화", "수", "목", "금", "토", "일")

# 하루 예시 시간 칸 상한 (시안 가독성용)
_MAX_SLOTS_PER_DAY = 9

# 예시 현황 일수 (오늘 KST 다음 날부터)
_EXAMPLE_DAYS = 5

# 예약 확인 안내 문구 (시안용 고정값)
_BOOKING_NOTE = "가게에서 확인한 뒤 연락드려요. 신청만으로 예약이 확정되지는 않아요."

# 예시 파일 캐시 (원형 글자 → 내용)
_EXAMPLES: dict = {}


def _examples(archetype: str) -> dict:
    """원형 예시 파일. 없으면 빈 값 (다른 원형은 J5b 이후)."""
    if archetype in _EXAMPLES:
        return _EXAMPLES[archetype]
    path = settings.templates_dir / "examples" / f"{archetype}.json"
    data = {"photos": {}, "prices": {}, "catalog": [], "staff": []}
    if path.is_file():
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = {**data, **{k: loaded[k] for k in data if k in loaded}}
    _EXAMPLES[archetype] = data
    return data


def _structured(card: dict) -> dict:
    """카드 구조 데이터. card["data"]가 있으면 쓰고 없으면 build를 부른다."""
    data = card.get("data")
    if isinstance(data, dict):
        return data
    try:
        from app.services import card_data as card_data_module
        return card_data_module.build(card)
    except Exception:
        return {"catalog": [], "staff": []}


def _fact(card: dict, key: str) -> str:
    """사실 칸 (FILLED만). design_variants._fact와 같은 규칙."""
    slot = (card.get("slots") or {}).get(key) or {}
    if slot.get("status") != S.FILLED:
        return ""
    value = slot.get("value")
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value or "")


def _kind_words(card: dict) -> str:
    """업종 말 (FILLED·ASSUMED). 첫 화면 부제가 비지 않게 거짓말 없이 잇는다."""
    slot = (card.get("slots") or {}).get("business_type") or {}
    if slot.get("status") not in (S.FILLED, S.ASSUMED):
        return ""
    value = slot.get("value")
    items = value if isinstance(value, list) else [value]
    return ", ".join(str(v) for v in items if v)


def _owner_photos(card: dict) -> list:
    """사장님 사진 (/uploads/로 시작하는 것만)."""
    out = []
    for photo in card.get("photos") or []:
        if isinstance(photo, dict) and str(photo.get("url") or "").startswith("/uploads/"):
            out.append(photo)
    return out


def _ai_url(card: dict, slot: str) -> str:
    """AI 예시 그림 주소 (버튼으로 만든 /uploads/ 것만)."""
    ai = card.get("ai_images") or {}
    url = (ai.get(slot) or {}).get("url") if isinstance(ai.get(slot), dict) else ""
    return url if isinstance(url, str) and url.startswith("/uploads/") else ""


def _anchor(sections: list, target: str) -> str:
    """청사진 target → #<type>-title-<id>. order-soon은 그대로."""
    if target == "order-soon":
        return "#order-soon"
    for sec in sections:
        if isinstance(sec, dict) and sec.get("id") == target:
            return f"#{sec.get('type')}-title-{target}"
    return ""


def _action(label: str, href: str) -> dict:
    """행동 버튼 한 개 (빈 값은 빼고 호출자가 판단)."""
    return {"label": label, "href": href}


def _target_action(sections: list, node: dict) -> dict:
    """primary·secondary 노드 ({label, target}) → {label, href}."""
    if not isinstance(node, dict):
        return {}
    label = node.get("label") if isinstance(node.get("label"), str) else ""
    href = _anchor(sections, node.get("target") if isinstance(node.get("target"), str) else "")
    if not label or not href:
        return {}
    return _action(label, href)


def skeleton(blueprint: dict, strategy_index: int) -> dict:
    """청사진 → 비어 있는 명세 (hero 포함, bind·tone 유지).

    primary·secondary는 resolve가 href로 바꿀 수 있게 함께 둔다.
    """
    strategy = blueprint["strategies"][strategy_index]
    sections = [{"id": "hero", "type": "hero", "variant": strategy["hero"],
                 "bind": "hero", "content": {}}]
    for node in strategy.get("sections") or []:
        section = {"id": node["id"], "type": node["type"], "variant": node["variant"],
                   "bind": node.get("bind", "none"), "content": {}}
        for key in ("label", "nav", "tone"):
            if node.get(key):
                section[key] = node[key]
        if node.get("order") is True:
            section["order"] = True
        sections.append(section)
    spec = {"version": 3, "locked": [], "tokens": copy.deepcopy(blueprint.get("tokens") or {}),
            "sections": sections}
    for key in ("primary", "secondary", "actionbar_secondary"):
        if blueprint.get(key):
            spec[key] = copy.deepcopy(blueprint[key])
    return spec


def _short_addr(address: str) -> str:
    """위치 한 줄 (앞의 넓은 지명 두 마디까지 뺀다. 예: 서울 마포구 연남로 12 → 연남로 12)."""
    words = address.split()
    return " ".join(words[2:]) if len(words) >= 3 else address


def _hero_image(card: dict, shop: str, pack: dict) -> dict:
    """첫 화면 사진 (사장님 → AI 예시 → 예시 팩)."""
    photos = _owner_photos(card)
    if photos:
        first = photos[0]
        return {"image": first["url"],
                "image_alt": first.get("caption") or f"{shop or '가게'} 대표 사진"}
    ai = _ai_url(card, "hero")
    if ai:
        return {"image": ai, "image_alt": "AI 예시 이미지: 사장님 사진으로 바뀌어요",
                "ai_example": True}
    if pack["photos"].get("hero"):
        return {"image": pack["photos"]["hero"],
                "image_alt": f"{shop or '가게'} 사진 (예시 이미지)", "ai_example": True}
    return {}


def _fill_hero(sec: dict, card: dict, pack: dict, shop: str,
               detail: str, tagline: str, hours: str, address: str,
               primary: dict, secondary: dict) -> None:
    """hero bind 채우기."""
    content = {"title": shop, "subtitle": tagline or detail or _kind_words(card)}
    content.update(_hero_image(card, shop, pack))
    facts = []
    if hours:
        facts.append({"label": "영업", "value": hours})
    if address:
        facts.append({"label": "위치", "value": _short_addr(address)})
    if facts:
        content["facts"] = facts
    if primary:
        content["cta"] = primary
    if secondary:
        content["cta2"] = secondary
    sec["content"] = content


def _example_price(name: str, prices: dict) -> str:
    """예시 가격 (이름이 정확히 맞거나 낱말이 겹치는 첫 값)."""
    if name in prices:
        return prices[name]
    for key, value in prices.items():
        if key and (key in name or name in key):
            return value
    return ""


def _catalog_flat_items(data: dict, pack: dict) -> list:
    """catalog bind → 분류 없이 펼친 목록 (offerings--list-price용)."""
    items = []
    for group in data.get("catalog") or []:
        for item in (group.get("items") or []) if isinstance(group, dict) else []:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            name = str(item["name"])
            price = str(item.get("price") or "")
            entry = {"name": name, "desc": str(item.get("desc") or "")}
            if price:
                entry["price"] = price
            else:
                guess = _example_price(name, pack["prices"])
                entry["price"] = guess
                if guess:
                    entry["price_example"] = True
            items.append(entry)
    if not items:
        for group in pack["catalog"]:
            items += [{**item, "example": True} for item in group.get("items") or []]
    return items


def _fill_catalog(sec: dict, data: dict, pack: dict, archetype: str, order: bool) -> None:
    """catalog bind → offerings--categories."""
    if sec.get("variant") == "list-price":
        content = {"label": sec.get("label") or ("시술·가격" if archetype == "B" else "메뉴"),
                   "items": _catalog_flat_items(data, pack)}
        if order:
            content["order"] = True
        sec["content"] = content
        return
    categories = []
    for group in data.get("catalog") or []:
        if not isinstance(group, dict):
            continue
        items = []
        for item in group.get("items") or []:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            name = str(item["name"])
            price = str(item.get("price") or "")
            entry = {"name": name, "desc": str(item.get("desc") or "")}
            if price:
                entry["price"] = price
            else:
                guess = _example_price(name, pack["prices"])
                entry["price"] = guess
                if guess:
                    entry["price_example"] = True
            items.append(entry)
        if not items:
            continue
        cat = {"name": str(group.get("name") or "")}
        photo = pack["photos"].get(f"category:{cat['name']}")
        if photo:
            cat["image"] = photo
            cat["image_alt"] = f"{cat['name']} 사진 (예시 이미지)"
            cat["image_example"] = True
        cat["items"] = items
        categories.append(cat)
    if not categories:
        for group in pack["catalog"]:
            items = [{**item, "example": True} for item in group.get("items") or []]
            cat = {"name": group.get("name"), "items": items}
            photo = pack["photos"].get(f"category:{cat['name']}")
            if photo:
                cat["image"] = photo
                cat["image_alt"] = f"{cat['name']} 사진 (예시 이미지)"
                cat["image_example"] = True
            categories.append(cat)
    content = {"label": sec.get("label") or ("시술·가격" if archetype == "B" else "메뉴"),
               "categories": categories}
    if order:
        content["order"] = True
    sec["content"] = content


def _fill_staff(sec: dict, data: dict, pack: dict, booking_href: str) -> None:
    """staff bind → members (+ solo works)."""
    members = []
    staff = [s for s in (data.get("staff") or []) if isinstance(s, dict) and str(s.get("name") or "").strip()]
    for pos, person in enumerate(staff, start=1):
        member = {"name": str(person["name"]), "role": str(person.get("role") or "")}
        tags = [t for t in (person.get("specialties") or []) if isinstance(t, str) and t.strip()][:4]
        if tags:
            member["specialties"] = tags
        photo = pack["photos"].get(f"staff:{pos}")
        if photo:
            member["image"] = photo
            member["image_example"] = True
        members.append(member)
    if not members:
        for pos, person in enumerate(pack["staff"], start=1):
            member = {**person, "example": True}
            photo = pack["photos"].get(f"staff:{pos}")
            if photo:
                member["image"] = photo
                member["image_example"] = True
            members.append(member)
    content = {"label": sec.get("label") or "담당자", "booking_href": booking_href,
               "members": members}
    if sec.get("variant") == "solo":
        works = []
        for pos in range(1, 7):
            photo = pack["photos"].get(f"style:{pos}")
            if photo:
                works.append({"src": photo, "image_example": True})
        if works:
            content["works"] = works
    sec["content"] = content


def _hours_range(hours: str) -> tuple:
    """영업시간 글에서 여는·닫는 시각 (못 읽으면 10~18시)."""
    found = [int(n) for n in re.findall(r"\d{1,2}", hours or "") if 0 <= int(n) <= 24]
    if len(found) >= 2 and found[1] > found[0]:
        return found[0], found[1]
    return 10, 18


def _slot_state(date: str, time: str) -> str:
    """결정론 예시 현황 (같은 날짜·시간이면 항상 같은 값)."""
    digest = hashlib.md5(f"{date}T{time}".encode("utf-8")).digest()[0] % 3
    return ("open", "few", "full")[digest]


def _example_days(hours: str, today=None) -> list:
    """예시 현황 5일 (오늘 KST 다음 날부터, 시간 단위)."""
    if today is None:
        today = datetime.datetime.now(KST).date()
    start, end = _hours_range(hours)
    times = [f"{h:02d}:00" for h in range(start, end + 1)][: _MAX_SLOTS_PER_DAY]
    days = []
    for plus in range(1, _EXAMPLE_DAYS + 1):
        day = today + datetime.timedelta(days=plus)
        date = day.isoformat()
        days.append({"date": date, "label": f"{day.month}/{day.day}",
                     "dow": _DOW[day.weekday()],
                     "slots": [{"time": t, "state": _slot_state(date, t)} for t in times]})
    return days


def _fill_booking(sec: dict, data: dict, archetype: str, hours: str) -> None:
    """booking bind → booking--slots (시안 예시 현황)."""
    staff = [str(s.get("name")) for s in (data.get("staff") or [])
             if isinstance(s, dict) and str(s.get("name") or "").strip()]
    services: list = []
    for group in data.get("catalog") or []:
        for item in (group.get("items") or []) if isinstance(group, dict) else []:
            name = str((item or {}).get("name") or "").strip() if isinstance(item, dict) else ""
            if name and name not in services:
                services.append(name)
    sec["content"] = {"label": sec.get("label") or "예약", "note": _BOOKING_NOTE,
                      "staff": staff, "services": services,
                      "service_label": "시술" if archetype == "B" else "메뉴",
                      "days": _example_days(hours), "days_example": True}


def _fill_gallery(sec: dict, card: dict, pack: dict, prefix: str) -> None:
    """space_photos·style_photos bind → 사진첩 (사장님 사진 우선)."""
    photos = _owner_photos(card)
    if photos:
        rest = photos[1:] or photos
        sec["content"] = {"label": sec.get("label") or "",
                          "items": [{"src": p["url"], "alt": p.get("caption") or f"사진 {i + 1}",
                                     "caption": p.get("caption") or ""}
                                    for i, p in enumerate(rest)]}
        return
    items = []
    for pos in range(1, 13):
        photo = pack["photos"].get(f"{prefix}:{pos}")
        if photo:
            items.append({"src": photo, "alt": "", "caption": "", "ai": True})
    sec["content"] = {"label": sec.get("label") or "", "items": items}


def _fill_menu_photos(sec: dict, card: dict, data: dict, pack: dict) -> None:
    """menu_photos bind → 분류 대표 사진첩 (사장님 사진 우선, 없으면 예시 팩 + ai 표시)."""
    photos = _owner_photos(card)
    if photos:
        rest = photos[1:] or photos
        sec["content"] = {"label": sec.get("label") or "",
                          "items": [{"src": p["url"], "alt": p.get("caption") or f"메뉴 사진 {i + 1}",
                                     "caption": p.get("caption") or ""}
                                    for i, p in enumerate(rest)]}
        return
    groups = [g for g in (data.get("catalog") or []) if isinstance(g, dict)]
    if not groups:
        groups = [g for g in pack["catalog"] if isinstance(g, dict)]
    items = []
    for group in groups:
        name = str(group.get("name") or "")
        photo = pack["photos"].get(f"category:{name}") if name else None
        if photo:
            items.append({"src": photo, "alt": f"{name} 메뉴 사진 (예시)",
                          "caption": name, "ai": True})
    if not items:
        for pos in range(1, 13):
            photo = pack["photos"].get(f"space:{pos}")
            if photo:
                items.append({"src": photo, "alt": "", "caption": "", "ai": True})
    sec["content"] = {"label": sec.get("label") or "", "items": items}


def _location_items(phone: str, hours: str) -> list:
    """around--map에 붙는 전화·영업시간 (FILLED만, 없는 값은 뺀다)."""
    items = []
    if phone:
        items.append({"name": "전화", "note": phone})
    if hours:
        items.append({"name": "영업시간", "note": hours})
    return items


def resolve(spec: dict, card: dict, *, archetype: str, mode: str = "draft") -> dict:
    """bind → content 채움 + navbar·actionbar (모드와 상관없이 같은 값)."""
    del mode
    out = copy.deepcopy(spec)
    sections = [s for s in (out.get("sections") or []) if isinstance(s, dict)]
    out["sections"] = sections
    data = _structured(card)
    pack = _examples(archetype)
    shop = _fact(card, "shop_name")
    phone, hours, address = _fact(card, "phone"), _fact(card, "hours"), _fact(card, "location")
    detail = _fact(card, "detail")
    copy_draft = card.get("copy") or {}
    tagline = copy_draft.get("tagline") if isinstance(copy_draft.get("tagline"), str) else ""
    primary = _target_action(sections, out.get("primary") or {})
    secondary = _target_action(sections, out.get("secondary") or {})
    booking_href = next((_anchor(sections, s["id"]) for s in sections
                         if s.get("bind") == "booking"), "") or "#booking-title-booking"
    menu_href = next((_anchor(sections, s["id"]) for s in sections
                      if s.get("bind") == "catalog"), "") or "#"
    order = (out.get("primary") or {}).get("target") == "order-soon" if isinstance(out.get("primary"), dict) else False
    for sec in sections:
        bind = sec.get("bind") or "none"
        if bind == "hero":
            _fill_hero(sec, card, pack, shop, detail, tagline, hours, address, primary, secondary)
        elif bind == "catalog":
            _fill_catalog(sec, data, pack, archetype, order)
        elif bind == "staff":
            _fill_staff(sec, data, pack, booking_href)
        elif bind == "booking":
            _fill_booking(sec, data, archetype, hours)
        elif bind == "location":
            sec["content"] = {"address": address, "items": _location_items(phone, hours)}
        elif bind == "contact":
            sec["content"] = {"phone": phone, "hours": hours, "address": address}
        elif bind in ("space_photos", "style_photos"):
            _fill_gallery(sec, card, pack, "space" if bind == "space_photos" else "style")
        elif bind == "menu_photos":
            _fill_menu_photos(sec, card, data, pack)
        elif bind == "order_soon":
            sec["content"] = {"phone": phone, "return_href": menu_href}
        else:
            sec["content"] = {}
    links = []
    for sec in sections:
        nav = sec.get("nav")
        if nav and len(links) < 4:
            href = _anchor(sections, sec["id"])
            if href:
                links.append({"label": nav, "href": href})
    out["navbar"] = {"title": shop, "top": "#hero-title-hero", "links": links}
    if primary:
        out["navbar"]["cta"] = primary
    actionbar = {"primary": primary} if primary else {}
    if phone:
        actionbar["secondary"] = _action("전화", f"tel:{phone}")
    else:
        around = next((s for s in sections if s.get("bind") == "location"), None)
        if around is not None:
            actionbar["secondary"] = _action("오시는 길", _anchor(sections, around["id"]))
    if actionbar:
        out["actionbar"] = actionbar
    return out
