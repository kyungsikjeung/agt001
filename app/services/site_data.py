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


# 원형 → 예약 칸 항목 이름 (card_data.ITEM_LABEL과 같은 말)
_ARCH_ITEM_LABEL = {"B": "시술", "C": "객실", "D": "수업", "E": "수업", "F": "작업", "G": "모임", "H": "요금제"}

def _examples(archetype: str, industry: str = "") -> dict:
    """원형 예시 파일. 업종 전용 파일(A-restaurant.json)이 있으면 먼저 쓴다. 없으면 빈 값.
    (식당이 카페 예시 사진·가격을 쓰던 문제: 집밥 식당에 케이크 사진이 나왔다)"""
    special = settings.templates_dir / "examples" / f"{archetype}-{industry}.json"
    if industry and special.is_file():
        archetype = f"{archetype}-{industry}"
    if archetype in _EXAMPLES:
        return _EXAMPLES[archetype]
    path = settings.templates_dir / "examples" / f"{archetype}.json"
    data = {"photos": {}, "prices": {}, "catalog": [], "staff": [],
            "classes": [], "rooms": [], "timetable": {}, "concerns": {}}
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
    """사장님 사진 (/uploads/로 시작하는 것만). 공지 사진은 뺀다 (NOTICE_PHOTO_CONTRACT §1-2)."""
    from app.services import photos as PH
    out = []
    for photo in PH.site_photos(card):
        if isinstance(photo, dict) and str(photo.get("url") or "").startswith("/uploads/"):
            out.append(photo)
    return out


def _ai_url(card: dict, slot: str) -> str:
    """AI 예시 그림 주소 (버튼으로 만든 /uploads/ 것만)."""
    ai = card.get("ai_images") or {}
    url = (ai.get(slot) or {}).get("url") if isinstance(ai.get(slot), dict) else ""
    return url if isinstance(url, str) and url.startswith("/uploads/") else ""


def _item_image(card: dict, name: str, pack: dict, example: dict) -> dict:
    """항목 사진 고르는 순서 (BETA_FLOW §2.7): 사장님 사진 → AI 그림 → 예시 팩."""
    try:
        from app.services import card_data as card_data_module
        hit = card_data_module.item_photo(card, name)
    except Exception:
        hit = None
    if isinstance(hit, dict) and str(hit.get("url") or "").startswith("/uploads/"):
        caption = str(hit.get("caption") or "").strip()
        return {"image": hit["url"], "image_alt": caption or f"{name} 사진"}
    ai = _ai_url(card, "item:" + name)
    if ai:
        return {"image": ai, "image_alt": f"{name} 사진 (AI 예시)", "image_ai": True}
    try:
        from app.services import art_lib  # 태그 사진 창고 (ART_LIB_CONTRACT §2-5, 그리기 중 생성·LLM 없음)
        lib = art_lib.pick(card, name)
    except Exception:
        lib = {}
    if lib:
        return lib
    return dict(example)


def _pack_room_example(pack: dict, name: str, pos: int) -> dict:
    """예시 팩 객실 사진 차례 (BETA_FLOW §2.5): room:k를 돌려 쓴다."""
    photos = pack.get("photos") or {}
    count = sum(1 for key in photos if str(key).startswith("room:"))
    if not count:
        return {}
    photo = photos.get(f"room:{(pos - 1) % count + 1}")
    if not photo:
        return {}
    return {"image": photo, "image_alt": f"{name} 사진 (예시)", "image_example": True}


def _item_caption(photo: dict) -> str:
    """사진첩 설명: 없으면 item: 태그의 이름을 쓴다 (§2.7)."""
    if not isinstance(photo, dict):
        return ""
    caption = str(photo.get("caption") or "").strip()
    if caption:
        return caption
    tag = str(photo.get("tag") or "")
    if tag.startswith("item:") and tag[5:].strip():
        return tag[5:].strip()
    return ""


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
        if node.get("optional") is True:
            section["optional"] = True
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
               primary: dict, secondary: dict, archetype: str = "") -> None:
    """hero bind 채우기."""
    content = {"title": shop, "subtitle": tagline or detail or _kind_words(card)}
    content.update(_hero_image(card, shop, pack))
    facts = []
    if hours:
        # 펜션은 체크인·체크아웃 시간이라 '영업' 대신 '입실·퇴실'로 말한다
        facts.append({"label": "입실·퇴실" if archetype == "C" else "영업", "value": hours})
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


