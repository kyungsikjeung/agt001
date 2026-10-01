"""객실·항목 카드 (BETA_FLOW §2.5 + §2.7 사진 순서·가로 스크롤). DB 없이 돌아간다."""
import datetime
import re

from app.services import archetype
from app.services import card_data
from app.services import design_variants as DV
from app.services import palette as PAL
from app.services import prd_engine as E
from app.services import prd_schema as S
from app.services import site_data
from app.services import site_render as SR


def _card(industry="pension", **slots):
    card = E.new_card(industry)
    for key, value in slots.items():
        E._put(card, key, value, S.FILLED, 1)
    card["turn"] = 1
    return card


def _page(card, public=False):
    bp = archetype.load("C")
    spec = site_data.resolve(site_data.skeleton(bp, 0), card, archetype="C")
    spec["tokens"]["palette"] = PAL.pick("C", 1)
    return SR.render_site(spec, site_key="test-rooms", title=DV.title_for(card),
                          kind=DV.kind_for(card), public=public)


def _price_card(**slots):
    base = {"business_type": "펜션", "shop_name": "숲속의 쉼",
            "offerings": ["객실 4개"]}
    base.update(slots)
    return _card("pension", **base)


# ---- 객실 수 세기 ----

def test_room_count_expands_to_numbered_rooms():
    for text in ("객실 4개", "방 4개", "4개 객실", "객실 4"):
        rooms = card_data.build(_card("pension", offerings=[text]))["rooms"]
        assert [r["name"] for r in rooms] == ["객실 1", "객실 2", "객실 3", "객실 4"]
        assert all(r["numbered"] is True and r["source"] == "owner" for r in rooms)


def test_room_count_caps_at_eight():
    rooms = card_data.build(_card("pension", offerings=["객실 10개"]))["rooms"]
    assert len(rooms) == 8 and rooms[-1]["name"] == "객실 8"


def test_named_rooms_unchanged():
    rooms = card_data.build(_card("pension", offerings=["101호 복층 4인"]))["rooms"]
    assert len(rooms) == 1 and rooms[0]["name"] == "101호 복층"
    assert "numbered" not in rooms[0]


# ---- 요금 읽기 ----

def test_season_prices_with_periods():
    prices = card_data.season_prices(
        _card("pension", price="성수기(7/15~8/20) 1박 25만원, 비수기 1박 15만원"))
    assert prices == [{"label": "성수기", "price": "1박 25만원", "period": "7/15~8/20"},
                      {"label": "비수기", "price": "1박 15만원", "period": ""}]


def test_season_prices_korean_date_period():
    prices = card_data.season_prices(
        _card("pension", price="성수기(7월 15일~8월 20일) 1박 25만원"))
    assert prices[0]["period"] == "7/15~8/20"


def test_season_prices_amount_forms():
    assert card_data.season_prices(_card("pension", price="250,000원")) == [
        {"label": "", "price": "250,000원"}]
    assert card_data.season_prices(_card("pension", price="성수기 25만원")) == [
        {"label": "성수기", "price": "25만원", "period": "7/15~8/20"}]
    assert card_data.season_prices(_card("pension", price="극성수기 1박 30만원"))[0] == {
        "label": "극성수기", "price": "1박 30만원", "period": "7/25~8/10"}
    assert card_data.season_prices(_card("pension", price="준성수기 1박 20만원"))[0]["period"] == ""
    assert card_data.season_prices(_card("pension", price="평일 1박 10만원"))[0]["label"] == "주중"


def test_season_prices_amount_only():
    assert card_data.season_prices(_card("pension", price="1박 15만원")) == [
        {"label": "", "price": "1박 15만원"}]
    assert card_data.season_prices(_card("pension")) == []


# ---- 지금 요금 ----

def test_current_label_inside_and_outside():
    prices = [{"label": "성수기", "price": "1박 25만원", "period": "7/15~8/20"},
              {"label": "비수기", "price": "1박 15만원", "period": ""}]
    assert card_data.current_label(prices, datetime.date(2026, 8, 1)) == "성수기"
    assert card_data.current_label(prices, datetime.date(2026, 10, 1)) == "비수기"


def test_current_label_wrapping_period():
    prices = [{"label": "비수기", "price": "1박 12만원", "period": "12/20~2/10"}]
    assert card_data.current_label(prices, datetime.date(2026, 1, 15)) == "비수기"
    assert card_data.current_label(prices, datetime.date(2026, 3, 1)) == "비수기"


def test_current_label_peak_before_high():
    prices = [{"label": "성수기", "price": "1박 25만원", "period": "7/15~8/20"},
              {"label": "극성수기", "price": "1박 30만원", "period": "7/25~8/10"}]
    assert card_data.current_label(prices, datetime.date(2026, 8, 1)) == "극성수기"
    assert card_data.current_label(prices, datetime.date(2026, 7, 20)) == "성수기"


