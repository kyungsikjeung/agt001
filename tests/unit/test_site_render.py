"""시안 렌더러 단위 테스트 (작업 R1).

외부 호출 없음 (chevron·토큰 JSON만 사용). DB를 쓰지 않는다.
"""
import copy
import json
import re
from pathlib import Path

import pytest

from app.services import site_render
from app.services.site_render import (
    SiteSpecError,
    contrast_ratio,
    list_variants,
    on_primary_for,
    render_site,
)

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "templates" / "samples"
SAMPLE_NAMES = ["pension", "cafe", "restaurant", "salon", "workshop", "academy"]


def _load_sample(name: str) -> dict:
    return json.loads((SAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))


def _section_ids(html_text: str) -> list:
    return re.findall(r'data-section-id="([^"]+)"', html_text)


@pytest.mark.parametrize("name", SAMPLE_NAMES)
def test_샘플_6종_렌더_성공(name):
    spec = _load_sample(name)
    out = render_site(spec, site_key="testkey", title="테스트 가게")
    assert out.startswith("<!doctype html>")
    assert 'lang="ko"' in out
    assert 'name="viewport"' in out
    assert "<script" not in out
    assert "{{" not in out
    # site.css에는 "{{"가 없으므로 위 검사로 Mustache 잔재를 잡는다.
    # ("}}"는 CSS 중괄호에 정상 포함되므로 검사하지 않는다.)
    # 빈 갤러리는 숨기므로(SPEC §2.4) 그 외 섹션은 전부 있어야 한다.
    for section in spec["sections"]:
        if section["type"] == "gallery" and not section["content"].get("items"):
            continue
        assert section["id"] in _section_ids(out)


def test_사용자_값_HTML_이스케이프():
    spec = _load_sample("pension")
    spec["sections"][0]["content"]["title"] = '<img src=x onerror="alert(1)">'
    spec["sections"][0]["content"]["subtitle"] = "<b>굵게</b>"
    out = render_site(spec)
    assert '<img src=x onerror' not in out
    assert "&lt;img" in out
    assert "&lt;b&gt;" in out
    # chevron 스코프 그림자 회귀 방지 (str.title 메서드 노출 금지).
    assert "built-in" not in out


def test_hero_제목이_비어있지않으면_그대로_보임():
    spec = _load_sample("pension")
    spec["sections"][0]["content"]["title"] = "푸른 언덕 펜션"
    out = render_site(spec)
    assert "푸른 언덕 펜션" in out
    assert "[가게 이름 입력]" not in out.split('id="hero-title-hero"')[1][:500]


def test_잘못된_조합과_토큰은_SiteSpecError():
    spec = _load_sample("cafe")
    bad = copy.deepcopy(spec)
    bad["sections"][0]["variant"] = "없는변형"
    with pytest.raises(SiteSpecError):
        render_site(bad)
    bad = copy.deepcopy(spec)
    bad["sections"][0]["type"] = "없는부품"
    with pytest.raises(SiteSpecError):
        render_site(bad)
    for key in ("palette", "font_pair", "density", "radius", "image_style"):
        bad = copy.deepcopy(spec)
        bad["tokens"][key] = "없는토큰"
        with pytest.raises(SiteSpecError):
            render_site(bad)


def test_URL_허용목록():
    spec = _load_sample("salon")
    hero = spec["sections"][0]["content"]
    hero["cta"] = {"label": "예약", "href": "javascript:alert(1)"}
    around = _load_sample("restaurant")
    around_map = next(s for s in around["sections"] if s["type"] == "around")["content"]
    around_map["map_url"] = "http://평문-host/지도"
    contact = next(s for s in spec["sections"] if s["type"] == "contact")["content"]
    contact["booking_url"] = "https://예약.example.com/abc"
    booking = next(s for s in spec["sections"] if s["type"] == "cta")["content"]
    booking["booking_url"] = "https://예약.example.com/abc"
    out = render_site(spec)
    assert "javascript:" not in out
    out_map = render_site(around)
    assert "http://평문-host" not in out_map
    assert "https://예약.example.com/abc" in out

    spec2 = _load_sample("cafe")
    spec2["sections"][0]["content"]["cta"] = {"label": "전화", "href": "tel:010-1234-5678"}
    out2 = render_site(spec2)
    assert "tel:01012345678" in out2


