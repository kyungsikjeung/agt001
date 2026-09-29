"""적합성 부품 (DESIGN_FIT_PLAN 2단계, D53): 분류 메뉴판·담당자·예시 지도·예약 현황·주문 준비 중·하단 행동 바.

부품마다 네 상태를 본다: 채움 / 예시(D53①) / 빈칸(시안 자리 표시) / 공개본(예시 값 제거·빈 부품 제외).
DB가 필요 없다: 로컬은 `pytest --noconftest tests/unit/test_fit_components.py`로도 돈다.
"""
import re

from app.services import site_render as SR

TOKENS = {"palette": "coffee", "font_pair": "sans-clean", "density": "comfortable", "radius": "soft", "image_style": "card"}


def _page(sections, public=False, **extra):
    return SR.render_site({"tokens": TOKENS, "sections": sections, **extra}, site_key="k", public=public)


def _menu(order=False):
    return {"id": "menu", "type": "offerings", "variant": "categories", "content": {"label": "메뉴", "order": order, "categories": [
        {"name": "커피", "image": "/art/ex/cafe-coffee.webp", "image_example": True, "items": [
            {"name": "아메리카노", "price": "4,500원", "badge": "대표"},
            {"name": "딸기라떼", "price": "6,000원", "price_example": True},
            {"name": "지어낸 메뉴", "price": "1원", "example": True}]},
        {"name": "디저트", "items": [{"name": "휘낭시에", "price": ""}, {"name": "", "price": "3,000원"}]}]}}


def _li(doc, name):
    return next(li for li in re.findall(r"<li\b.*?</li>", doc, re.S) if name in li)


def test_no_script_in_any_new_part():
    doc = _page([_menu(True), _staff("team"), _map("서울 마포구 연남로 12"), _slots(),
                 {"id": "order-soon", "type": "order", "variant": "soon", "content": {}}],
                actionbar={"primary": {"label": "예약하기", "href": "#booking-title-booking"}})
    assert "<script" not in doc.lower() and "javascript:" not in doc.lower()


# ---- 분류 메뉴판 ----
def test_menu_categories_pair_price_with_item_and_chip_per_category():
    doc = _page([_menu()])
    assert re.search(r"<h3\b[^>]*>\s*커피", doc) and re.search(r"<h3\b[^>]*>\s*디저트", doc)
    assert doc.count('class="s-chip"') == 2
    assert "4,500원" in _li(doc, "아메리카노") and "대표" in _li(doc, "아메리카노")
    assert "예시" in _li(doc, "딸기라떼")                       # 예시 가격은 표시와 함께
    assert "[가격 입력]" in _li(doc, "휘낭시에")                  # 모르는 가격은 자리 표시
    assert "3,000원" not in doc                                  # 이름 없는 품목은 뺀다


def test_menu_public_drops_example_values_and_items():
    doc = _page([_menu()], public=True)
    assert "4,500원" in doc and "아메리카노" in doc
    assert "6,000원" not in doc and "딸기라떼" in doc          # 예시 가격만 빠지고 품목은 남는다
    assert "지어낸 메뉴" not in doc                            # 예시 품목은 통째로 빠진다
    assert "예시 이미지" in doc                                # 예시 사진 표시는 남는다(D51)


def test_menu_order_links_to_soon_sheet_only_when_ordering():
    assert 'href="#order-soon"' not in _page([_menu()])
    doc = _page([_menu(order=True)])
    assert 'aria-label="아메리카노 담기"' in doc and doc.count('href="#order-soon"') == 5  # 담기 4 + 주문하기 1


def test_menu_without_categories_is_placeholder_and_hidden_on_public():
    empty = {"id": "menu", "type": "offerings", "variant": "categories", "content": {"categories": []}}
    assert "[메뉴 입력]" in _page([empty])
    assert "offerings-title-menu" not in _page([empty], public=True)


# ---- 담당자 ----
def _staff(variant, members=None):
    members = members or [{"name": "김미용", "role": "원장", "specialties": ["컷", "레이어드"]},
                          {"name": "박하나", "role": "실장", "specialties": ["염색"], "image": "javascript:alert(1)"},
                          {"name": "예시 디자이너", "role": "디자이너", "example": True}]
    return {"id": "staff", "type": "staff", "variant": variant,
            "content": {"booking_href": "#booking-title-booking", "members": members,
                        "works": [{"src": "/art/ex/salon-style1.webp", "image_example": True}]}}