def _desc_with_time(item: dict) -> str:
    """설명 + 걸리는 시간 ("펌 2시간 30분", D55 C3). 시간은 사장님이 말한 duration_min만."""
    desc = str(item.get("desc") or "")
    minutes = item.get("duration_min")
    if not isinstance(minutes, int) or minutes <= 0:
        return desc
    hours, rest = divmod(minutes, 60)
    took = " ".join(p for p in (f"{hours}시간" if hours else "", f"{rest}분" if rest else "") if p)
    return f"{desc} · {took} 걸려요" if desc else f"{took} 걸려요"


def _catalog_flat_items(data: dict, pack: dict) -> list:
    """catalog bind → 분류 없이 펼친 목록 (offerings--list-price용)."""
    items = []
    for group in data.get("catalog") or []:
        for item in (group.get("items") or []) if isinstance(group, dict) else []:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            name = str(item["name"])
            price = str(item.get("price") or "")
            entry = {"name": name, "desc": _desc_with_time(item)}
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


def _orderable(item: dict) -> bool:
    """주문 가능: 카드 가격(price_won)을 읽을 수 있을 때만. 예시 가격은 안 된다."""
    won = (item or {}).get("price_won")
    return isinstance(won, int) and not isinstance(won, bool) and won > 0


def _order_action(card: dict) -> str | None:
    """주문 폼 주소. design.py가 렌더 전에 카드 복사본에 둔다 (resolve에는 site_key가 안 들어온다)."""
    form = (card or {}).get("order_form")
    if not isinstance(form, dict):
        return None
    action = form.get("action")
    if isinstance(action, str) and action.startswith("/api/orders/") and len(action) < 120:
        return action
    return None


def _fill_catalog(sec: dict, data: dict, pack: dict, archetype: str, order: bool,
                  order_action: str | None = None, card: dict | None = None) -> None:
    """catalog bind → offerings--categories. order_action이 있으면 주문 폼(order_form·순서·주문 가능)도 넣는다."""
    if sec.get("variant") == "list-price":
        content = {"label": sec.get("label") or ("시술·가격" if archetype == "B" else "메뉴"),
                   "items": _catalog_flat_items(data, pack)}
        if order:
            content["order"] = True
        sec["content"] = content
        return
    categories = []
    idx = 0  # 주문 폼 칸 번호 (구역 안에서 0부터 차례로)
    for group in data.get("catalog") or []:
        if not isinstance(group, dict):
            continue
        items = []
        for item in group.get("items") or []:
            if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                continue
            name = str(item["name"])
            price = str(item.get("price") or "")
            entry = {"name": name, "desc": _desc_with_time(item)}
            if price:
                entry["price"] = price
            else:
                guess = _example_price(name, pack["prices"])
                entry["price"] = guess
                if guess:
                    entry["price_example"] = True
            entry["order_index"] = idx
            idx += 1
            entry["orderable"] = _orderable(item)
            items.append(entry)
        if not items:
            continue
        cat = {"name": str(group.get("name") or "")}
        # 분류 대표 사진: 첫 메뉴의 사장님 사진 → AI 그림 → 태그 사진 창고(ART_LIB) → 업종 예시 팩
        own = _item_image(card, items[0]["name"], pack, {}) if card and items[0].get("name") else {}
        photo = pack["photos"].get(f"category:{cat['name']}")
        if own.get("image"):
            cat["image"] = own["image"]
            cat["image_alt"] = f"{cat['name']} 사진" + (" (예시 이미지)" if own.get("image_example") else "")
            for flag in ("image_example", "image_ai"):
                if own.get(flag):
                    cat[flag] = True
        elif photo:
            cat["image"] = photo
            cat["image_alt"] = f"{cat['name']} 사진 (예시 이미지)"
            cat["image_example"] = True
        cat["items"] = items
        categories.append(cat)
    if not categories:
        for group in pack["catalog"]:
            items = []
            for item in group.get("items") or []:
                one = {**item, "example": True, "order_index": idx, "orderable": False}
                idx += 1
                items.append(one)
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
    if order_action and (order or sec.get("order") is True):
        content["order_form"] = {"action": order_action}
    sec["content"] = content