def test_빈_사실값은_자리표시():
    out = render_site(_load_sample("pension"))
    assert "[가게 이름 입력]" in out
    assert "[전화번호 입력]" in out
    assert "[가격 입력]" in out or "[메뉴 입력]" in out


def test_문의폼_action에_site_key():
    spec = _load_sample("cafe")
    spec["sections"].append({
        "id": "inquiry", "type": "contact", "variant": "form", "content": {},
    })
    out = render_site(spec, site_key="가게키123", retention_days=30)
    assert 'action="/api/inquiries/가게키123"' in out
    assert "30일" in out


def test_토큰_CSS변수와_파생값():
    out = render_site(_load_sample("pension"))
    root = out.split("<style>")[1].split("</style>")[0]
    assert "--c-primary:#2f5d50" in root.replace(" ", "")
    assert "--c-accent" in root
    assert "--c-ground" in root
    assert "--c-ink" in root
    assert "--on-primary" in root
    assert "--ground-soft" in root
    assert "--line" in root
    assert "--focus" in root
    assert "--muted" in root


def test_파생값_대비계산():
    # 흰 바탕 위 진한 초록은 흰 글자가 된다 (SPEC §1.6 forest).
    assert on_primary_for("#2f5d50") == "#FFFFFF"
    # 흰 바탕 위 흰 주색은 대비가 안 나오므로 검정에 가까운 글자.
    assert on_primary_for("#ffffff") == "#1A1A1A"
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0)
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0)


def test_tabs_index와_has_불리언():
    spec = _load_sample("workshop")
    tabs = next(s for s in spec["sections"] if s["variant"] == "tabs")
    tabs["content"]["items"] = [
        {"name": "반1", "desc": "설명", "price": "10000"},
        {"name": "반2", "desc": "", "price": ""},
    ]
    out = render_site(spec)
    assert "#tab-classes-1" in out
    assert "#tab-classes-2" in out
    assert "[가격 입력]" in out


def test_list_variants_25종():
    variants = list_variants()
    assert len(variants) == 25  # 20 + 문의 2 + 영상 1 + P2 새 부품 2(features--icons, stats--band)
    assert "hero--photo-overlay" in variants
    assert "contact--form" in variants
    assert "reviews--slot-only" in variants
    assert "video--card" in variants
    assert variants == sorted(variants)
    assert "contact--form" in site_render.list_variants()


# ---- 작업 A1: 사진 없는 자리를 업종별 예시 그림으로 ----

def _hero_빈사진(variant="photo-overlay"):
    return {"id": "hero", "type": "hero", "variant": variant,
            "content": {"title": "가게", "subtitle": "소개", "cta": {},
                        "image": "", "image_alt": ""}}


def _gallery_빈사진(variant="grid"):
    return {"id": "gallery", "type": "gallery", "variant": variant,
            "content": {"items": []}}


def _bare_spec(sections):
    spec = copy.deepcopy(_load_sample("cafe"))
    spec["sections"] = sections
    return spec


def test_사진없음_예시그림과_예시표시():
    out = render_site(_bare_spec([_hero_빈사진(), _gallery_빈사진()]), kind="cafe")
    assert "<svg" in out
    assert '<div class="s-illu"' in out
    assert "예시 이미지" in out
    assert "[사진 입력]" not in out
    assert "사장님 사진으로 바뀌어요" in out
    assert "<script" not in out
    assert "{{" not in out
    # 외부 파일을 부르지 않고 인라인으로 넣는다.
    assert "/illustrations/" not in out


def test_옆배치_대표도_빈사진이면_그림():
    out = render_site(_bare_spec([_hero_빈사진("photo-side")]), kind="pension")
    assert "<svg" in out
    assert "예시 이미지" in out


