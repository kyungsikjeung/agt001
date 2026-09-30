"""공지 띠·팝업 그리기 (NOTICE_PHOTO_CONTRACT §2·§5의 4)."""
from app.services.publish_check import check_html
from app.services.site_render import render_site

HERO = {"id": "hero", "type": "hero", "variant": "photo-overlay", "content": {"title": "마포"}}
TOKENS = {"palette": "coffee", "font_pair": "serif-warm", "density": "comfortable", "radius": "soft",
          "image_style": "card"}
P1, P2 = "/uploads/r1/a.jpg", "/uploads/r1/b.jpg"


def _page(notice, **kw):
    spec = {"version": 3, "tokens": dict(TOKENS), "sections": [dict(HERO)], "notice": notice}
    return render_site(spec, kind="cafe", title="t", site_key="t", **kw)


def test_text_only_keeps_band_with_bell():
    page = _page({"text": "10월 3일은 쉬어요", "photos": [], "popup": False}, public=True)
    assert 'class="s-notice__bell"' in page and "10월 3일은 쉬어요" in page
    assert 'id="s-popup"' not in page and 'data-popup="open"' not in page
    old = _page({"text": "쉬어요", "popup": True}, public=True)  # 예전 모양(photos 없음)도 읽는다
    assert 'id="s-popup"' in old and 'data-auto="1"' in old


def test_photo_notice_band_thumb_popup_dots():
    page = _page({"text": "", "photos": [P1, P2], "popup": False}, public=True)
    assert "사진 공지 2장" in page
    assert f'class="s-notice__thumb" src="{P1}"' in page
    assert 'data-popup="open"' in page and 'data-auto="0"' in page
    assert page.count('alt="공지 사진') == 2
    assert page.count("<li class=\"on\"></li>") == 1 and 's-notice__dots' in page
    assert check_html(page) == []


def test_only_uploads_and_max_five():
    page = _page({"text": "새 메뉴", "photos": ["https://evil.example/x.jpg", "javascript:x", P1] + [P2] * 6},
                 public=True)
    assert "evil.example" not in page and "javascript:x" not in page
    assert page.count('alt="공지 사진') == 5


def test_edit_preview_has_band_but_no_popup():
    page = _page({"text": "쉬어요", "photos": [P1], "popup": True}, edit=True)
    assert "s-notice__thumb" in page and 'id="s-popup"' not in page and 'data-popup="open"' not in page


def test_text_is_escaped():
    page = _page({"text": "<script>alert(1)</script>", "photos": [P1], "popup": True}, public=True)
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page
