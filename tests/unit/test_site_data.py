"""리졸버 (BUILD_W1_W2 §1.4): skeleton + resolve.

DB가 필요 없다: 청사진 dict를 직접 만들고 card["data"]를 직접 넣는다
(J4·J1a가 파일을 동시에 만드는 중이라 실물을 읽지 않는다).
`pytest --noconftest tests/unit/test_site_data.py`로 돈다.
"""
import copy

from app.services import site_data
from app.services import site_render as SR


def _slot(value):
    return {"status": "filled", "value": value}


CAFE_TOKENS = {"palette": "coffee", "font_pair": "serif-warm", "density": "comfortable",
               "radius": "soft", "image_style": "card"}

CAFE_BP = {
    "archetype": "A", "mode": "dinein",
    "primary": {"label": "길찾기", "target": "around"},
    "secondary": {"label": "메뉴 보기", "target": "menu"},
    "actionbar_secondary": "phone",
    "tokens": CAFE_TOKENS,
    "strategies": [{
        "id": "v1", "name": "메뉴판형", "journey": "메뉴 보고 → 길찾기", "tone": "calm",
        "hero": "photo-overlay",
        "sections": [
            {"id": "menu", "type": "offerings", "variant": "categories",
             "bind": "catalog", "label": "메뉴", "nav": "메뉴"},
            {"id": "space", "type": "gallery", "variant": "swipe",
             "bind": "space_photos", "label": "공간", "nav": "공간"},
            {"id": "around", "type": "around", "variant": "map",
             "bind": "location", "nav": "오시는 길"},
            {"id": "contact", "type": "contact", "variant": "call-first", "bind": "contact"},
            {"id": "inquiry", "type": "contact", "variant": "form", "bind": "none"},
        ],
    }],
}

CAFE_DATA = {
    "version": 1, "mode": "dinein", "primary_action": "visit",
    "catalog": [
        {"name": "커피", "source": "assumed", "items": [
            {"name": "아메리카노", "price": "4,500원", "desc": "", "source": "owner"},
            {"name": "카페라떼", "price": "", "desc": "", "source": "owner"}]},
        {"name": "음료", "source": "assumed", "items": [
            {"name": "유자에이드", "price": "", "desc": "", "source": "owner"}]},
        {"name": "디저트", "source": "assumed", "items": [
            {"name": "바스크치즈케이크", "price": "6,500원", "desc": "", "source": "owner"}]},
    ],
    "staff": [], "classes": [], "rooms": [], "schedule": None,
}


def _cafe_card(**slots):
    base = {"shop_name": "연남 느린오후", "phone": "02-123-4567",
            "hours": "매일 10~21시", "location": "서울 마포구 연남로 12",
            "detail": "직접 로스팅하는 조용한 카페"}
    base.update(slots)
    card = {"slots": {k: _slot(v) for k, v in base.items() if v is not None},
            "copy": {"tagline": "창가 자리가 넓은 조용한 카페예요."},
            "data": copy.deepcopy(CAFE_DATA)}
    return card


def _section(spec, bind):
    return next(s for s in spec["sections"] if s.get("bind") == bind)


def _items_by_name(menu):
    return {i["name"]: i for c in menu["content"]["categories"] for i in c["items"]}


def test_skeleton_keeps_hero_first_and_bind_tone():
    spec = site_data.skeleton(CAFE_BP, 0)
    assert spec["sections"][0]["type"] == "hero" and spec["sections"][0]["bind"] == "hero"
    binds = [s["bind"] for s in spec["sections"]]
    assert binds == ["hero", "catalog", "space_photos", "location", "contact", "none"]
    assert all(s["content"] == {} for s in spec["sections"])


def test_cafe_prices_owner_first_example_marked():
    spec = site_data.resolve(site_data.skeleton(CAFE_BP, 0), _cafe_card(), archetype="A")
    items = _items_by_name(_section(spec, "catalog"))
    assert items["아메리카노"]["price"] == "4,500원" and "price_example" not in items["아메리카노"]
    assert items["카페라떼"]["price"] == "5,000원" and items["카페라떼"]["price_example"] is True
    assert items["유자에이드"]["price"] == "5,500원" and items["유자에이드"]["price_example"] is True
    assert items["바스크치즈케이크"]["price"] == "6,500원" and "price_example" not in items["바스크치즈케이크"]
    SR.render_site(spec)  # 예외 없이 그려짐
    public = SR.render_site(spec, public=True)
    assert "4,500원" in public and "6,500원" in public
    assert "5,000원" not in public and "카페라떼" in public  # 예시 가격만 빠짐