def test_current_label_weekday_weekend():
    prices = [{"label": "주중", "price": "1박 10만원", "period": ""},
              {"label": "주말", "price": "1박 15만원", "period": ""}]
    assert card_data.current_label(prices, datetime.date(2026, 10, 2)) == "주말"  # 금요일
    assert card_data.current_label(prices, datetime.date(2026, 9, 28)) == "주중"  # 월요일
    assert card_data.current_label([], datetime.date(2026, 9, 28)) == ""


# ---- 렌더링 ----

def test_rendered_pension_has_scroll_cards_and_price_table():
    doc = _page(_price_card(price="성수기 1박 25만원, 비수기 1박 15만원"))
    assert doc.count('<li class="s-room">') == 4
    assert "s-rooms__list--scroll" in doc
    assert 'aria-label="객실 4개, 옆으로 넘겨 보세요"' in doc
    assert "옆으로 넘겨 보세요 → (4개)" in doc
    assert "<script" not in doc.lower()
    tables = re.findall(r'<table class="s-room__prices".*?</table>', doc, re.S)
    assert len(tables) == 4
    for table in tables:
        assert table.count('class="is-current"') == 1
        assert table.count("지금 적용") == 1
    assert 'data-from="07-15" data-to="08-20"' in doc


def test_rendered_public_has_script_and_single_current():
    doc = _page(_price_card(price="성수기 1박 25만원, 비수기 1박 15만원"), public=True)
    assert doc.count('<li class="s-room">') == 4
    assert "s-rooms__list--scroll" in doc
    assert 'aria-label="객실 4개, 옆으로 넘겨 보세요"' in doc
    assert "Asia/Seoul" in doc
    scripts = re.findall(r"<script>.*?</script>", doc, re.S)
    assert len(scripts) == 1
    assert len(scripts[0].strip().splitlines()) <= 20
    assert "src=" not in scripts[0]


def test_rendered_weekend_rows_have_dow():
    doc = _page(_price_card(price="주중 1박 10만원, 주말 1박 15만원"))
    assert 'data-dow="5,6"' in doc and 'data-dow="0,1,2,3,4"' in doc


# ---- 항목 사진 순서 ----

def test_item_photo_tag_and_caption():
    card = _card("pension", offerings=["객실 2개"])
    card["photos"] = [{"url": "/uploads/a.jpg", "tag": "item:객실 1"},
                      {"url": "/uploads/b.jpg", "caption": "객실 2 전경"}]
    assert card_data.item_photo(card, "객실 1")["url"] == "/uploads/a.jpg"
    assert card_data.item_photo(card, "객실 2")["url"] == "/uploads/b.jpg"
    assert card_data.item_photo(card, "객실 3") is None


def test_room_photo_owner_ai_example_order():
    card = _price_card(price="성수기 1박 25만원, 비수기 1박 15만원")
    card["photos"] = [{"url": "/uploads/r1.jpg", "tag": "item:객실 1"}]
    card["ai_images"] = {"item:객실 2": {"url": "/uploads/ai2.jpg"}}
    doc = _page(card)
    assert "/uploads/r1.jpg" in doc
    assert "/uploads/ai2.jpg" in doc and "AI 예시" in doc
    assert "/art/ex/pension-room2.webp" in doc and "예시 이미지" in doc


def test_gallery_uses_item_tag_as_caption():
    card = _price_card()
    card["photos"] = [{"url": "/uploads/hero.jpg", "caption": "대표 사진"},
                      {"url": "/uploads/perm.jpg", "tag": "item:펌"}]
    bp = archetype.load("C")
    spec = site_data.resolve(site_data.skeleton(bp, 1), card, archetype="C")
    gallery = next(s for s in spec["sections"] if s.get("bind") == "space_photos")
    captions = [i["caption"] for i in gallery["content"]["items"]]
    assert "펌" in captions


# ---- 펜션 요금 질문 ----

def test_pension_price_question():
    pension = S.INDUSTRIES["pension"]
    assert "price" in pension.required
    question = S.question_for(pension, "price")
    assert question.ask == ("객실 요금을 알려 주세요. 성수기·비수기가 다르면 둘 다 알려 주세요. "
                            "(예: 성수기 1박 25만원, 비수기 1박 15만원)")
    assert question.options == ("나중에 넣을게요",)


def _messy_card(features="성수기 기간: 7월 15일 ~ 8월 20일"):
    card = _price_card(offerings=["객실 4개", "성수기 1박", "비수기 1박"],
                       price="25만원, 15만원",
                       features=[features])
    card["price_pairs"] = {"성수기 1박": "25만원", "비수기 1박": "15만원"}
    return card


def test_messy_llm_split_rooms():
    rooms = card_data.build(_messy_card())["rooms"]
    assert [r["name"] for r in rooms] == ["객실 1", "객실 2", "객실 3", "객실 4"]
    for room in rooms:
        assert [p["label"] for p in room["prices"]] == ["성수기", "비수기"]
        assert [p["price"] for p in room["prices"]] == ["1박 25만원", "1박 15만원"]
    assert rooms[0]["prices"][0]["period"] == "7/15~8/20"


