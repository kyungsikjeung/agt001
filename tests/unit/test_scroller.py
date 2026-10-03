"""가로 넘기기 줄(.s-scroller): 마우스로 보는 화면에서도 넘길 수 있게 화살표·끌어 넘기기 (10/4, 2안 '주변' 사진).

손가락·트랙패드·Shift+휠은 원래 넘어갔고, 마우스는 끌기·화살표가 없어 빌더 미리보기에서 '안 넘어간다'로 보였다.
"""
from app.services import site_render

TOKENS = {"palette": "forest", "font_pair": "serif-warm", "density": "comfortable", "radius": "soft", "image_style": "card"}


def _page(items, variant="swipe", **kw):
    spec = {"version": 3, "tokens": dict(TOKENS),
            "sections": [{"id": "view", "type": "gallery", "variant": variant, "content": {"label": "주변", "items": items}}]}
    return site_render.render_site(spec, site_key="t", title="t", kind="pension", **kw)


PHOTOS = [{"src": f"/uploads/p{i}.jpg", "alt": f"사진 {i}"} for i in range(4)]


def test_swipe_gallery_has_arrows_and_one_script():
    page = _page(PHOTOS, public=True)
    assert '<div class="s-scroller">' in page and 'class="s-gallery__swipe" data-scroller' in page
    assert 'aria-label="이전 사진"' in page and BTN in page
    assert page.count("function pos(t)") == 1  # 문서에 한 번만(구역마다 아님)


BTN = 'data-action="scroll" data-dir="1" aria-label="다음 사진"'


def test_example_swipe_gallery_also_scrolls():
    page = _page([], edit=True)  # 사진 0장 → 예시 그림 줄
    assert 'class="s-gallery__swipe" data-scroller' in page and BTN in page


def test_design_preview_has_no_arrows_or_script():
    """시안 미리보기는 sandbox(스크립트 없음)라 화살표를 빼 둔다 — 눌러도 안 되는 버튼 금지."""
    for items in (PHOTOS, []):
        page = _page(items, public=False)
        assert 'data-scroller' in page and BTN not in page and "<script" not in page


def test_no_script_without_strip_but_always_in_editor():
    assert "function pos(t)" not in _page(PHOTOS, variant="grid", public=True)
    # 편집 미리보기는 나중에 구역을 바꿔 끼울 수 있어 늘 넣는다
    assert "function pos(t)" in _page(PHOTOS, variant="grid", edit=True)


def test_arrows_only_for_mouse_screens():
    css = site_render._bundle()["site_css"]
    i = css.index("@media (hover: hover) and (pointer: fine)", css.index(".s-scroller__btn { display: none; }"))
    assert ".s-scroller__btn {" in css[i:i + 600]