def test_no_phone_means_no_invention_and_around_secondary():
    card = _cafe_card()
    del card["slots"]["phone"]
    spec = site_data.resolve(site_data.skeleton(CAFE_BP, 0), card, archetype="A")
    assert spec["actionbar"]["secondary"] == {"label": "오시는 길", "href": "#around-title-around"}
    assert _section(spec, "contact")["content"]["phone"] == ""
    SR.render_site(spec)


SALON_BP = {
    "archetype": "B", "mode": "team",
    "primary": {"label": "예약하기", "target": "booking"},
    "secondary": {"label": "디자이너 보기", "target": "staff"},
    "actionbar_secondary": "phone",
    "tokens": {"palette": "charcoal-gold", "font_pair": "serif-elegant",
               "density": "comfortable", "radius": "soft", "image_style": "card"},
    "strategies": [{
        "id": "v1", "name": "디자이너형", "journey": "디자이너 보고 → 예약", "tone": "calm",
        "hero": "photo-overlay",
        "sections": [
            {"id": "staff", "type": "staff", "variant": "team",
             "bind": "staff", "label": "디자이너", "nav": "디자이너"},
            {"id": "price", "type": "offerings", "variant": "categories",
             "bind": "catalog", "label": "시술·가격", "nav": "시술·가격"},
            {"id": "booking", "type": "booking", "variant": "slots",
             "bind": "booking", "label": "예약", "nav": "예약"},
            {"id": "style", "type": "gallery", "variant": "swipe",
             "bind": "style_photos", "label": "스타일", "nav": "스타일"},
            {"id": "around", "type": "around", "variant": "map",
             "bind": "location", "nav": "오시는 길"},
            {"id": "inquiry", "type": "contact", "variant": "form", "bind": "none"},
        ],
    }],
}


def _salon_card():
    return {
        "slots": {"shop_name": _slot("살롱 드 연남"), "phone": _slot("02-333-4444"),
                  "hours": _slot("10~20시"), "location": _slot("서울 마포구 동교로 30")},
        "copy": {},
        "data": {
            "version": 1, "mode": "team", "primary_action": "reserve",
            "catalog": [
                {"name": "컷", "source": "assumed", "items": [
                    {"name": "컷", "price": "2만5천원", "desc": "", "source": "owner"}]},
                {"name": "염색", "source": "assumed", "items": [
                    {"name": "염색", "price": "", "desc": "", "source": "owner"}]},
            ],
            "staff": [
                {"name": "김미용", "role": "원장", "specialties": ["컷"], "source": "owner"},
                {"name": "박하나", "role": "실장", "specialties": ["염색"], "source": "owner"},
                {"name": "이서준", "role": "디자이너", "specialties": ["펌"], "source": "owner"},
            ],
            "classes": [], "rooms": [], "schedule": None,
        },
    }


def test_salon_team_staff_and_booking():
    spec = site_data.resolve(site_data.skeleton(SALON_BP, 0), _salon_card(), archetype="B")
    staff = _section(spec, "staff")["content"]
    assert [m["name"] for m in staff["members"]] == ["김미용", "박하나", "이서준"]
    assert staff["booking_href"] == "#booking-title-booking"
    booking = _section(spec, "booking")["content"]
    assert booking["days_example"] is True and booking["staff"] == ["김미용", "박하나", "이서준"]
    assert booking["service_label"] == "시술" and set(booking["services"]) == {"컷", "염색"}
    assert len(booking["days"]) == 5  # 오늘 다음 날부터 5일
    states = {s["state"] for d in booking["days"] for s in d["slots"]}
    assert states <= {"open", "few", "full"} and len(states) > 1  # 결정론으로 섞임
    again = site_data.resolve(site_data.skeleton(SALON_BP, 0), _salon_card(), archetype="B")
    assert again["sections"] == spec["sections"]  # 같은 입력이면 같은 결과
    SR.render_site(spec)


