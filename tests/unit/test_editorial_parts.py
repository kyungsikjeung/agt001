"""편집형(에디토리얼) 7부품 단위 테스트 (Claude 시범, 2026-09-27).

7개 부품이 렌더되고, <script> 없음, 페이지당 h1 1개, 이미지 alt 있음,
실사 예시에 "예시 이미지" 표시, publish_check.assert_publishable 통과.
DB를 쓰지 않는다.
"""
import re
from pathlib import Path

import pytest

from app.services import site_render
from app.services.publish_check import assert_publishable
from app.services.site_render import list_variants, render_site
from evals.build_editorial_preview import spec_a, spec_b, spec_c, spec_d

ROOT = Path(__file__).resolve().parents[2]

NEW_PARTS = [
    "hero--illustrated",
    "hero--story",
    "hero--arch",
    "hero--cinematic",
    "offerings--cards",
    "concerns--bubbles",
    "quickbar--float",
]

BASE_TOKENS = {
    "palette": "coffee",
    "font_pair": "serif-warm",
    "density": "comfortable",
    "radius": "soft",
    "image_style": "card",
}

# 부품별 최소 명세 (가짜 정보, 실존 상호 없음).
MINI_CONTENTS = {
    "hero--illustrated": {
        "title": "예시 가게", "lines": ["첫 줄 선언문", "둘째 줄 선언문"],
        "image": "/art/cafe-engraving.webp", "image_alt": "판화풍 그림",
    },
    "hero--story": {
        "title": "처음 코딩, 두렵지 않게", "highlight": "두렵지 않게",
        "subtitle": "소개 한 줄", "image": "/art/academy-glass.webp",
        "image_alt": "유리 추상 그림",
    },
    "hero--arch": {
        "eyebrow": "작은 윗줄", "title": "예시 가게", "subtitle": "소개 한 줄",
        "image": "/art/pension-example.webp", "image_alt": "예시 사진",
        "ai_example": True, "label_en": "EXAMPLE STAY",
    },
    "hero--cinematic": {
        "kicker": "윗줄 문구", "title": "예시 가게", "subtitle": "소개 한 줄",
        "image": "/art/pension-example.webp", "image_alt": "예시 사진",
        "ai_example": True,
        "cta": {"label": "예약하기", "href": "https://booking.example.com/x"},
        "cta2": {"label": "전화 상담", "href": "tel:01012345678"},
    },
    "offerings--cards": {
        "label": "메뉴",
        "items": [{"name": "예시 메뉴", "desc": "한 줄 특징", "price": "5,000원"}],
    },
    "concerns--bubbles": {
        "heading": "이런 고민 있으세요?",
        "items": [{"quote": "처음인데 괜찮을까요?", "who": "예비 손님"}],
    },
    "quickbar--float": {
        "phone": "010-1234-5678",
        "channel_url": "https://pf.example.com/x",
        "booking_url": "https://booking.example.com/x",
    },
}


def _one_section_spec(key: str) -> dict:
    section_type, variant = key.split("--")
    return {
        "version": 3, "tokens": dict(BASE_TOKENS), "locked": [],
        "sections": [{"id": "s1", "type": section_type, "variant": variant,
                      "content": MINI_CONTENTS[key]}],
    }


def _img_alts(html_text: str) -> list:
    return re.findall(r"<img[^>]*\balt=\"([^\"]*)\"", html_text)


def test_7부품_파일과_목록():
    assert set(NEW_PARTS) <= set(list_variants())
    for key in NEW_PARTS:
        assert (ROOT / "templates" / "sections" / f"{key}.mustache").is_file()


@pytest.mark.parametrize("key", NEW_PARTS)
def test_7부품_개별_렌더(key):
    out = render_site(_one_section_spec(key), title="예시 가게", public=True)
    assert 'data-section-id="s1"' in out
    assert "<script" not in out.lower()
    assert "{{" not in out
    for alt in _img_alts(out):
        assert alt.strip()
    assert_publishable(out)


@pytest.mark.parametrize("maker,letter", [(spec_a, "A"), (spec_b, "B"), (spec_c, "C"), (spec_d, "D")])
def test_4방향_페이지_품질(maker, letter):
    spec, title = maker()
    out = render_site(spec, title=title, public=True)
    assert len(re.findall(r"<h1", out)) == 1, letter
    assert "<script" not in out.lower(), letter
    assert "<iframe" not in out.lower(), letter
    imgs = re.findall(r"<img[^>]*>", out)
    assert imgs, letter
    for tag in imgs:
        m = re.search(r'alt="([^"]*)"', tag)
        assert m and m.group(1).strip(), letter
    assert_publishable(out)


def test_B_핵심어_mark강조():
    spec, title = spec_b()
    assert "<mark>" in render_site(spec, title=title, public=True)


@pytest.mark.parametrize("maker,letter", [(spec_c, "C"), (spec_d, "D")])
def test_실사예시_배지표시(maker, letter):
    spec, title = maker()
    out = render_site(spec, title=title, public=True)
    assert "예시 이미지" in out, letter


def test_새템플릿_금지규칙():
    for key in NEW_PARTS:
        text = (ROOT / "templates" / "sections" / f"{key}.mustache").read_text(encoding="utf-8")
        assert "{{{" not in text, key
        assert "<script" not in text.lower(), key
        assert "<iframe" not in text.lower(), key
        assert "http:" not in text, key


def test_편집형CSS_규칙():
    css = (ROOT / "templates" / "site.css").read_text(encoding="utf-8")
    marker = "/* 편집형 부품 (Claude 시범, 2026-09-27) */"
    assert marker in css
    # 맨 끝 블록으로만 추가: 마커 뒤에 다른 블록이 오지 않는다.
    assert css.rstrip().endswith("}")
    block = css.split(marker, 1)[1]
    assert "@supports (animation-timeline: view())" in block
    assert "prefers-reduced-motion" in block
    assert "var(--font-display)" in block
    assert "min-height: 48px" in block
    assert "<script" not in block.lower()