def test_staff_team_card_per_member_with_booking_link():
    doc = _page([_staff("team")])
    assert 's-staff--team' in doc and doc.count('class="s-staff__card"') == 3
    assert "김미용 원장에게 예약" in doc and 'href="#booking-title-booking"' in doc
    assert "javascript" not in doc and 's-staff__avatar--mono' in doc   # 나쁜 주소는 머리글자로


def test_staff_public_drops_example_member_and_empty_section():
    doc = _page([_staff("team")], public=True)
    assert "예시 디자이너" not in doc and "김미용" in doc
    only_example = _staff("team", [{"name": "예시", "example": True}])
    assert "staff-title-staff" not in _page([only_example], public=True)


def test_staff_solo_one_owner_with_works():
    doc = _page([_staff("solo")])
    assert 's-staff--solo' in doc and "김미용" in doc and "박하나" not in doc
    assert "원장님께 예약하기" in doc and "salon-style1.webp" in doc


def test_staff_rejects_non_anchor_booking_link():
    sec = _staff("team")
    sec["content"]["booking_href"] = "https://evil.example"
    assert "에게 예약" not in _page([sec])


# ---- 예시 지도 ----
def _map(address):
    return {"id": "around", "type": "around", "variant": "map", "content": {"address": address}}


def test_map_dummy_art_and_app_links():
    doc = _page([_map("서울 마포구 연남로 12")])
    assert "예시 지도" in doc and "<svg" in doc
    assert "https://map.kakao.com/?q=%EC%84%9C%EC%9A%B8" in doc and "https://map.naver.com/p/search/" in doc


def test_map_without_address_has_no_links():
    doc = _page([_map("")])
    assert "[주소 입력]" in doc and "map.kakao.com" not in doc


def test_map_public_keeps_links_hides_dummy_via_css():
    doc = _page([_map("서울 마포구 연남로 12")], public=True)
    assert '<body class="is-public">' in doc and ".is-public .s-map__art { display: none; }" in doc
    assert "map.naver.com" in doc


# ---- 예약 현황 ----
def _slots(example=True, staff=("김미용", "박하나")):
    return {"id": "booking", "type": "booking", "variant": "slots", "content": {
        "staff": list(staff), "services": ["컷"], "days_example": example, "days": [
            {"date": "2026-10-01", "dow": "목", "slots": [{"time": "10:00", "state": "open"}, {"time": "11:00", "state": "full"},
                                                          {"time": "12:00", "state": "few"}, {"time": "1pm", "state": "open"}]},
            {"date": "bad", "slots": [{"time": "10:00"}]}]}}


def test_slots_radio_per_time_full_is_disabled():
    doc = _page([_slots()])
    radios = re.findall(r'<input class="s-pick__in" type="radio"[^>]*name="slot"[^>]*>', doc)
    assert len(radios) == 3                                     # 잘못된 날짜·시간은 버린다
    assert 'value="2026-10-01 10:00"' in radios[0] and "disabled" in radios[1] and "disabled" not in radios[2]
    assert "마감 임박" in doc and "예시 현황" in doc and "10/01" in doc


def test_slots_staff_chips_only_for_team():
    assert doc_count(_page([_slots()]), 'name="staff"') == 3      # 상관없음 + 2명
    assert 'name="staff"' not in _page([_slots(staff=("김단정",))])


def doc_count(doc, needle):
    return doc.count(needle)


def test_slots_public_example_falls_back_to_date_input():
    doc = _page([_slots()], public=True)
    assert 'name="slot"' not in doc and 'type="date"' in doc
    real = _page([_slots(example=False)], public=True)
    assert 'name="slot"' in real                                # 확정 예약으로 계산한 현황은 공개본에도


# ---- 주문 준비 중 안내창 ----
def test_order_soon_sheet_targets_and_safe_return():
    sec = {"id": "order-soon", "type": "order", "variant": "soon",
           "content": {"phone": "02-123-4567", "return_href": "javascript:alert(1)"}}
    doc = _page([sec])
    assert 'id="order-soon"' in doc and 'role="dialog"' in doc and "준비 중" in doc
    assert 'href="tel:021234567"' in doc and "javascript" not in doc and 'href="#"' in doc


# ---- 하단 행동 바 ----
def test_actionbar_needs_existing_target():
    bar = {"primary": {"label": "예약하기", "href": "#booking-title-booking"}, "secondary": {"label": "전화", "href": "tel:02-1-2"}}
    assert 's-actionbar' in _page([_slots()], actionbar=bar)
    assert 'class="s-actionbar"' not in _page([_map("주소")], actionbar=bar)     # 예약 섹션이 없으면 그리지 않는다
    assert 'href="tel:0212"' in _page([_slots()], actionbar=bar)