def test_empty_catalog_uses_example_all_and_hidden_on_public():
    card = _cafe_card()
    card["data"]["catalog"] = []
    spec = site_data.resolve(site_data.skeleton(CAFE_BP, 0), card, archetype="A")
    cats = _section(spec, "catalog")["content"]["categories"]
    assert cats and all(i.get("example") is True for c in cats for i in c["items"])
    SR.render_site(spec)
    assert 'id="offerings-title-menu"' not in SR.render_site(spec, public=True)


def test_navbar_links_follow_nav_order_and_order_soon_target():
    spec = site_data.resolve(site_data.skeleton(CAFE_BP, 0), _cafe_card(), archetype="A")
    assert [(l["label"], l["href"]) for l in spec["navbar"]["links"]] == [
        ("메뉴", "#offerings-title-menu"), ("공간", "#gallery-title-space"),
        ("오시는 길", "#around-title-around")]
    assert spec["navbar"]["cta"] == {"label": "길찾기", "href": "#around-title-around"}
    pickup = copy.deepcopy(CAFE_BP)
    pickup["primary"] = {"label": "주문하기", "target": "order-soon"}
    pickup["strategies"][0]["sections"].append(
        {"id": "order-soon", "type": "order", "variant": "soon", "bind": "order_soon"})
    got = site_data.resolve(site_data.skeleton(pickup, 0), _cafe_card(), archetype="A")
    assert got["navbar"]["cta"] == {"label": "주문하기", "href": "#order-soon"}
    assert _section(got, "catalog")["content"]["order"] is True
    soon = _section(got, "order_soon")["content"]
    assert soon["return_href"] == "#offerings-title-menu" and soon["phone"] == "02-123-4567"


def test_all_sections_pass_render_contract():
    for blueprint, card, archetype in ((CAFE_BP, _cafe_card(), "A"), (SALON_BP, _salon_card(), "B")):
        spec = site_data.resolve(site_data.skeleton(blueprint, 0), card, archetype=archetype)
        allowed = set(SR.list_variants())
        for sec in spec["sections"]:
            assert f"{sec['type']}--{sec['variant']}" in allowed
        SR.render_site(spec)
        SR.render_site(spec, public=True)


def test_location_items_show_phone_and_hours():
    """J5: call-first를 뺀 대신 around--map에 FILLED 전화·영업시간을 넣는다."""
    spec = site_data.resolve(site_data.skeleton(CAFE_BP, 0), _cafe_card(), archetype="A")
    items = _section(spec, "location")["content"]["items"]
    assert {"name": "전화", "note": "02-123-4567"} in items
    assert {"name": "영업시간", "note": "매일 10~21시"} in items
    card = _cafe_card()
    del card["slots"]["phone"]
    spec = site_data.resolve(site_data.skeleton(CAFE_BP, 0), card, archetype="A")
    items = _section(spec, "location")["content"]["items"]
    assert all(i["name"] != "전화" for i in items)
    assert {"name": "영업시간", "note": "매일 10~21시"} in items
    SR.render_site(spec)


MENU_PHOTOS_BP = {
    "archetype": "A", "mode": "pickup",
    "primary": {"label": "주문하기", "target": "order-soon"},
    "tokens": CAFE_TOKENS,
    "strategies": [{
        "id": "v3", "name": "빠른 주문형", "journey": "메뉴 고르고 → 바로 주문", "tone": "calm",
        "hero": "photo-side",
        "sections": [
            {"id": "today-menu", "type": "gallery", "variant": "marquee",
             "bind": "menu_photos", "label": "오늘의 메뉴"},
        ],
    }],
}