def _fill_staff(sec: dict, data: dict, pack: dict, booking_href: str) -> None:
    """staff bind → members (+ solo works). 선생님 수로 변형을 고른다(1명 solo, 2명 이상 team)."""
    members = []
    staff = [s for s in (data.get("staff") or []) if isinstance(s, dict) and str(s.get("name") or "").strip()]
    if staff:
        sec["variant"] = "solo" if len(staff) == 1 else "team"
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
    """booking bind → booking--slots (시안 예시 현황). 학원은 반 이름으로 고른다."""
    staff = [str(s.get("name")) for s in (data.get("staff") or [])
             if isinstance(s, dict) and str(s.get("name") or "").strip()]
    if archetype == "D":
        services = [str(c.get("name")) for c in (data.get("classes") or [])
                    if isinstance(c, dict) and str(c.get("name") or "").strip()]
        service_label = "반"
    else:
        services = []
        for group in data.get("catalog") or []:
            for item in (group.get("items") or []) if isinstance(group, dict) else []:
                name = str((item or {}).get("name") or "").strip() if isinstance(item, dict) else ""
                if name and name not in services:
                    services.append(name)
        service_label = _ARCH_ITEM_LABEL.get(archetype, "메뉴")
    sec["content"] = {"label": sec.get("label") or "예약", "note": _BOOKING_NOTE,
                      "staff": staff, "services": services,
                      "service_label": service_label,
                      "days": _example_days(hours), "days_example": True}


def _fill_classes(sec: dict, data: dict, pack: dict, booking_href: str) -> None:
    """classes bind → classes--cards (모르는 수강료는 예시 파일 값 + fee_example)."""
    items = []
    for entry in (data.get("classes") or [])[:12]:
        if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
            continue
        name = str(entry["name"])
        item = {"name": name, "target": str(entry.get("target") or ""),
                "days": str(entry.get("days") or ""), "time": str(entry.get("time") or ""),
                "capacity": str(entry.get("capacity") or "")}
        for key in ("level", "desc"):
            if entry.get(key):
                item[key] = str(entry[key])
        fee = str(entry.get("fee") or "")
        if fee:
            item["fee"] = fee
        else:
            guess = _example_price(name, pack["prices"])
            if guess:
                item["fee"] = guess
                item["fee_example"] = True
        items.append(item)
    if not items:
        for entry in pack["classes"]:
            if isinstance(entry, dict) and str(entry.get("name") or "").strip():
                items.append({**entry, "example": True})
    sec["content"] = {"label": sec.get("label") or "반 안내",
                      "cta_href": booking_href, "classes": items}


def _timetable_from_classes(classes: list) -> tuple:
    """반 요일·시간 → (요일 목록, 시간표 행)."""
    order = ("월", "화", "수", "목", "금", "토", "일")
    days = [d for d in order
            if any(d in str(c.get("days") or "").split("·")
                   for c in classes if isinstance(c, dict))]
    by_time: dict = {}
    for entry in classes:
        if not isinstance(entry, dict):
            continue
        found = [d for d in str(entry.get("days") or "").split("·") if d in order]
        time = str(entry.get("time") or "").strip()
        name = str(entry.get("name") or "").strip()
        if not found or not time or not name:
            continue
        by_time.setdefault(time, []).append((name, found))
    rows = []
    for time in sorted(by_time):
        cells = []
        for day in days:
            names = [name for name, found in by_time[time] if day in found]
            cells.append({"day": day, "text": names[0] if names else ""})
        rows.append({"time": time, "cells": cells})
    return days, rows[:12]


def _fill_timetable(sec: dict, data: dict, pack: dict) -> None:
    """timetable bind → timetable--week (반으로 표를 만들고, 없으면 예시 표 + example)."""
    days, rows = _timetable_from_classes(data.get("classes") or [])
    example = False
    if not rows:
        table = pack["timetable"] if isinstance(pack.get("timetable"), dict) else {}
        days = [d for d in (table.get("days") or []) if isinstance(d, str)][:7]
        rows = [r for r in (table.get("rows") or []) if isinstance(r, dict)]
        example = True
    content = {"label": sec.get("label") or "시간표", "days": days, "rows": rows}
    if example:
        content["example"] = True
    sec["content"] = content


