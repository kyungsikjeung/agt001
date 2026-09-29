"""프로필 깊이 A1 (가격 숫자·시술 시간). DB 없이 돌아간다."""
from app.services import card_data
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services.botmaker import seed


def test_price_won_table():
    cases = {
        "2만원": 20000,
        "8만5천원": 85000,
        "8만 5천원": 85000,
        "25,000원": 25000,
        "4500원": 4500,
        "1박 25만원": 250000,
        "3만원": 30000,
        "만원": 10000,
    }
    for text, want in cases.items():
        assert card_data.price_won(text) == want, text
    assert card_data.price_won("2만원~3만원") is None
    assert card_data.price_won("") is None
    assert card_data.price_won("문의 주세요") is None


def test_record_duration_pairs():
    card = E.new_card("salon")
    E._record_duration_pairs(card, "컷 2만원 30분, 펌 8만원 2시간 반, 염색은 1시간반")
    assert card["duration_pairs"] == {"컷": 30, "펌": 150, "염색": 90}


def test_record_duration_pairs_ignores_hours():
    card = E.new_card("salon")
    E._record_duration_pairs(card, "10시~19시 영업")
    assert card.get("duration_pairs") in (None, {})


def _salon_card():
    card = E.new_card("salon")
    E._put(card, "offerings", ["컷", "펌"], S.FILLED, 1)
    card["price_pairs"] = {"컷": "2만원", "펌": "8만원"}
    card["duration_pairs"] = {"컷": 30, "펌": 150}
    return card


def test_catalog_has_price_won_and_duration():
    data = card_data.build(_salon_card())
    got = {i["name"]: i for cat in data["catalog"] for i in cat["items"]}
    assert got["컷"]["price_won"] == 20000 and got["컷"]["duration_min"] == 30
    assert got["펌"]["price_won"] == 80000 and got["펌"]["duration_min"] == 150


def test_seed_prefills_duration_and_price():
    spec = seed(_salon_card())
    perm = {s["name"]: s for s in spec.get("services") or []}["펌"]
    assert perm["duration_min"] == 150 and perm["price"] == 80000


def test_apply_updates_records_durations():
    card = E.new_card("salon")
    card["turn"] = 1
    E.apply_updates(card, [{"slot": "offerings", "value": "컷, 펌"}],
                    "컷 2만원 30분, 펌 8만원 2시간 반")
    assert card["duration_pairs"] == {"컷": 30, "펌": 150}


def test_duration_pairs_only_for_salon():
    card = E.new_card("cafe")
    card["turn"] = 1
    E._record_duration_pairs(card, "역에서 10분 거리예요")
    assert not card.get("duration_pairs")
