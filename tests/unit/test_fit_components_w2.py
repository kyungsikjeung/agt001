"""2주차 부품 (BUILD_W1_W2 §1.7 C1): 반 카드·시간표·객실 카드·입실일 예약.

부품마다 네 상태를 본다: 채움 / 예시(D53①) / 빈칸(시안 자리 표시) / 공개본(예시 값 제거·빈 부품 제외).
DB가 필요 없다: 로컬은 `pytest --noconftest tests/unit/test_fit_components_w2.py`로도 돈다.
"""
import re

from app.services import site_render as SR

TOKENS = {"palette": "coffee", "font_pair": "sans-clean", "density": "comfortable", "radius": "soft", "image_style": "card"}


def _page(sections, public=False, **extra):
    return SR.render_site({"tokens": TOKENS, "sections": sections, **extra}, site_key="k", public=public)


def test_no_script_in_new_parts():
    doc = _page([_classes(), _timetable(), _rooms(), _dates(),
                 {"id": "x", "type": "classes", "variant": "cards", "tone": "inverse", "content": {}}])
    assert "<script" not in doc.lower() and "javascript:" not in doc.lower() and "onclick" not in doc.lower()


def test_extra_css_is_bundled_after_site_css():
    doc = _page([_classes()])
    style = doc.split("<style>")[1].split("</style>")[0]
    assert ".s-classes__list" in style and ".s-timetable__scroll" in style
    assert ".s-rooms__list" in style and ".s-dates__opts" in style
    assert style.find(".s-classes__list") > style.find(":root{")


def test_data_tone_inverse_on_first_tag_only():
    sec = _classes()
    sec["tone"] = "inverse"
    doc = _page([sec])
    first = doc[doc.find("<section"):doc.find(">", doc.find("<section")) + 1]
    assert 'data-tone="inverse"' in first
    roots = re.findall(r"<section[^>]*>", doc)
    assert len(roots) == 1 and 'data-tone="inverse"' in roots[0]
    plain = _page([_classes()])
    assert not re.findall(r"<section[^>]*data-tone", plain)


# ---- 반 카드 ----
def _classes(cta="#booking-title-booking"):
    return {"id": "classes", "type": "classes", "variant": "cards",
            "content": {"label": "반 안내", "cta_href": cta, "classes": [
                {"name": "초등 파닉스반", "target": "초등 1~3학년", "days": "월·수", "time": "16:00",
                 "capacity": "8명", "fee": "18만원", "level": "입문", "desc": "소수 정원 수업"},
                {"name": "중등 수학반", "fee": "20만원", "fee_example": True},
                {"name": "예시 반", "fee": "1원", "example": True},
                {"name": "", "fee": "5만원"}]}}


def test_classes_filled_card_lines():
    doc = _page([_classes()])
    assert "s-classes--cards" in doc and "초등 파닉스반" in doc
    assert "초등 1~3학년" in doc and "월·수 16:00" in doc
    assert "정원 8명" in doc and "18만원" in doc and "입문" in doc and "소수 정원 수업" in doc
    assert "상담 신청" in doc and 'href="#booking-title-booking"' in doc
    assert "예시" in doc  # 예시 수강료·예시 반 표시


def test_classes_public_drops_example_values_and_items():
    doc = _page([_classes()], public=True)
    assert "초등 파닉스반" in doc and "18만원" in doc
    assert "20만원" not in doc and "중등 수학반" in doc  # 예시 수강료만 빠지고 반은 남는다
    assert "예시 반" not in doc  # 예시 반은 통째로 빠진다
    assert "5만원" not in doc  # 이름 없는 반은 뺀다


def test_classes_empty_is_placeholder_and_hidden_on_public():
    empty = {"id": "classes", "type": "classes", "variant": "cards", "content": {"classes": []}}
    assert "[반 입력]" in _page([empty])
    assert "classes-title-classes" not in _page([empty], public=True)


def test_classes_rejects_bad_values_and_caps():
    sec = _classes(cta="https://evil.example")
    sec["content"]["classes"] = [{"name": "  ", "fee": "1원"}, {"name": "파닉스반", "fee": "1원"}]
    doc = _page([sec])
    assert "상담 신청" not in doc  # #가 아니면 링크를 뺀다
    assert "1원" in doc and "파닉스반" in doc  # 이름 없는 반은 버린다
    sec["content"]["classes"] = [{"name": f"반{i}", "fee": "1원"} for i in range(20)]
    assert _page([sec]).count('class="s-class"') == 12  # 최대 12개


# ---- 시간표 ----
def _timetable(example=False):
    content = {"label": "시간표", "days": ["월", "수", "금"], "rows": [
        {"time": "16:00", "cells": [{"day": "월", "text": "파닉스"}, {"day": "수", "text": "파닉스"}]},
        {"time": "17:00", "cells": [{"day": "금", "text": "회화"}]},
        {"time": "", "cells": [{"day": "월", "text": "버림"}]}]}
    if example:
        content["example"] = True
    return {"id": "tt", "type": "timetable", "variant": "week", "content": content}


def test_timetable_table_with_caption_and_aligned_cells():
    doc = _page([_timetable()])
    assert "<table" in doc and "<caption>시간표</caption>" in doc
    assert "<thead" in doc and "<tbody" in doc
    assert '<th scope="col">월</th>' in doc and '<th scope="row">16:00</th>' in doc
    assert doc.count("파닉스") == 2 and "회화" in doc
    assert "버림" not in doc  # 시간 없는 행은 버린다