def _season_rows(prices: list, today) -> tuple:
    """season_prices → 요금표 행 + 지금 이름표 (BETA_FLOW §2.5)."""
    from app.services import card_data as card_data_module
    current = card_data_module.current_label(prices, today)
    rows = []
    for entry in prices:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "")
        period = str(entry.get("period") or "")
        date_from, date_to = card_data_module.period_mmdd(period)
        dow = ""
        if not date_from:
            dow = "5,6" if label == "주말" else ("0,1,2,3,4" if label == "주중" else "")
        rows.append({"label": label, "period": period, "price": str(entry.get("price") or ""),
                     "from": date_from, "to": date_to, "dow": dow,
                     "is_current": bool(current) and label == current})
    return rows, current


def _fill_rooms(sec: dict, card: dict, data: dict, pack: dict, booking_href: str) -> None:
    """rooms bind → rooms--cards (사장님 → AI → 예시 팩 사진, 요금표 + 지금 요금)."""
    from app.services import card_data as card_data_module
    today = datetime.datetime.now(KST).date()
    season = None
    items = []
    rooms = [r for r in (data.get("rooms") or [])
             if isinstance(r, dict) and str(r.get("name") or "").strip()]
    for pos, entry in enumerate(rooms[:8], start=1):
        name = str(entry["name"])
        item = {"name": name, "capacity": str(entry.get("capacity") or "")}
        if entry.get("size"):
            item["size"] = str(entry["size"])
        item.update(_item_image(card, name, pack, _pack_room_example(pack, name, pos)))
        price = str(entry.get("price") or "")
        prices = None
        if price:
            item["price"] = price
        else:
            prices = entry.get("prices") or None
            if not prices:
                if season is None:
                    try:
                        season = card_data_module.season_prices(card)
                    except Exception:
                        season = []
                prices = season or None
        if prices:
            rows, current = _season_rows(prices, today)
            item["prices"] = rows
            item["has_prices"] = True
            current_price = next((r["price"] for r in rows
                                  if r["label"] == current and r["price"]), "")
            if current_price:
                item["price"] = current_price
        if not item.get("price"):
            guess = _example_price(name, pack["prices"])
            if guess:
                item["price"] = guess
                item["price_example"] = True
        feats = [f for f in (entry.get("features") or [])
                 if isinstance(f, str) and f.strip()][:6]
        if feats:
            item["features"] = feats
        items.append(item)
    if not items:
        listed = pack["rooms"] if isinstance(pack.get("rooms"), list) else []
        for pos, entry in enumerate(listed[:8], start=1):
            if not isinstance(entry, dict) or not str(entry.get("name") or "").strip():
                continue
            item = {**entry, "example": True}
            photo = pack["photos"].get(f"room:{pos}")
            if photo and not item.get("image"):
                item["image"] = photo
                item["image_alt"] = f"{item['name']} 사진 (예시)"
                item["image_example"] = True
            items.append(item)
    sec["content"] = {"label": sec.get("label") or "객실",
                      "booking_href": booking_href, "rooms": items}


def _stay_state(date: str) -> str:
    """결정론 예시 입실 현황 (같은 날짜면 항상 같은 값)."""
    digest = hashlib.md5(f"stay:{date}".encode("utf-8")).digest()[0] % 3
    return ("open", "few", "full")[digest]


def _example_stay_days(today=None) -> list:
    """예시 입실 현황 14일 (오늘 KST 다음 날부터)."""
    if today is None:
        today = datetime.datetime.now(KST).date()
    days = []
    for plus in range(1, 15):
        day = today + datetime.timedelta(days=plus)
        date = day.isoformat()
        days.append({"date": date, "label": f"{day.month}/{day.day}",
                     "dow": _DOW[day.weekday()], "state": _stay_state(date)})
    return days


def _fill_dates(sec: dict, data: dict) -> None:
    """dates bind → booking--dates (예시 14일 + days_example, 객실 이름, nights_max 3)."""
    rooms = [str(r.get("name")) for r in (data.get("rooms") or [])
             if isinstance(r, dict) and str(r.get("name") or "").strip()]
    sec["content"] = {"label": sec.get("label") or "예약",
                      "note": "빈 날짜를 골라 신청해 주세요. 가게에서 확인 후 연락드려요.",
                      "rooms": rooms, "nights_max": 3,
                      "days": _example_stay_days(), "days_example": True}


