"""컴포넌트 엔진 (COMPONENT_ENGINE_PLAN): 등록표·공용 조각·구역 조각 렌더·스타일 축·구역 모양 바꾸기."""
import copy
import json
import re
from pathlib import Path

from app.services import components as COMP
from app.services import layout_edits as LE
from app.services import site_data as SD
from app.services import site_render as SR

ROOT = Path(__file__).resolve().parents[2] / "templates"


def _cafe_spec() -> dict:
    return json.loads((ROOT / "samples" / "cafe.json").read_text(encoding="utf-8"))


def _gallery_spec(variant: str, label: str = "") -> dict:
    spec = _cafe_spec()
    spec["sections"] = [
        {"id": "hero", "type": "hero", "variant": "text-only", "content": {"title": "연남 느린오후"}},
        {"id": "space", "type": "gallery", "variant": variant,
         "content": {"label": label, "items": [{"src": "/uploads/r/1.jpg", "alt": "창가"},
                                               {"src": "/uploads/r/2.jpg", "alt": "카운터"}]}},
    ]
    return spec


# ---- 등록표 ----

def test_registry_matches_templates():
    """모든 템플릿이 등록표에 있고, 묶음의 변형마다 템플릿이 있고, {{> label}}을 쓰면 기본 제목이 있다."""
    assert COMP.problems() == []


def test_shapes_are_same_data_siblings():
    gallery = [s["variant"] for s in COMP.shapes("gallery", "space_photos")]
    assert gallery == ["grid", "swipe", "marquee", "masonry"]
    assert COMP.can_switch("offerings", "catalog", "compact")
    assert not COMP.can_switch("offerings", "signature", "compact")  # 다른 데이터(bind)는 못 바꾼다
    assert not COMP.can_switch("gallery", "space_photos", "nope")
    assert COMP.shapes("staff", "staff") == []  # 사람 수로 모양이 정해지는 구역은 묶음이 없다
    assert any(s["new"] for s in COMP.shapes("gallery", "space_photos"))


# ---- 공용 조각 {{> label}} ----

def test_label_partial_uses_registry_default_or_given_label():
    html = SR.render_site(_gallery_spec("grid"))
    assert '<h2 id="gallery-title-space">사진첩</h2>' in html
    html = SR.render_site(_gallery_spec("grid", label="우리 공간"))
    assert '<h2 id="gallery-title-space">우리 공간</h2>' in html
    assert "{{" not in html


# ---- render_page ----

def test_render_page_matches_render_site_and_keys_parts():
    spec = _cafe_spec()
    for mode in ({}, {"public": True}, {"edit": True}):
        page = SR.render_page(copy.deepcopy(spec), site_key="k", **mode)
        assert page["html"] == SR.render_site(copy.deepcopy(spec), site_key="k", **mode)
    page = SR.render_page(spec, site_key="k", edit=True)
    sections = [p for p in page["parts"] if p["section"]]
    assert page["order"] == [p["key"] for p in sections]
    for part in sections:
        # 구역 조각 하나 = 뿌리 요소 하나, 그 뿌리의 data-section-id가 key (미리보기가 그대로 바꿔 끼운다)
        roots = re.findall(r'^<(section|nav|div)[^>]*data-section-id="([^"]+)"', part["html"].lstrip())
        assert roots and roots[0][1] == part["key"], part["key"]
    assert all(not p["key"].startswith("@") for p in sections)


def test_shell_stays_when_only_section_content_changes():
    spec = _gallery_spec("grid")
    one = SR.render_page(copy.deepcopy(spec), edit=True)
    spec["sections"][1]["content"]["label"] = "새 제목"
    two = SR.render_page(copy.deepcopy(spec), edit=True)
    assert one["shell"] == two["shell"]
    changed = [p["key"] for p, q in zip(one["parts"], two["parts"]) if p["hash"] != q["hash"]]
    assert changed == ["space"]


def test_theme_is_separate_in_edit_mode_only():
    page = SR.render_page(_cafe_spec(), edit=True)
    assert '<style id="agt-theme">' in page["html"] and page["theme"]["css"] in page["html"]
    assert "agt-patch" in page["html"] and "e.source!==parent" in page["html"]
    assert '<style id="agt-theme">' not in SR.render_site(_cafe_spec())
    assert '<style id="agt-theme">' not in SR.render_site(_cafe_spec(), public=True)


def test_palette_change_keeps_shell_and_section_parts():
    """색만 바뀌면 뼈대·구역 조각은 같고 토큰 CSS만 다르다 → 다시 불러오지 않고 바꿔 끼운다."""
    spec = _gallery_spec("grid")
    one = SR.render_page(copy.deepcopy(spec), edit=True)
    spec["tokens"]["palette"] = "forest"
    two = SR.render_page(copy.deepcopy(spec), edit=True)
    assert one["shell"] == two["shell"]
    assert [p["hash"] for p in one["parts"] if p["section"]] == [p["hash"] for p in two["parts"] if p["section"]]
    assert one["theme"]["css"] != two["theme"]["css"]


