"""사진 구역 설정 (10/4): 보일 사진 수·움직임. 구역 편집(layout_edits.settings)으로 저장하고 렌더러가 읽는다."""
import re

from app.services import layout_edits as LE
from app.services import site_render as SR

BP = {"strategies": [{"hero": "photo-overlay", "sections": [
    {"id": "space", "type": "gallery", "variant": "swipe", "bind": "space_photos"},
    {"id": "around", "type": "around", "variant": "map", "bind": "location"},
    {"id": "inquiry", "type": "contact", "variant": "form", "bind": "none"}]}]}


def test_normalize_keeps_only_gallery_and_known_values():
    out = LE.normalize({"settings": {
        "space": {"count": 6, "motion": "still"},
        "around": {"count": 3},                       # 사진 구역이 아님
        "nope": {"count": 3},                         # 없는 구역
    }}, BP, 0)
    assert out["settings"] == {"space": {"count": 6, "motion": "still"}}
    assert LE.normalize({"settings": {"space": {"count": 7, "motion": "dance"}}}, BP, 0) is None
    assert LE.normalize({"settings": {"space": {"count": True}}}, BP, 0) is None


def test_apply_puts_settings_on_section_and_sections_lists_them():
    edits = {"settings": {"space": {"count": 3}}}
    spec = LE.apply({"sections": [{"id": "hero"}, {"id": "space", "type": "gallery"}, {"id": "around"}, {"id": "inquiry"}]},
                    BP, 0, edits)
    assert next(s for s in spec["sections"] if s["id"] == "space")["settings"] == {"count": 3}
    listed = {s["id"]: s["settings"] for s in LE.sections(BP, 0, edits)}
    assert listed["space"] == {"count": 3} and listed["around"] == {}


TOKENS = {"palette": "forest", "font_pair": "serif-warm", "density": "comfortable", "radius": "soft", "image_style": "card"}


def _gallery(settings=None, variant="grid"):
    sec = {"id": "g", "type": "gallery", "variant": variant, "content": {"items": [
        {"src": f"/art/ex/pension-space{i % 3 + 1}.webp", "alt": f"사진 {i}"} for i in range(8)]}}
    if settings is not None:
        sec["settings"] = settings
    return SR.render_site({"tokens": TOKENS, "sections": [sec]})


def test_render_count_and_motion():
    assert len(re.findall(r"<img", _gallery())) == 8
    doc = _gallery({"count": 3, "motion": "lively"})
    assert len(re.findall(r"<img", doc)) == 3
    assert 'data-section-id="g"' in doc and 'data-motion="lively"' in doc
    assert 'data-motion="dance"' not in _gallery({"motion": "dance"})
    assert 'section[data-motion="still"]' in doc                       # CSS는 늘 실려 있다
    # 기본값이면 출력이 그대로(설정 전과 같은 바이트)
    assert _gallery({}) == _gallery()


def test_api_saves_settings_and_keeps_them_on_move(client):
    from tests.unit.test_card_api import _cafe_room, _section_ids
    rid = _cafe_room(client)
    h = {"X-Member-Id": "owner"}
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"layout": {"variant": "v1", "settings": {
        "space": {"count": 3, "motion": "still"}, "around": {"count": 3}}}})
    assert r.status_code == 200, r.text
    assert r.json()["layout"]["v1"]["settings"] == {"space": {"count": 3, "motion": "still"}}
    pv = client.get(f"/api/rooms/{rid}/card/preview?variant=v1", headers=h).json()
    assert next(s for s in pv["sections"] if s["id"] == "space")["settings"] == {"count": 3, "motion": "still"}
    assert re.search(r'data-section-id="space"[^>]*data-motion="still"', pv["html"])
    # 순서만 바꿔도(설정을 안 보냄) 설정은 그대로
    order = [i for i in _section_ids(pv["html"]) if i not in ("hero", "inquiry")]
    r = client.put(f"/api/rooms/{rid}/card", headers=h, json={"layout": {"variant": "v1", "order": list(reversed(order))}})
    assert r.json()["layout"]["v1"]["settings"] == {"space": {"count": 3, "motion": "still"}}
    # 미리 그리기(draft)도 같은 설정으로 그린다
    d = client.post(f"/api/rooms/{rid}/card/preview/draft", headers=h, json={
        "variant": "v1", "layout": {"variant": "v1", "settings": {"space": {"motion": "calm"}}}}).json()
    space = next(p for p in d["parts"] if p["id"] == "space")
    assert 'data-motion="calm"' in space["html"]