def test_timetable_example_badge_and_hidden_on_public():
    assert "예시" in _page([_timetable(example=True)])
    assert "timetable-title-tt" not in _page([_timetable(example=True)], public=True)


def test_timetable_empty_is_placeholder_and_hidden_on_public():
    empty = {"id": "tt", "type": "timetable", "variant": "week", "content": {"days": [], "rows": []}}
    assert "[시간표 입력]" in _page([empty])
    assert "timetable-title-tt" not in _page([empty], public=True)


def test_timetable_caps_rows():
    sec = _timetable()
    sec["content"]["rows"] = [{"time": f"{9 + i}:00", "cells": []} for i in range(20)]
    assert _page([sec]).count('<th scope="row">') == 12  # 최대 12행


# ---- 객실 카드 ----
def _rooms(href="#booking-title-booking"):
    return {"id": "rooms", "type": "rooms", "variant": "cards",
            "content": {"label": "객실", "booking_href": href, "rooms": [
                {"name": "숲뷰 201호", "image": "/art/ex/pension-room.webp", "image_example": True,
                 "capacity": "2~4인", "size": "20평", "price": "15만원", "features": ["욕조", "바비큐"]},
                {"name": "계곡뷰 202호", "price": "18만원", "price_example": True},
                {"name": "예시 객실", "price": "1원", "example": True},
                {"name": "", "price": "9만원"}]}}


def test_rooms_filled_card_with_photo_and_chips():
    doc = _page([_rooms()])
    assert "s-rooms--cards" in doc and "숲뷰 201호" in doc
    assert "/art/ex/pension-room.webp" in doc and "예시 이미지" in doc and 'loading="lazy"' in doc
    assert "2~4인" in doc and "20평" in doc and "15만원" in doc
    assert "욕조" in doc and "바비큐" in doc
    assert "이 객실 예약" in doc and 'href="#booking-title-booking"' in doc


def test_rooms_public_drops_example_room_and_price():
    doc = _page([_rooms()], public=True)
    assert "숲뷰 201호" in doc and "15만원" in doc
    assert "18만원" not in doc and "계곡뷰 202호" in doc  # 예시 요금만 빠지고 객실은 남는다
    assert "예시 객실" not in doc  # 예시 객실은 통째로 빠진다
    assert "9만원" not in doc  # 이름 없는 객실은 뺀다
    assert "예시 이미지" in doc  # 예시 사진 표시는 남는다(D51)


def test_rooms_empty_is_placeholder_and_hidden_on_public():
    empty = {"id": "rooms", "type": "rooms", "variant": "cards", "content": {"rooms": []}}
    assert "[객실 입력]" in _page([empty])
    assert "rooms-title-rooms" not in _page([empty], public=True)


def test_rooms_rejects_bad_values_and_caps():
    sec = _rooms(href="javascript:alert(1)")
    sec["content"]["rooms"] = ([{"name": "독채", "image": "javascript:alert(1)"}] +
                               [{"name": f"객실{i}"} for i in range(12)])
    doc = _page([sec])
    assert "javascript" not in doc and "이 객실 예약" not in doc
    assert len(re.findall(r'<li class="s-room"', doc)) == 8  # 최대 8개


# ---- 입실일 예약 ----
def _dates(example=True, rooms=("숲뷰 201호", "계곡뷰 202호")):
    return {"id": "booking", "type": "booking", "variant": "dates", "content": {
        "note": "주말은 빨리 찹니다", "rooms": list(rooms), "nights_max": 5, "days_example": example, "days": [
            {"date": "2026-10-02", "label": "10/02", "dow": "금", "state": "open"},
            {"date": "2026-10-03", "dow": "토", "state": "full"},
            {"date": "2026-10-04", "state": "few"},
            {"date": "bad", "state": "open"}]}}


def _date_radios(doc):
    return re.findall(r'<input class="s-pick__in" type="radio"[^>]*name="date"[^>]*>', doc)


def test_dates_radio_per_day_full_is_disabled():
    doc = _page([_dates()])
    radios = _date_radios(doc)
    assert len(radios) == 3  # 잘못된 날짜는 버린다
    assert 'value="2026-10-02"' in radios[0] and "disabled" not in radios[0]
    assert "disabled" in radios[1] and "disabled" not in radios[2]
    assert "마감 임박" in doc and "예시 현황" in doc and "주말은 빨리 찹니다" in doc
    assert 'name="service"' in doc and "숲뷰 201호" in doc
    assert 'name="nights"' in doc and 'max="5"' in doc and 'name="party"' in doc


def test_dates_public_example_falls_back_to_date_input():
    doc = _page([_dates()], public=True)
    assert not _date_radios(doc) and 'name="date" type="date"' in doc
    real = _page([_dates(example=False)], public=True)
    assert _date_radios(real)  # 확정 예약으로 계산한 현황은 공개본에도


def test_dates_without_days_has_date_input_and_defaults():
    sec = _dates()
    sec["content"]["days"] = []
    del sec["content"]["nights_max"]
    doc = _page([sec])
    assert 'name="date" type="date"' in doc and 'max="3"' in doc  # 박 수 기본 3


def test_dates_caps_days_and_rejects_bad_state():
    sec = _dates()
    sec["content"]["days"] = [{"date": f"2026-11-{i + 1:02d}", "state": "weird"} for i in range(30)]
    doc = _page([sec])
    assert len(_date_radios(doc)) == 21  # 최대 21일
    assert "weird" not in doc  # 모르는 상태는 여유로