# ---- 스타일 축 ----

def _body_tag(html: str) -> str:
    return re.search(r"</head>\n(<body[^>]*>)", html).group(1)


def test_style_axes_default_adds_nothing():
    html = SR.render_site(_cafe_spec())
    assert _body_tag(html) == "<body>"
    spec = _cafe_spec()
    spec["tokens"].update({"surface": "soft", "heading": "bar"})  # 기본값 = 지금 모양
    assert SR.render_site(spec) == html


def test_style_axes_set_body_attrs_and_drop_unknown():
    spec = _cafe_spec()
    spec["tokens"].update({"surface": "outline", "heading": "eyebrow"})
    page = SR.render_page(spec, edit=True)
    assert '<body data-surface="outline" data-heading="eyebrow" data-edit-mode>' in page["html"]
    assert page["theme"]["attrs"] == {"data-surface": "outline", "data-heading": "eyebrow"}
    assert set(page["theme"]["axes"]) == {"data-surface", "data-heading"}
    spec["tokens"].update({"surface": "<b>", "heading": "display"})
    html = SR.render_site(spec, public=True)
    assert '<body data-heading="display" class="is-public">' in html


def test_clean_style():
    assert COMP.clean_style({"surface": "flat", "heading": "bar", "x": "y"}) == {"surface": "flat"}
    assert COMP.clean_style({"surface": "nope"}) == {}
    assert COMP.clean_style(None) == {}


# ---- 새 변형 ----

def test_new_variants_render_and_hide_empty_in_public():
    spec = _gallery_spec("masonry")
    html = SR.render_site(spec)
    assert 's-gallery--masonry' in html and 'loading="lazy"' in html
    spec = _cafe_spec()
    spec["sections"] = [
        {"id": "hero", "type": "hero", "variant": "text-only", "content": {"title": "가게"}},
        {"id": "menu", "type": "offerings", "variant": "compact",
         "content": {"items": [{"name": "아메리카노", "price": "4,500원", "desc": "산미 적은"},
                              {"name": "라떼", "price": ""}]}},
        {"id": "greeting", "type": "intro", "variant": "quote", "content": {"body": "동네 커피를 볶아요"}},
    ]
    html = SR.render_site(spec)
    assert 's-board__dots' in html and "4,500원" in html and "[가격 입력]" in html
    assert '<blockquote class="s-quote"><p>동네 커피를 볶아요</p></blockquote>' in html
    spec["sections"][2]["content"]["body"] = ""
    assert "s-intro--quote" not in SR.render_site(spec, public=True)  # 빈 소개는 공개본에서 뺀다(형제와 같게)


def test_compact_fill_uses_flat_items_like_list_price():
    sec = {"id": "menu", "type": "offerings", "variant": "compact", "bind": "catalog"}
    data = {"catalog": [{"name": "커피", "items": [{"name": "아메리카노", "price": "4,500원"}]}]}
    SD._fill_catalog(sec, data, {"prices": {}, "catalog": [], "photos": {}}, "A", False)
    assert [i["name"] for i in sec["content"]["items"]] == ["아메리카노"]


# ---- 구역 모양 바꾸기 (layout_edits.variants) ----

def _blueprint() -> dict:
    return json.loads((ROOT / "blueprints" / "A-dinein.json").read_text(encoding="utf-8"))


def test_variants_normalize_keeps_only_switchable_and_non_default():
    bp = _blueprint()
    gid = next(n["id"] for n in bp["strategies"][0]["sections"] if n["type"] == "gallery")
    base = next(n["variant"] for n in bp["strategies"][0]["sections"] if n["id"] == gid)
    got = LE.normalize({"variants": {gid: "masonry", "hero": "cinematic", "nope": "grid"}}, bp, 0)
    assert got["variants"] == {gid: "masonry", "hero": "cinematic"}
    assert LE.normalize({"variants": {gid: base}}, bp, 0) is None  # 기본 모양과 같으면 효과 없음
    assert LE.normalize({"variants": {gid: "compact"}}, bp, 0) is None  # 다른 데이터의 모양은 버린다
    # 예전 편집(variants 없음)은 키도 없다
    assert "variants" not in (LE.normalize({"hidden": [gid]}, bp, 0) or {})


def test_variants_apply_before_fill_and_show_in_sections():
    bp = _blueprint()
    gid = next(n["id"] for n in bp["strategies"][0]["sections"] if n["type"] == "gallery")
    edits = {"variants": {gid: "masonry", "hero": "arch"}}
    spec = LE.apply(SD.skeleton(bp, 0), bp, 0, edits)
    shapes = {s["id"]: s["variant"] for s in spec["sections"]}
    assert shapes[gid] == "masonry" and shapes["hero"] == "arch"
    listed = {s["id"]: s for s in LE.sections(bp, 0, edits)}
    assert listed[gid]["variant"] == "masonry" and listed[gid]["base_variant"] != "masonry"
    assert "masonry" in [x["variant"] for x in listed[gid]["shapes"]]
    assert listed["hero"]["variant"] == "arch"
