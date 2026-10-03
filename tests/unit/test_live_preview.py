"""실시간 미리보기 (COMPONENT_ENGINE_PLAN §5·§6): 저장 전 미리 그리기(draft)·스타일 축·구역 모양 저장."""
from app import store
from test_card_api import _cafe_room

H = {"X-Member-Id": "owner"}


def _preview(client, rid, variant="v1"):
    r = client.get(f"/api/rooms/{rid}/card/preview?variant={variant}", headers=H)
    assert r.status_code == 200
    return r.json()


def _card(rid):
    return store.read_session(store.read_room(rid)["session_id"])["prd"]


def test_preview_has_live_fields(client):
    rid = _cafe_room(client)
    body = _preview(client, rid)
    assert body["shell"] and body["order"] and body["theme"]["css"].startswith(":root{")
    assert [p["id"] for p in body["parts"]] == body["order"]
    assert all(set(p) == {"id", "hash"} for p in body["parts"])
    assert set(body["styles"]) == {"surface", "heading"} and body["style"] == {}
    gallery = next(s for s in body["sections"] if s["bind"] in ("space_photos", "style_photos"))
    assert "masonry" in [x["variant"] for x in gallery["shapes"]]
    assert gallery["variant"] == gallery["base_variant"]


def test_draft_returns_only_changed_sections_and_does_not_save(client):
    rid = _cafe_room(client)
    body = _preview(client, rid)
    have = {p["id"]: p["hash"] for p in body["parts"]}
    before = _card(rid)
    r = client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H, json={
        "variant": "v1", "fields": {"shop_name": "연남 빠른오후"}, "have": have, "shell": body["shell"]})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    out = r.json()
    with_html = [p for p in out["parts"] if "html" in p]
    assert with_html and all(p["hash"] != have.get(p["id"]) for p in with_html)
    assert any("연남 빠른오후" in p["html"] for p in with_html)
    # 이름이 안 들어간 구역은 다시 보내지 않는다
    assert len(with_html) < len(out["parts"])
    assert _card(rid) == before  # 저장하지 않는다


def test_draft_shell_change_sends_full_html_only_when_needed(client):
    rid = _cafe_room(client)
    body = _preview(client, rid)
    r = client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H,
                    json={"variant": "v1", "have": {}, "shell": "different"})
    assert "html" in r.json() and r.json()["html"].startswith("<!doctype html>")
    r = client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H,
                    json={"variant": "v1", "have": {}, "shell": body["shell"]})
    assert "html" not in r.json()


def test_draft_style_changes_theme_attrs_not_sections(client):
    rid = _cafe_room(client)
    body = _preview(client, rid)
    have = {p["id"]: p["hash"] for p in body["parts"]}
    r = client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H, json={
        "variant": "v1", "style": {"variant": "v1", "surface": "outline", "heading": "eyebrow"},
        "have": have, "shell": body["shell"]})
    out = r.json()
    assert out["theme"]["attrs"] == {"data-surface": "outline", "data-heading": "eyebrow"}
    assert not any("html" in p for p in out["parts"]) and "html" not in out


def test_draft_shape_switch_and_bad_input(client):
    rid = _cafe_room(client)
    body = _preview(client, rid)
    gallery = next(s for s in body["sections"] if s["bind"] in ("space_photos", "style_photos"))
    r = client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H, json={
        "variant": "v1", "layout": {"variant": "v1", "order": [], "hidden": [], "added": [],
                                    "variants": {gallery["id"]: "masonry"}},
        "have": {p["id"]: p["hash"] for p in body["parts"]}, "shell": body["shell"]})
    part = next(p for p in r.json()["parts"] if p["id"] == gallery["id"])
    assert "s-gallery--masonry" in part["html"]
    assert client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H,
                       json={"variant": "v9"}).status_code == 400
    assert client.post(f"/api/rooms/{rid}/card/preview/draft", headers=H, json={
        "variant": "v1", "style": {"variant": "v2", "surface": "flat"}}).status_code == 400
    assert client.post(f"/api/rooms/{rid}/card/preview/draft", headers={"X-Member-Id": "guest"},
                       json={"variant": "v1"}).status_code == 403


def test_put_style_saves_and_preview_uses_it(client):
    rid = _cafe_room(client)
    r = client.put(f"/api/rooms/{rid}/card", headers=H,
                   json={"style": {"variant": "v2", "surface": "flat", "heading": "bar"}})
    assert r.status_code == 200
    assert _card(rid)["style_axes"] == {"v2": {"surface": "flat"}}  # 기본값(bar)은 적지 않는다
    v2 = _preview(client, rid, "v2")
    assert v2["style"] == {"surface": "flat"} and 'data-surface="flat"' in v2["html"]
    assert 'data-surface' not in _preview(client, rid, "v1")["html"].split("</head>")[1][:80]
    client.put(f"/api/rooms/{rid}/card", headers=H, json={"style": {"variant": "v2"}})
    assert "style_axes" not in _card(rid)  # 전부 기본값이면 지운다


def test_put_layout_without_variants_keeps_chosen_shapes(client):
    """끌어서 순서만 바꾸는 저장(variants 없음)이 고른 구역 모양을 지우지 않는다."""
    rid = _cafe_room(client)
    body = _preview(client, rid)
    gallery = next(s for s in body["sections"] if s["bind"] in ("space_photos", "style_photos"))
    r = client.put(f"/api/rooms/{rid}/card", headers=H, json={"layout": {
        "variant": "v1", "order": [], "hidden": [], "added": [], "variants": {gallery["id"]: "masonry"}}})
    assert r.status_code == 200
    assert _card(rid)["layout_edits"]["v1"]["variants"] == {gallery["id"]: "masonry"}
    order = list(reversed([s["id"] for s in body["sections"] if not s["locked"]]))
    client.put(f"/api/rooms/{rid}/card", headers=H,
               json={"layout": {"variant": "v1", "order": order, "hidden": [], "added": []}})
    assert _card(rid)["layout_edits"]["v1"]["variants"] == {gallery["id"]: "masonry"}
    again = next(s for s in _preview(client, rid)["sections"] if s["id"] == gallery["id"])
    assert again["variant"] == "masonry"
    # 빈 variants를 보내면 모양을 되돌린다
    client.put(f"/api/rooms/{rid}/card", headers=H,
               json={"layout": {"variant": "v1", "order": order, "hidden": [], "added": [], "variants": {}}})
    assert "variants" not in _card(rid)["layout_edits"]["v1"]
