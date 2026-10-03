"""항목 판단 엔진 (COMPOSE_INTERVIEW_CONTRACT §10): 사진 필요·모양·손님 행동·후기를 이유와 함께."""
from app.services import item_plan as P
from app.services import prd_engine as E
from app.services import prd_schema as S


def mk(ind, bt, items, prices=None, said=None, commerce=None):
    card = E.new_card(ind)
    E._put(card, "business_type", bt, S.FILLED, 1)
    E._put(card, "offerings", items, S.FILLED, 1)
    card["price_pairs"] = prices or {}
    card["said"] = said or []
    if commerce:
        card["commerce"] = commerce
    return card


def test_few_menu_items_get_photo_carousel():
    d = P.decide(mk("cafe", "카페", ["아메리카노", "라떼", "케이크"]))
    assert (d["kind"], d["photo"], d["layout"]) == ("menu", "each", "cards")
    assert d["commerce"]["level"] == "info" and d["commerce"]["ask"] and d["reviews"]
    assert any("캐러셀" in r for r in d["reasons"])


def test_many_menu_items_get_menu_board_with_signature_photos():
    d = P.decide(mk("restaurant", "고깃집", [f"메뉴{i}" for i in range(12)]))
    assert (d["photo"], d["layout"]) == ("signature", "categories")
    assert any("대표 3개" in r for r in d["reasons"])


def test_salon_services_need_no_item_photos_and_book():
    d = P.decide(mk("salon", "미용실", ["컷트", "펌"], {"컷트": "2만원", "펌": "8만원"}))
    assert (d["kind"], d["photo"], d["layout"]) == ("service", "none", "list-price")
    assert d["commerce"]["level"] == "book" and not d["commerce"]["ask"]
    assert "duration" in d["fields"]


def test_rooms_always_have_photos_and_booking():
    d = P.decide(mk("pension", "펜션", ["101호", "102호"]))
    assert (d["kind"], d["photo"], d["layout"], d["commerce"]["level"]) == ("room", "each", "rooms", "book")


def test_order_words_infer_order_and_missing_prices_block_ready():
    d = P.decide(mk("cafe", "카페", ["아메리카노", "라떼"], {"아메리카노": "4500원"}, said=["포장 주문도 받아요"]))
    assert d["commerce"]["level"] == "order" and not d["commerce"]["ask"]
    assert not d["commerce"]["ready"] and d["commerce"]["missing_price"] == ["라떼"]


def test_pay_and_explicit_choice():
    assert P.decide(mk("cafe", "카페", ["라떼"], said=["카드 결제까지 받고 싶어요"]))["commerce"]["level"] == "pay"
    d = P.decide(mk("cafe", "카페", ["라떼"], commerce="book"))
    assert d["commerce"]["level"] == "book" and d["commerce"]["explicit"]


def test_item_action_only_when_owner_chose():
    assert P.item_action(mk("cafe", "카페", ["라떼"])) is None  # 기존 시안에는 단추를 붙이지 않는다
    assert P.item_action(mk("cafe", "카페", ["라떼"], commerce="pay")) == {"kind": "order", "label": "주문하기"}


def test_same_card_same_decision():
    card = mk("cafe", "카페", ["아메리카노", "라떼"])
    assert P.decide(card) == P.decide(card)