# ---- 첫 화면 두 번째 행동·사진첩 제목 ----
def test_hero_second_action_is_text_link_not_second_button():
    hero = {"id": "hero", "type": "hero", "variant": "photo-overlay", "content": {
        "title": "가게", "cta": {"label": "길찾기", "href": "#around-title-around"},
        "cta2": {"label": "메뉴 보기", "href": "#offerings-title-menu"}}}
    doc = _page([hero, _menu(), _map("주소")])
    part = doc[doc.find('<section class="s-hero s-hero--photo-overlay'):]
    part = part[:part.find("</section>")]
    assert part.count('class="s-btn') == 1 and 'class="s-hero__link"' in part and "메뉴 보기" in part


def test_gallery_label_replaces_generic_title():
    gal = {"id": "space", "type": "gallery", "variant": "grid", "content": {"label": "공간", "items": [{"src": "/art/ex/cafe-space.webp"}]}}
    doc = _page([gal])
    assert re.search(r"<h2[^>]*>공간</h2>", doc) and not re.search(r"<h2[^>]*>사진첩</h2>", doc)


def test_drop_examples_rules():
    got = SR._drop_examples({"a": [{"x": 1, "example": True}, {"x": 2}], "price": "1원", "price_example": True,
                             "image": "/art/a.webp", "image_example": True, "days": [1], "days_example": True})
    assert got["a"] == [{"x": 2}] and got["price"] == "" and got["image"] == "/art/a.webp" and got["days"] == []


def test_hero_second_action_dropped_when_target_missing_on_public():
    hero = {"id": "hero", "type": "hero", "variant": "photo-overlay", "content": {
        "title": "가게", "cta": {"label": "예약하기", "href": "#booking-title-booking"},
        "cta2": {"label": "디자이너 보기", "href": "#staff-title-staff"}}}
    only_example = _staff("team", [{"name": "예시", "example": True}])
    assert "디자이너 보기" in _page([hero, only_example])
    assert "디자이너 보기" not in _page([hero, only_example], public=True)


def test_public_page_has_og_tags(monkeypatch):
    """카톡 미리보기 (디자인 품질 7번): 공개본에만 og 태그, 사진은 공개 호스트 절대 주소."""
    from app.config import settings
    monkeypatch.setattr(settings, "preview_host", "preview.example")
    hero = {"id": "hero", "type": "hero", "variant": "photo-overlay",
            "content": {"title": "마포 느린오후", "subtitle": "조용한 카페예요", "image": "/art/ex/cafe-hero.webp"}}
    pub = _page([hero], public=True)
    assert '<meta property="og:title" content="마포 느린오후">' in pub
    assert '<meta property="og:image" content="https://preview.example/art/ex/cafe-hero.webp">' in pub
    assert "og:title" not in _page([hero])


def test_webp_served_as_image(client):
    r = client.get("/art/ex/cafe-hero.webp")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"


def test_notice_banner_and_popup_escape():
    """공지 띠는 늘, 팝업은 켰을 때만. 사장님 글은 이스케이프 (D56)."""
    hero = {"id": "hero", "type": "hero", "variant": "photo-overlay", "content": {"title": "마포"}}
    on = _page([hero], public=True, notice={"text": "쉬어요 <b>", "popup": True})
    assert '<p class="s-notice" role="note"><strong>공지</strong> 쉬어요 &lt;b&gt;</p>' in on
    assert 'id="s-popup"' in on and "오늘 하루" not in on
    off = _page([hero], public=True, notice={"text": "쉬어요", "popup": False})
    assert '<p class="s-notice"' in off and 'id="s-popup"' not in off


def test_app_layout_tabbar_replaces_actionbar():
    """앱형 (D56): 하단 탭이 행동 바를 대신한다. 탭은 실제 있는 구역만."""
    hero = {"id": "hero", "type": "hero", "variant": "app", "content": {"title": "마포", "subtitle": "카페"}}
    doc = _page([hero, _menu()], layout="app",
                navbar={"title": "마포", "top": "#hero-title-hero", "links": [{"label": "메뉴", "href": "#offerings-title-menu"},
                                                                         {"label": "없는 곳", "href": "#nope"}]},
                actionbar={"primary": {"label": "전화", "href": "tel:0212345678"}})
    assert '<body class="is-app">' in doc and "마포입니다." in doc
    assert doc.count('class="s-tabbar__tab"') == 3 and "없는 곳" not in doc  # 홈·메뉴·전화
    assert '<nav class="s-actionbar"' not in doc
