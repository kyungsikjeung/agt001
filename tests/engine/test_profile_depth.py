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
        "3천5백원": 3500,
        "1만2천5백원": 12500,
        "5백원": 500,
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


def test_academy_notes_fill_classes():
    card = E.new_card("academy")
    card["turn"] = 1
    E._put(card, "offerings", ["초등반", "중등 수학반"], S.FILLED, 1)
    E.apply_updates(card, [], "초등반 화목 4시 월 20만원, 중등 수학반 월수금 저녁 7시 정원 8명 월 25만원")
    got = {c["name"]: c for c in card_data.build(card)["classes"]}
    assert got["초등반"]["days"] == "화·목" and got["초등반"]["time"] == "16:00"
    assert got["초등반"]["price_won"] == 200000  # '월 20만원'의 '월'은 요일이 아니다
    assert got["중등 수학반"]["days"] == "월·수·금" and got["중등 수학반"]["capacity"] == "8명"


def test_pension_notes_fill_rooms():
    card = E.new_card("pension")
    card["turn"] = 1
    E._put(card, "offerings", ["바다방", "101호 (오션뷰)"], S.FILLED, 1)
    E.apply_updates(card, [], "바다방 2인 12만원, 101호 4인 18만원(성수기 25만원), 입실 15시 퇴실 11시")
    got = {r["name"]: r for r in card_data.build(card)["rooms"]}
    assert got["바다방"]["capacity"] == "2인" and got["바다방"]["price_won"] == 120000
    assert got["101호"]["capacity"] == "4인" and got["101호"]["price_won"] is None  # 금액 둘이면 비움
    assert not any("입실" in k for k in card["item_notes"])


def test_item_notes_not_for_cafe():
    card = E.new_card("cafe")
    card["turn"] = 1
    E._record_item_notes(card, "아메리카노 4,500원")
    assert not card.get("item_notes")


def test_summary_has_numbered_item_table():
    text = E.summary_text(_salon_card())
    assert "  1. 컷 — 2만원 · 30분" in text and "  2. 펌 — 8만원 · 2시간 30분" in text


def test_correct_item_row_price_and_duration():
    card = _salon_card()
    assert E.correct_item_row(card, "2번째 줄 가격 9만원, 3시간 걸려요") == "2번 펌 가격·시간"
    assert card["price_pairs"]["펌"] == "9만원" and card["duration_pairs"]["펌"] == 180
    assert E.correct_item_row(card, "첫 번째 메뉴 2만5천원으로 고쳐 주세요") == "1번 컷 가격"
    assert card_data.build(card)["catalog"][0]["items"][0]["price_won"] == 25000


def test_correct_item_row_ignores_other_numbers():
    card = _salon_card()
    assert E.correct_item_row(card, "역 2번 출구에서 5분이에요") is None
    assert E.correct_item_row(card, "9번 가격 1만원") is None  # 없는 줄
    assert E.correct_item_row(card, "2번 출구 앞이에요") is None  # 값이 없다