def _fill_concerns(sec: dict, pack: dict) -> None:
    """concerns bind → concerns--bubbles (예시 파일 고민, who는 예시)."""
    node = pack.get("concerns") if isinstance(pack.get("concerns"), dict) else {}
    quotes = node.get("items") if isinstance(node.get("items"), list) else []
    items = [{"quote": str(found), "who": "예시"} for found in quotes[:6]
             if isinstance(found, str) and found.strip()]
    content = {"items": items}
    if isinstance(node.get("heading"), str) and node["heading"].strip():
        content["heading"] = node["heading"]
    if isinstance(node.get("note"), str) and node["note"]:
        content["note"] = node["note"]
    sec["content"] = content


def _fill_signature(sec: dict, card: dict, data: dict, pack: dict) -> None:
    """signature bind → offerings--cards (badge 품목, 없으면 분류마다 첫 품목, 최대 3개).

    사진은 사장님 → AI 그림 → 분류 예시 팩 순서 (§2.7).
    """
    groups = [g for g in (data.get("catalog") or []) if isinstance(g, dict)]
    if not groups:
        groups = [g for g in pack["catalog"] if isinstance(g, dict)]
    picked: list = []
    for group in groups:
        for item in (group.get("items") or []) if isinstance(group, dict) else []:
            if isinstance(item, dict) and item.get("badge") and str(item.get("name") or "").strip():
                picked.append((group, item))
    for group in groups:
        if len(picked) >= 3:
            break
        items = [i for i in (group.get("items") or [])
                 if isinstance(i, dict) and str(i.get("name") or "").strip()]
        if items and all(p[1].get("name") != items[0].get("name") for p in picked):
            picked.append((group, items[0]))
    cards = []
    for group, item in picked[:3]:
        name = str(item["name"])
        card_item = {"name": name, "desc": str(item.get("desc") or "")}
        price = str(item.get("price") or "")
        if price:
            card_item["price"] = price
        else:
            guess = _example_price(name, pack["prices"])
            if guess:
                card_item["price"] = guess
                card_item["price_example"] = True
        photo = pack["photos"].get(f"category:{group.get('name')}")
        example = {"image": photo, "image_alt": f"{name} 사진 (예시)", "image_example": True} if photo else {}
        card_item.update(_item_image(card, name, pack, example))
        if item.get("example") is True:
            card_item["example"] = True
        cards.append(card_item)
    sec["content"] = {"label": sec.get("label") or "시그니처", "items": cards}