def test_글자만_대표는_그림없음():
    out = render_site(_bare_spec(
        [{"id": "hero", "type": "hero", "variant": "text-only",
          "content": {"title": "가게", "subtitle": "소개", "cta": {}}}]), kind="cafe")
    assert '<div class="s-illu"' not in out
    assert "<svg" not in out


def test_사진있음_예시그림없음():
    hero = _hero_빈사진()
    hero["content"]["image"] = "https://사진.example.com/대표.jpg"
    gallery = {"id": "gallery", "type": "gallery", "variant": "grid",
               "content": {"items": [{"src": "https://사진.example.com/1.jpg",
                                      "alt": "내부", "caption": "홀"}]}}
    out = render_site(_bare_spec([hero, gallery]), kind="cafe")
    assert '<div class="s-illu"' not in out
    assert "예시 이미지" not in out
    assert "https://사진.example.com/대표.jpg" in out
    assert "https://사진.example.com/1.jpg" in out


def test_uploads_사진도_실사진으로():
    hero = _hero_빈사진()
    hero["content"]["image"] = "/uploads/방123/사진1.jpg"
    out = render_site(_bare_spec([hero]), kind="cafe")
    assert "/uploads/방123/사진1.jpg" in out
    assert '<div class="s-illu"' not in out


def test_clean_url_uploads허용_기타상대경로거부():
    assert site_render._clean_url("/uploads/방1/가.jpg") == "/uploads/방1/가.jpg"
    assert site_render._clean_url("/etc/passwd") == ""
    assert site_render._clean_url("상대/경로.jpg") == ""
    assert site_render._clean_url("../탈출.jpg") == ""
    assert site_render._clean_url("/assets/방/1.jpg") == ""


def test_설명만있고_사진없음_예시그림():
    gallery = {"id": "gallery", "type": "gallery", "variant": "swipe",
               "content": {"items": [{"src": "", "caption": "곧 사진이 와요"}]}}
    out = render_site(_bare_spec([gallery]), kind="pension")
    assert "사장님 사진으로 바뀌어요" in out
    assert "s-gallery__swipe" in out


def test_업종10종_모두렌더():
    assert len(site_render.KIND_KEYS) == 10
    for kind in site_render.KIND_KEYS:
        out = render_site(_bare_spec([_hero_빈사진(), _gallery_빈사진()]), kind=kind)
        assert "<svg" in out
        assert "예시 이미지" in out
        assert "사장님 사진으로 바뀌어요" in out
    # 모르는 업종은 other 그림으로 렌더한다.
    out = render_site(_bare_spec([_hero_빈사진()]), kind="없는업종")
    assert "<svg" in out


def test_public_mode_hides_placeholders():
    """공개 사이트: 빈칸 부품은 빼고, 빈 줄은 숨김 규칙, 가격은 '가격 문의'. 시안은 그대로 보인다."""
    import json
    from app.services.site_render import render_site
    spec = json.load(open("templates/samples/cafe.json"))
    design_html = render_site(spec, kind="cafe")
    public_html = render_site(spec, kind="cafe", public=True)
    assert '<body class="is-public">' in public_html and '<body class="is-public">' not in design_html
    assert "후기가 모이면" in design_html and "후기가 모이면" not in public_html
    assert "가격 문의" in public_html  # CSS 규칙으로 들어간다


# ---- 작업 P1: 영상 카드 ----

def _video_섹션(items):
    return {"id": "videos", "type": "video", "variant": "card",
            "content": {"items": items}}


def test_영상카드_유튜브3형식():
    items = [
        {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "title": "손질 영상"},
        {"url": "https://youtu.be/dQw4w9WgXcQ", "title": "매장 소개"},
        {"url": "https://www.youtube.com/shorts/dQw4w9WgXcQ", "title": "쇼츠"},
    ]
    out = render_site(_bare_spec([_video_섹션(items)]), kind="cafe")
    assert "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg" in out
    assert "손질 영상" in out
    assert 'target="_blank"' in out
    assert 'rel="noopener"' in out
    assert "<iframe" not in out
    assert "<script" not in out
    assert "{{" not in out