def test_menu_photos_uses_owner_first_then_category_pack():
    """J5: menu_photos는 사장님 사진 우선, 없으면 분류 대표 예시 팩 + ai 표시."""
    spec = site_data.resolve(site_data.skeleton(MENU_PHOTOS_BP, 0), _cafe_card(), archetype="A")
    items = _section(spec, "menu_photos")["content"]["items"]
    assert items and all(i.get("ai") is True for i in items)
    assert {i["src"] for i in items} >= {
        "/art/ex/cafe-coffee.webp", "/art/ex/cafe-drink.webp", "/art/ex/cafe-dessert.webp"}
    card = _cafe_card()
    card["photos"] = [{"url": "/uploads/lab-x/p1.jpg", "caption": "대표 사진"},
                      {"url": "/uploads/lab-x/p2.jpg", "caption": "라떼"}]
    spec = site_data.resolve(site_data.skeleton(MENU_PHOTOS_BP, 0), card, archetype="A")
    items = _section(spec, "menu_photos")["content"]["items"]
    assert items[0]["src"] == "/uploads/lab-x/p2.jpg"
    assert all("ai" not in i for i in items)
    SR.render_site(spec)


ACADEMY_DATA = {
    "version": 1, "mode": "", "primary_action": "consult",
    "catalog": [],
    "staff": [{"name": "김믿음", "role": "원장", "specialties": ["초등"], "source": "owner"}],
    "classes": [
        {"name": "초등 파닉스반", "target": "초등", "days": "월·수", "time": "16:00",
         "capacity": "8명", "fee": "월 18만원", "source": "owner"},
        {"name": "초등 리딩반", "target": "초등", "days": "금", "time": "16:00",
         "capacity": "", "fee": "", "source": "owner"},
    ],
    "rooms": [], "schedule": None,
}

PENSION_DATA = {
    "version": 1, "mode": "", "primary_action": "reserve",
    "catalog": [], "staff": [],
    "classes": [],
    "rooms": [
        {"name": "101호 복층", "capacity": "기준 4인", "price": "1박 18만원",
         "source": "owner", "features": ["복층"]},
        {"name": "201호", "capacity": "", "price": "", "source": "owner"},
    ],
    "schedule": None,
}


def _academy_card():
    return {
        "slots": {"shop_name": _slot("믿음영어"), "phone": _slot("02-777-8888"),
                  "hours": _slot("평일 14~22시"), "location": _slot("서울 노원구 상계로 77")},
        "copy": {},
        "data": copy.deepcopy(ACADEMY_DATA),
    }


def _pension_card():
    return {
        "slots": {"shop_name": _slot("숲속의 쉼"), "phone": _slot("033-000-1111"),
                  "hours": _slot("입실 15시·퇴실 11시"), "location": _slot("강원 평창군 봉평면")},
        "copy": {},
        "data": copy.deepcopy(PENSION_DATA),
    }


def _bind_bp(bind, section_type="classes", variant="cards", label="반 안내", **extra):
    node = {"id": "x", "type": section_type, "variant": variant,
            "bind": bind, "label": label, "nav": label}
    node.update(extra)
    return {
        "archetype": "D",
        "primary": {"label": "상담 신청", "target": "booking"},
        "tokens": dict(CAFE_TOKENS),
        "strategies": [{
            "id": "v1", "name": "형", "journey": "보기 → 상담", "tone": "calm",
            "hero": "photo-overlay",
            "sections": [
                node,
                {"id": "booking", "type": "booking", "variant": "slots",
                 "bind": "booking", "label": "상담 예약"},
            ],
        }],
    }


def test_classes_fee_owner_first_example_marked():
    """J5b: 수강료는 사장님 값 우선, 모르면 예시 파일 값 + fee_example."""
    spec = site_data.resolve(site_data.skeleton(_bind_bp("classes"), 0), _academy_card(), archetype="D")
    got = {c["name"]: c for c in _section(spec, "classes")["content"]["classes"]}
    assert got["초등 파닉스반"]["fee"] == "월 18만원" and "fee_example" not in got["초등 파닉스반"]
    assert got["초등 리딩반"]["fee"] == "월 15만원" and got["초등 리딩반"]["fee_example"] is True
    assert _section(spec, "classes")["content"]["cta_href"] == "#booking-title-booking"
    SR.render_site(spec)