def test_season_period_from_features_overrides_default():
    rooms = card_data.build(_messy_card("성수기 기간: 7월 1일 ~ 8월 31일"))["rooms"]
    assert rooms[0]["prices"][0]["period"] == "7/1~8/31"


def test_features_period_not_from_longer_label():
    card = _price_card(price="성수기 1박 25만원",
                       features=["극성수기 기간: 7월 25일 ~ 8월 10일"])
    prices = card_data.season_prices(card)
    assert prices[0]["period"] == "7/15~8/20"


def test_room_number_with_season_word_kept():
    rooms = card_data.build(_card("pension", offerings=["101호 주말특가"]))["rooms"]
    assert len(rooms) == 1


def test_messy_split_page_has_price_table():
    html = _page(_messy_card())
    assert "[요금 입력]" not in html
    assert ">성수기 1박<" not in html
    assert "25만원" in html


# ---- 대화 단계에서 요금 이름표 모으기 (F2) ----

_SEASON_SAID = ("객실 4개고요, 성수기 1박 25만원, 비수기 1박 15만원이에요. "
                "성수기는 7월 15일부터 8월 20일까지예요")


def _apply(text, updates, card=None):
    card = card or E.new_card("pension")
    card["turn"] = card.get("turn", 0) + 1
    card.setdefault("said", []).append(text)
    applied = E.apply_updates(card, updates, text)
    return card, applied


def test_messy_extraction_folds_into_price():
    card, applied = _apply(_SEASON_SAID, [
        {"slot": "offerings", "value": ["객실 4개", "성수기 1박", "비수기 1박"]},
        {"slot": "price", "value": "25만원, 15만원"},
        {"slot": "features", "value": ["성수기 기간: 7월 15일 ~ 8월 20일"]}])
    assert card["slots"]["offerings"]["value"] == ["객실 4개"]
    assert card["slots"]["price"]["value"] == "성수기(7/15~8/20) 1박 25만원, 비수기 1박 15만원"
    assert "features" not in card["slots"]
    assert not card.get("features_judged")
    assert not (card.get("notes") or {}).get("items")
    assert "price" in applied
    summary = E.summary_text(card)
    assert "객실 구성: 객실 4개\n" in summary
    assert "성수기 기간" not in summary
    assert card_data.season_prices(card)[0] == {
        "label": "성수기", "price": "1박 25만원", "period": "7/15~8/20"}


def test_messy_extraction_without_pairs_uses_price_order():
    card, _ = _apply("객실 3개, 성수기 1박 20만원 비수기 1박 12만원", [
        {"slot": "offerings", "value": ["객실 3개", "성수기 1박", "비수기 1박"]},
        {"slot": "price", "value": "20만원, 12만원"}])
    card.pop("price_pairs", None)
    card["slots"]["offerings"]["value"] = ["객실 3개", "성수기 1박", "비수기 1박"]
    card["slots"]["price"]["value"] = "20만원, 12만원"
    assert E._fold_season_rates(card, 2, None)
    assert card["slots"]["price"]["value"] == "성수기 1박 20만원, 비수기 1박 12만원"
    assert card["slots"]["offerings"]["value"] == ["객실 3개"]


def test_labeled_price_kept_and_offering_label_dropped():
    card, _ = _apply("객실 2개, 성수기 1박 25만원, 비수기 1박 15만원", [
        {"slot": "offerings", "value": ["객실 2개", "성수기"]},
        {"slot": "price", "value": "성수기 1박 25만원, 비수기 1박 15만원"}])
    assert card["slots"]["offerings"]["value"] == ["객실 2개"]
    assert card["slots"]["price"]["value"] == "성수기 1박 25만원, 비수기 1박 15만원"


def test_season_period_later_turn():
    card, _ = _apply("객실 4개, 성수기 1박 25만원, 비수기 1박 15만원", [
        {"slot": "offerings", "value": ["객실 4개"]},
        {"slot": "price", "value": "성수기 1박 25만원, 비수기 1박 15만원"}])
    card, _ = _apply("성수기는 7월 1일부터 8월 31일까지예요", [
        {"slot": "features", "value": ["성수기 기간: 7월 1일 ~ 8월 31일"]}], card)
    assert card["slots"]["price"]["value"] == "성수기(7/1~8/31) 1박 25만원, 비수기 1박 15만원"
    assert "features" not in card["slots"]


def test_named_room_and_other_industry_untouched():
    card, _ = _apply("101호 주말특가 있어요, 1박 15만원", [
        {"slot": "offerings", "value": ["101호 주말특가"]},
        {"slot": "price", "value": "1박 15만원"}])
    assert "101호 주말특가" in card["slots"]["offerings"]["value"]
    cafe = E.new_card("cafe")
    cafe["slots"]["offerings"] = {"value": ["주말 브런치"], "status": S.FILLED, "evidence": [1], "by": None}
    assert not E._fold_season_rates(cafe, 1, None)