def test_영상카드_인스타_네이버():
    items = [
        {"url": "https://www.instagram.com/reel/C8abc123XYZ/", "title": "릴스"},
        {"url": "https://tv.naver.com/v/12345", "title": "방송"},
    ]
    out = render_site(_bare_spec([_video_섹션(items)]), kind="cafe")
    assert "인스타그램" in out
    assert "네이버TV" in out
    assert "릴스" in out
    assert "<iframe" not in out
    assert "<script" not in out


def test_영상카드_이상한주소_버림():
    items = [
        {"url": "javascript:alert(1)", "title": "나쁜 주소"},
        {"url": "http://평문-host/영상", "title": "평문"},
        {"url": "https://example.com/video/1", "title": "모름"},
    ]
    out = render_site(_bare_spec([_video_섹션(items)]), kind="cafe")
    assert '<section class="s-video' not in out
    assert 'data-section-id="videos"' not in out
    out_public = render_site(_bare_spec([_video_섹션(items)]), kind="cafe", public=True)
    assert '<section class="s-video' not in out_public


def test_영상카드_비면숨김_최대3개():
    out = render_site(_bare_spec([_video_섹션([])]), kind="cafe")
    assert '<section class="s-video' not in out
    assert 'data-section-id="videos"' not in out
    out_public = render_site(_bare_spec([_video_섹션([])]), kind="cafe", public=True)
    assert '<section class="s-video' not in out_public
    items = [
        {"url": "https://youtu.be/AAA111AAA11", "title": "1"},
        {"url": "https://youtu.be/BBB222BBB22", "title": "2"},
        {"url": "https://youtu.be/CCC333CCC33", "title": "3"},
        {"url": "https://youtu.be/DDD444DDD44", "title": "4"},
    ]
    out = render_site(_bare_spec([_video_섹션(items)]), kind="cafe")
    assert "AAA111AAA11" in out
    assert "DDD444DDD44" not in out


def test_public_quality_fixes_2026_09_26():
    """사이트 품질 점검(docs/product/evals/site-quality-2026-09-26.md) Q-2~Q-5 회귀 방지."""
    # Q-4: 예약 주소 없이 전화만 있는 cta--external은 공개본에서 뺀다(제목만 남던 문제)
    spec = _load_sample("workshop")
    for sec in spec["sections"]:
        if sec["type"] == "cta":
            sec["content"] = {"booking_url": "", "phone": "010-0000-0000"}
    assert "booking" not in _section_ids(render_site(spec, public=True))
    assert "booking" in _section_ids(render_site(spec))  # 시안에서는 채울 곳으로 보인다

    # Q-5: 이름 없는 상품 항목은 공개본에서 빠지고, 다 빠지면 부품째 빠진다
    spec = _load_sample("academy")
    offer = next(s for s in spec["sections"] if s["type"] == "offerings")
    offer["content"]["items"] = [{"name": "", "desc": "", "price": ""}, {"name": "중등 수학 반", "desc": "", "price": ""}]
    html_text = render_site(spec, public=True)
    assert html_text.count('class="s-price-list__row"') == 1 and "중등 수학 반" in html_text
    offer["content"]["items"] = [{"name": "", "desc": "", "price": ""}]
    assert offer["id"] not in _section_ids(render_site(spec, public=True))

    # Q-2: 공개본 CSS는 사진 없는 상품 카드를 통째로 숨기지 않는다
    css = render_site(_load_sample("pension"), public=True)
    assert "li:has(> .is-placeholder:not(.s-media__empty))" in css
    # D36: 예시 그림 배지는 방문자에게도 보이고(숨기는 규칙 없음), 사장님용 사진첩 안내만 숨긴다
    assert ".is-public .s-illu-badge" not in css and ".is-public .s-gallery__notice" in css
