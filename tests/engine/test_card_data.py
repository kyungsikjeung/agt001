"""카드 구조 데이터 (BUILD_W1_W2 §1.1) 시험. DB 없이 돌아간다."""
from app.services import card_data
from app.services import prd_engine as E
from app.services import prd_schema as S


def _card(industry, **slots):
    card = E.new_card(industry)
    for key, value in slots.items():
        E._put(card, key, value, S.FILLED, 1)
    card["turn"] = 1
    return card


def test_price_pairs_saved_and_menu_split():
    card = _card("cafe")
    text = "아메리카노 4,500원, 카페라떼 5,000원이에요"
    E.apply_updates(card, [{"slot": "offerings", "value": "아메리카노 4,500원, 카페라떼 5,000원"}], text)
    assert card["price_pairs"] == {"아메리카노": "4,500원", "카페라떼": "5,000원"}
    assert E._slot(card, "offerings")["value"] == ["아메리카노", "카페라떼"]


def test_price_not_in_text_not_paired():
    card = _card("cafe")
    E.apply_updates(card, [{"slot": "offerings", "value": "아메리카노 9,999원"}], "아메리카노 주세요")
    assert card.get("price_pairs") in (None, {})


def test_cafe_catalog_categories():
    card = _card("cafe", offerings=["아메리카노", "딸기라떼", "유자에이드", "바스크치즈케이크", "감자샐러드"])
    card["price_pairs"] = {"아메리카노": "4,500원"}
    data = card_data.build(card)
    cats = {c["name"]: c for c in data["catalog"]}
    assert cats["커피"]["items"][0]["name"] == "아메리카노"
    assert cats["커피"]["items"][0]["price"] == "4,500원"
    assert [i["name"] for i in cats["음료"]["items"]] == ["딸기라떼", "유자에이드"]
    assert [i["name"] for i in cats["디저트"]["items"]] == ["바스크치즈케이크"]
    assert [i["name"] for i in cats["메뉴"]["items"]] == ["감자샐러드"]
    assert all(c["source"] == "assumed" for c in data["catalog"])
    assert all(i["source"] == "owner" for c in data["catalog"] for i in c["items"])


def test_salon_staff_parsing_and_mode():
    solo = _card("salon", staff=["원장 김미용(컷·펌)"])
    data = card_data.build(solo)
    assert data["staff"] == [{"name": "김미용", "role": "원장", "specialties": ["컷", "펌"], "source": "owner"}]
    assert data["mode"] == "solo"
    assert data["primary_action"] == "reserve"
    team = _card("salon", staff=["원장 김미용(컷)", "실장 박하나(염색)"])
    assert card_data.build(team)["mode"] == "team"


def test_cafe_contact_mode():
    pickup = _card("cafe", contact_method="픽업 주문")
    assert card_data.build(pickup)["mode"] == "pickup"
    assert card_data.build(pickup)["primary_action"] == "order"
    plain = _card("cafe")
    assert card_data.build(plain)["mode"] == "dinein"
    assert card_data.build(plain)["primary_action"] == "visit"


def test_academy_classes_parsed():
    """J5b: 학원 offerings → 반 (이름·대상·요일·시간·정원·수강료)."""
    card = _card("academy", offerings=["초등 파닉스반 월수 16시 8명", "중등 내신반 화목 오후 6시 정원 10명"],
                target="초등·중학생")
    card["price_pairs"] = {"초등 파닉스반": "월 18만원", "중등 내신반": "월 24만원"}
    classes = card_data.build(card)["classes"]
    assert classes[0] == {"name": "초등 파닉스반", "target": "초등", "days": "월·수",
                          "time": "16:00", "capacity": "8명", "fee": "월 18만원", "source": "owner"}
    assert classes[1]["days"] == "화·목" and classes[1]["time"] == "18:00"
    assert classes[1]["capacity"] == "10명" and classes[1]["fee"] == "월 24만원"


def test_academy_class_without_detail_keeps_name():
    """J5b: 토막이 없으면 이름 그대로, 빈 값은 비워 둔다."""
    card = _card("academy", offerings=["토익반"], target="성인")
    classes = card_data.build(card)["classes"]
    assert classes == [{"name": "토익반", "target": "성인", "days": "", "time": "",
                        "capacity": "", "fee": "", "source": "owner"}]


def test_pension_rooms_parsed():
    """J5b: 펜션 offerings → 객실 (이름·인원·요금)."""
    card = _card("pension", offerings=["101호 복층 4인", "102호(온돌)(4인)", "바베큐장"])
    card["price_pairs"] = {"101호 복층": "18만원", "102호": "12만원"}
    rooms = card_data.build(card)["rooms"]
    assert rooms[0]["name"] == "101호 복층" and rooms[0]["capacity"] == "4인"
    assert rooms[0]["price"] == "18만원" and rooms[0]["source"] == "owner"
    assert rooms[1]["name"] == "102호" and rooms[1]["capacity"] == "(4인)"
    assert len(rooms) == 2  # 바베큐장 같은 부대시설은 객실 카드("이 객실 예약")가 아니다


def test_other_archetypes_have_no_classes_or_rooms():
    card = _card("cafe", offerings=["아메리카노"])
    data = card_data.build(card)
    assert data["classes"] == [] and data["rooms"] == []


def test_one_syllable_menu_keeps_price_pair():
    # 미용실 "컷 2만원, 펌 8만원": 한 글자 품목도 가격 짝이 생겨야 한다(실제 대화 경로)
    from app.services import prd_engine as E
    card = E.new_card("salon")
    text = "컷 2만원, 펌 8만원이에요"
    E.apply_updates(card, [{"slot": "offerings", "value": "컷 2만원, 펌 8만원"}], text)
    assert card["price_pairs"] == {"컷": "2만원", "펌": "8만원"}
    # 품목이 아닌 한 글자는 여전히 버린다
    menu, price = E._cut_price("총 5만원")
    assert price is None