def _fill_gallery(sec: dict, card: dict, pack: dict, prefix: str) -> None:
    """space_photos·style_photos bind → 사진첩 (사장님 사진 우선)."""
    photos = _owner_photos(card)
    if photos:
        rest = photos[1:] or photos
        sec["content"] = {"label": sec.get("label") or "",
                          "items": [{"src": p["url"], "alt": _item_caption(p) or f"사진 {i + 1}",
                                     "caption": _item_caption(p)}
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
                          "items": [{"src": p["url"], "alt": _item_caption(p) or f"메뉴 사진 {i + 1}",
                                     "caption": _item_caption(p)}
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


def _location_geo(card: dict) -> dict | None:
    """공개 지도 좌표 (MAP_CONTRACT §1). placeholder면 없음."""
    geo = card.get("location_geo")
    if not isinstance(geo, dict) or geo.get("src") == "placeholder":
        return None
    try:
        return {"x": float(geo.get("x")), "y": float(geo.get("y"))}
    except (TypeError, ValueError):
        return None


def _location_items(phone: str, hours: str, archetype: str = "") -> list:
    """around--map에 붙는 전화·영업시간 (FILLED만, 없는 값은 뺀다)."""
    items = []
    if phone:
        items.append({"name": "전화", "note": phone})
    if hours:
        # 펜션은 체크인·체크아웃 시간이라 '영업시간' 대신 '입실·퇴실 시간'으로 말한다
        items.append({"name": "입실·퇴실 시간" if archetype == "C" else "영업시간", "note": hours})
    return items


def resolve(spec: dict, card: dict, *, archetype: str, mode: str = "draft") -> dict:
    """bind → content 채움 + navbar·actionbar (모드와 상관없이 같은 값)."""
    del mode
    out = copy.deepcopy(spec)
    sections = [s for s in (out.get("sections") or []) if isinstance(s, dict)]
    out["sections"] = sections
    data = _structured(card)
    from app.services import prd_engine  # 순환 참조 방지용 늦은 불러오기
    pack = _examples(archetype, prd_engine.industry_of(card).key)
    # 선생님이 없으면 optional staff 섹션은 뺀다 (학원 D).
    staff = [s for s in (data.get("staff") or [])
             if isinstance(s, dict) and str(s.get("name") or "").strip()]
    sections = [s for s in sections
                if not (s.get("bind") == "staff" and s.get("optional") is True and not staff)]
    out["sections"] = sections
    shop = _fact(card, "shop_name")
    phone, hours, address = _fact(card, "phone"), _fact(card, "hours"), _fact(card, "location")
    detail = _fact(card, "detail")
    copy_draft = card.get("copy") or {}
    tagline = copy_draft.get("tagline") if isinstance(copy_draft.get("tagline"), str) else ""
    primary = _target_action(sections, out.get("primary") or {})
    secondary = _target_action(sections, out.get("secondary") or {})
    booking_href = next((_anchor(sections, s["id"]) for s in sections
                         if s.get("bind") in ("booking", "dates")), "") or "#booking-title-booking"
    menu_href = next((_anchor(sections, s["id"]) for s in sections
                      if s.get("bind") == "catalog"), "") or "#"
    order = (out.get("primary") or {}).get("target") == "order-soon" if isinstance(out.get("primary"), dict) else False
    order_action = _order_action(card)
    for sec in sections:
        bind = sec.get("bind") or "none"
        if bind == "hero":
            _fill_hero(sec, card, pack, shop, detail, tagline, hours, address, primary, secondary,
                       archetype=archetype)
        elif bind == "catalog":
            _fill_catalog(sec, data, pack, archetype, order, order_action, card)
        elif bind == "staff":
            _fill_staff(sec, data, pack, booking_href)
        elif bind == "booking":
            _fill_booking(sec, data, archetype, hours)
        elif bind == "classes":
            _fill_classes(sec, data, pack, booking_href)
        elif bind == "timetable":
            _fill_timetable(sec, data, pack)
        elif bind == "rooms":
            _fill_rooms(sec, card, data, pack, booking_href)
        elif bind == "dates":
            _fill_dates(sec, data)
        elif bind == "concerns":
            _fill_concerns(sec, pack)
        elif bind == "signature":
            _fill_signature(sec, card, data, pack)
        elif bind == "location":
            sec["content"] = {"address": address, "items": _location_items(phone, hours, archetype=archetype)}
            geo = _location_geo(card)  # 좌표 있을 때만 공개 지도용으로 더한다
            if geo is not None:
                sec["content"]["geo"] = geo
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
    if order_action and any(isinstance(s, dict)
                            and isinstance((s.get("content") or {}).get("order_form"), dict)
                            for s in sections):
        out["order_form"] = True
    links = []
    for sec in sections:
        nav = sec.get("nav")
        if nav and len(links) < 4:
            href = _anchor(sections, sec["id"])
            if href:
                links.append({"label": nav, "href": href})
    if (spec.get("stamps") is True or isinstance(card.get("stamps"), dict)) and len(links) < 4:
        # 스탬프 화면 주소. site_key는 주문 폼과 같은 방식으로 카드 복사본에 실려 온다.
        stamp_key = ""
        boxed = card.get("stamps")
        if isinstance(boxed, dict) and isinstance(boxed.get("site_key"), str):
            stamp_key = boxed["site_key"]
        if not stamp_key:
            action = _order_action(card) or ""
            if action.startswith("/api/orders/"):
                stamp_key = action[len("/api/orders/"):].strip("/")
        if stamp_key and not any(l.get("href", "").endswith("/my") for l in links):
            links.append({"label": "스탬프", "href": f"/api/orders/{stamp_key}/my"})
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
    # 공지 글·사진. 사진 주소는 그대로 (NOTICE_PHOTO_CONTRACT §1-7).
    from app.services import photos as PH
    notice = PH.notice_of(card)
    if notice["text"] or notice["photos"]:
        out["notice"] = notice
    return out