def test_timetable_from_classes_and_example_fallback():
    """J5b: 시간표는 반 요일·시간으로, 없으면 예시 표 + example."""
    spec = site_data.resolve(
        site_data.skeleton(_bind_bp("timetable", "timetable", "week", "시간표"), 0),
        _academy_card(), archetype="D")
    table = _section(spec, "timetable")["content"]
    assert table["days"] == ["월", "수", "금"] and "example" not in table
    assert table["rows"][0]["time"] == "16:00"
    assert table["rows"][0]["cells"][0] == {"day": "월", "text": "초등 파닉스반"}
    card = _academy_card()
    card["data"]["classes"] = []
    spec = site_data.resolve(
        site_data.skeleton(_bind_bp("timetable", "timetable", "week", "시간표"), 0),
        card, archetype="D")
    table = _section(spec, "timetable")["content"]
    assert table["example"] is True and table["rows"]
    SR.render_site(spec)


def test_rooms_image_and_price_example():
    """J5b: 객실은 예시 사진 + image_example, 모르는 요금은 예시 값 + price_example."""
    spec = site_data.resolve(
        site_data.skeleton(_bind_bp("rooms", "rooms", "cards", "객실"), 0),
        _pension_card(), archetype="C")
    content = _section(spec, "rooms")["content"]
    first, second = content["rooms"]
    assert first["price"] == "1박 18만원" and "price_example" not in first
    assert first["image"] == "/art/ex/pension-room1.webp" and first["image_example"] is True
    assert second.get("price", "") == "" and "price_example" not in second
    assert content["booking_href"] == "#booking-title-booking"
    SR.render_site(spec)


def test_dates_fourteen_example_days():
    """J5b: 입실일은 예시 14일 + days_example, 객실 이름, nights_max 3."""
    spec = site_data.resolve(
        site_data.skeleton(_bind_bp("dates", "booking", "dates", "예약"), 0),
        _pension_card(), archetype="C")
    content = _section(spec, "dates")["content"]
    assert len(content["days"]) == 14 and content["days_example"] is True
    assert content["rooms"] == ["101호 복층", "201호"] and content["nights_max"] == 3
    assert {d["state"] for d in content["days"]} <= {"open", "few", "full"}
    SR.render_site(spec)


def test_concerns_example_three():
    """J5b: 고민은 예시 파일 3개, who는 예시."""
    spec = site_data.resolve(
        site_data.skeleton(_bind_bp("concerns", "concerns", "bubbles", "고민"), 0),
        _academy_card(), archetype="D")
    content = _section(spec, "concerns")["content"]
    assert len(content["items"]) == 3
    assert all(i["who"] == "예시" and i["quote"] for i in content["items"])
    SR.render_site(spec)


def test_staff_variant_follows_count_and_optional_drop():
    """J5b: 선생님 1명 solo·2명 이상 team, 없으면 optional 섹션 없음."""
    solo = site_data.resolve(
        site_data.skeleton(_bind_bp("staff", "staff", "solo", "선생님", optional=True), 0),
        _academy_card(), archetype="D")
    assert _section(solo, "staff")["variant"] == "solo"
    card = _academy_card()
    card["data"]["staff"].append(
        {"name": "이열심", "role": "강사", "specialties": ["중등"], "source": "owner"})
    team = site_data.resolve(
        site_data.skeleton(_bind_bp("staff", "staff", "solo", "선생님", optional=True), 0),
        card, archetype="D")
    assert _section(team, "staff")["variant"] == "team"
    assert [m["name"] for m in _section(team, "staff")["content"]["members"]] == ["김믿음", "이열심"]
    empty = _academy_card()
    empty["data"]["staff"] = []
    dropped = site_data.resolve(
        site_data.skeleton(_bind_bp("staff", "staff", "solo", "선생님", optional=True), 0),
        empty, archetype="D")
    assert [s.get("bind") for s in dropped["sections"]] == ["hero", "booking"]
    SR.render_site(dropped)


def test_signature_picks_first_per_category_max_three():
    """J5b: 시그니처는 분류마다 첫 품목, 최대 3개, 분류 사진·가격."""
    spec = site_data.resolve(
        site_data.skeleton(_bind_bp("signature", "offerings", "cards", "시그니처"), 0),
        _cafe_card(), archetype="A")
    content = _section(spec, "signature")["content"]
    assert content["label"] == "시그니처"
    assert [i["name"] for i in content["items"]] == ["아메리카노", "유자에이드", "바스크치즈케이크"]
    assert all(i.get("image", "").startswith("/art/ex/") for i in content["items"])
    SR.render_site(spec)
